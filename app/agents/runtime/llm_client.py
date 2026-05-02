"""Thin OpenAI wrapper for structured-output calls used by V2.0 agents.

Per Doc B v2.1 §2.4. Returns a parsed dict matching the requested JSON schema,
along with cost and token metadata. Raises LLMClientError on any failure.

This wrapper exists alongside (not replacing) app/core/llm.py, the V1.9 spine.
The V1.9 client supports tool-calling for legacy agents. This one is purpose-built
for V2.0 structured-output dispatch.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


# Approximate per-1k-token costs for cost tracking. These are caller-side estimates;
# the canonical record is the OpenAI billing dashboard.
COST_PER_1K_INPUT_TOKENS = {
    "gpt-5.4-mini": 0.00015,
    "gpt-4o-mini": 0.00015,
    "gpt-4o": 0.0025,
}
COST_PER_1K_OUTPUT_TOKENS = {
    "gpt-5.4-mini": 0.00060,
    "gpt-4o-mini": 0.00060,
    "gpt-4o": 0.01000,
}


@dataclass
class LLMResponse:
    parsed: dict
    raw_text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LLMClientError(Exception):
    """Raised on any failure of the structured-output call."""


class LLMClient:
    """Stateless wrapper around openai.OpenAI for structured-output calls."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key or not key.startswith("sk-"):
            raise LLMClientError("OPENAI_API_KEY missing or malformed")
        self._client = OpenAI(api_key=key)

    def call(
        self,
        model: str,
        system_prompt: str,
        user_message: str,
        response_schema: dict,
        max_completion_tokens: int = 1000,
    ) -> LLMResponse:
        """Make a structured-output call. Returns parsed dict + metadata.

        response_schema is a JSON schema dict per OpenAI's response_format spec.
        """
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "agent_response",
                        "strict": True,
                        "schema": response_schema,
                    },
                },
                max_completion_tokens=max_completion_tokens,
            )
        except Exception as exc:
            raise LLMClientError(f"OpenAI call failed: {exc!r}") from exc

        choice = resp.choices[0]
        raw_text = choice.message.content or ""

        if not raw_text and getattr(choice.message, "refusal", None):
            raise LLMClientError(f"OpenAI refused: {choice.message.refusal}")

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMClientError(
                f"OpenAI returned non-JSON content under structured output: {raw_text[:200]!r}"
            ) from exc

        usage = resp.usage
        in_tok = getattr(usage, "prompt_tokens", 0) or 0
        out_tok = getattr(usage, "completion_tokens", 0) or 0

        cost = self._estimate_cost(model, in_tok, out_tok)

        return LLMResponse(
            parsed=parsed,
            raw_text=raw_text,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
        )

    @staticmethod
    def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        in_rate = COST_PER_1K_INPUT_TOKENS.get(model, 0.0)
        out_rate = COST_PER_1K_OUTPUT_TOKENS.get(model, 0.0)
        return round((input_tokens / 1000.0) * in_rate + (output_tokens / 1000.0) * out_rate, 6)
