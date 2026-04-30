import json
import os
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal


@dataclass
class LLMResult:
    success: bool
    text: str
    fallback_used: bool
    model: str | None = None
    error: str | None = None
    parsed_json: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] | None = None


_call_times: deque[datetime] = deque()
_daily_cost: dict[str, float] = {}
_limits_lock = threading.Lock()


def _log(action_type: str, message: str, metadata: dict[str, Any] | None = None) -> None:
    agent_name = (metadata or {}).get("agent_name", "llm_spine")
    print(
        json.dumps(
            {
                "action_type": action_type,
                "agent_name": agent_name,
                "message": message,
            }
        )
    )


def load_prompt(name: str, variables: dict[str, Any] | None = None) -> str:
    """Load prompts/{name}.md with simple {variable} substitution."""
    path = Path("prompts") / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    template = path.read_text(encoding="utf-8")
    if not variables:
        return template
    return template.format(**variables)


def _within_limits(estimated_cost: float) -> bool:
    now = datetime.now(timezone.utc)
    minute_ago = now.timestamp() - 60
    max_calls = int(os.getenv("LLM_MAX_CALLS_PER_MINUTE", "30"))
    max_cost = float(os.getenv("LLM_MAX_COST_PER_DAY", "5.00"))
    day_key = now.date().isoformat()

    with _limits_lock:
        while _call_times and _call_times[0].timestamp() < minute_ago:
            _call_times.popleft()
        if len(_call_times) >= max_calls:
            return False

        today_cost = _daily_cost.get(day_key, 0.0)
        if today_cost + estimated_cost > max_cost:
            return False

        _call_times.append(now)
        _daily_cost[day_key] = today_cost + estimated_cost
    return True


def llm_call(
    *,
    user_prompt: str,
    system_prompt: str,
    model: str | None = None,
    temperature: float = 0.2,
    tools: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    provider_call: Callable[..., dict[str, Any]] | None = None,
    response_format: Literal["text", "json"] = "text",
    json_schema: dict[str, Any] | None = None,
    estimated_cost: float = 0.0,
) -> LLMResult:
    """Phase-1 LLM wrapper.

    tools must follow OpenAI function-calling schema:
    [{"type": "function", "function": {"name": str, "description": str, "parameters": dict}}]

    metadata shape:
    {
      "agent_name": str,
      "purpose": str,
      "office_id": int,
      "citizen_id": int | None,
      "ticket_id": int | None,
      "idempotency_key": str | None
    }
    """
    # Per-agent model override: LLM_MODEL_<AGENT_NAME> > LLM_MODEL > "gpt-4o-mini"
    if model is None:
        agent_name = (metadata or {}).get("agent_name", "").upper()
        model = os.getenv(f"LLM_MODEL_{agent_name}") or os.getenv("LLM_MODEL", "gpt-4o-mini")

    if not os.getenv("LLM_ENABLED", "false").lower() == "true":
        return LLMResult(
            success=True,
            text="",
            fallback_used=True,
            parsed_json={} if response_format == "json" else None,
        )

    if not _within_limits(estimated_cost):
        _log("llm.throttled", "Rate or cost limit reached; fallback used.", metadata)
        return LLMResult(success=True, text="", fallback_used=True)

    if provider_call is None:
        return LLMResult(success=False, text="", fallback_used=True, error="provider_call is required")

    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "15"))
    sp = system_prompt
    if response_format == "json":
        sp += "\nReturn JSON only. Do not include markdown or extra text."
        if json_schema:
            sp += f"\nTarget JSON schema: {json.dumps(json_schema)}"

    def _invoke() -> dict[str, Any]:
        return provider_call(
            model=model,
            system_prompt=sp,
            user_prompt=user_prompt,
            temperature=temperature,
            tools=tools,
            metadata=metadata,
        )

    for attempt in range(2 if response_format == "json" else 1):
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                raw = pool.submit(_invoke).result(timeout=timeout)
        except FutureTimeoutError:
            _log("llm.error", "Provider timeout; fallback used.", metadata)
            return LLMResult(success=True, text="", fallback_used=True, error="timeout")
        except Exception as exc:  # noqa: BLE001
            return LLMResult(success=False, text="", fallback_used=True, error=str(exc))

        text = raw.get("text", "")
        tool_calls = raw.get("tool_calls")

        if response_format == "json":
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return LLMResult(
                        success=True,
                        text=text,
                        fallback_used=False,
                        model=model,
                        parsed_json=parsed,
                        tool_calls=tool_calls,
                    )
            except json.JSONDecodeError:
                if attempt == 0:
                    continue
                return LLMResult(
                    success=False,
                    text=text,
                    fallback_used=False,
                    model=model,
                    error="json_parse_failed",
                    parsed_json=None,
                    tool_calls=tool_calls,
                )
        else:
            return LLMResult(
                success=True,
                text=text,
                fallback_used=False,
                model=model,
                tool_calls=tool_calls,
            )

    return LLMResult(success=False, text="", fallback_used=True, error="unknown_failure")
