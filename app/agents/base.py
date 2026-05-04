"""BaseAgent: the runtime contract every V2.0 agent extends.

The four NotImplementedError stubs from PR 4a are replaced with real
implementations in this file (PR 4e). Subclasses provide response_schema()
and, optionally, override the grounding/validation hooks.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.engine import Engine

from app.agents.runtime.llm_client import LLMClient, LLMClientError
from app.agents.runtime.state_reader import StateReader, StateReaderError
from app.agents.runtime.action_logger import ActionLogger
from app.agents.runtime.prompt_renderer import PromptRenderer, PromptRendererError
from app.agents.runtime.structured_data_validator import (
    StructuredDataValidator,
    StructuredDataValidatorError,
)
from app.agents.runtime.grounding_checker import SubstringGroundingChecker


# ---------------------------------------------------------------------------
# V2.0 base class
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    """The shape every agent's dispatch() returns."""
    reply_text: Optional[str]
    tool_calls_made: list[dict]
    cost_usd: float
    hops_used: int
    escalated: bool
    error: Optional[str]


@dataclass
class AgentContext:
    """Inputs passed to dispatch() per turn."""
    conversation_id: str
    incoming_message: str
    incoming_message_script: str  # 'telugu' | 'devanagari' | 'roman'
    citizen_id: Optional[str]


class BaseAgent(ABC):
    """Every agent in Constituency OS extends this class.

    Subclasses must define:
      agent_name: str
      runtime_pattern: str  # 'reactive' | 'periodic' | 'interactive' | 'location_triggered' | 'event_triggered'

    Subclasses must implement:
      response_schema() -> dict   # JSON schema for the LLM's structured output

    See Doc C v2.1 §3 for the Communication Agent's specific config.
    """

    agent_name: str = ""
    runtime_pattern: str = ""
    max_hops: int = 3
    max_session_turns: int = 40
    cost_ceiling_usd_per_day: float = 2.00
    tools: list[str] = []
    system_prompt_path: str = ""

    def __init__(
        self,
        engine: Engine,
        llm_client: LLMClient,
        prompt_renderer: PromptRenderer,
        validator: Optional[StructuredDataValidator] = None,
        grounding_checker: Optional[SubstringGroundingChecker] = None,
        model: Optional[str] = None,
    ) -> None:
        if not self.agent_name:
            raise ValueError(f"{type(self).__name__} must define agent_name")
        if not self.runtime_pattern:
            raise ValueError(f"{type(self).__name__} must define runtime_pattern")

        self._engine = engine
        self._llm_client = llm_client
        self._prompt_renderer = prompt_renderer
        self._validator = validator if validator is not None else StructuredDataValidator()
        self._grounding_checker = grounding_checker if grounding_checker is not None else SubstringGroundingChecker()
        self._state_reader = StateReader(engine)
        self._action_logger = ActionLogger(engine)
        self._model = model or os.getenv("LLM_MODEL_COMMUNICATION", "gpt-4o-mini")

    @abstractmethod
    def response_schema(self) -> dict:
        """Return the JSON schema the LLM must conform to. Subclasses override."""

    def category_schema_for_validation(self, conversation_summary: dict) -> Optional[dict]:
        """Return the loaded category schema for validating extracted fields, or None.

        Default: None. Subclasses override when they know which sub-category
        the conversation is currently in.
        """
        return None

    def grounded_field_pairs(
        self, conversation_summary: dict, parsed: dict
    ) -> list[tuple[str, str]]:
        """Return (field_name, value) pairs that should be grounded against transcript.

        Default: empty list. Subclasses override when they extract text values that
        should be grounded.
        """
        return []

    def transcript_for_grounding(self, conversation_summary: dict, incoming_message: str) -> str:
        """Return the transcript string used for grounding.

        Default: last 20 history_compressed entries plus the incoming message.
        """
        history = (conversation_summary.get("history_compressed") or [])[-20:]
        parts = [entry.get("text", "") for entry in history]
        parts.append(incoming_message or "")
        return " ".join(parts)

    def dispatch(self, context: AgentContext) -> AgentResult:
        """Run one turn. Implements Doc B v2.1 §3."""
        try:
            summary = self._state_reader.read(context.conversation_id)
        except StateReaderError as exc:
            return self._fail("read_state_failed", context, str(exc))

        try:
            system_prompt = self._prompt_renderer.render(
                conversation_summary=summary,
                category_schema=self.category_schema_for_validation(summary),
            )
        except PromptRendererError as exc:
            return self._fail("render_failed", context, str(exc))

        try:
            llm_response = self._llm_client.call(
                model=self._model,
                system_prompt=system_prompt,
                user_message=context.incoming_message,
                response_schema=self.response_schema(),
            )
        except LLMClientError as exc:
            return self._fail("llm_call_failed", context, str(exc))

        parsed = llm_response.parsed

        cat_schema = self.category_schema_for_validation(summary)
        if cat_schema:
            try:
                self._validator.validate(parsed, cat_schema)
            except StructuredDataValidatorError as exc:
                return self._fail(
                    "validation_failed", context, str(exc), cost_usd=llm_response.cost_usd
                )

        grounding_failures: list = []
        pairs = self.grounded_field_pairs(summary, parsed)
        if pairs:
            transcript = self.transcript_for_grounding(summary, context.incoming_message)
            report = self._grounding_checker.check(pairs, transcript)
            if not report.all_grounded:
                grounding_failures = [
                    {"field": f.field_name, "value": f.extracted_value, "reason": f.reason}
                    for f in report.failures
                ]

        self._action_logger.log(
            agent_name=self.agent_name,
            conversation_id=context.conversation_id,
            action_type="dispatch",
            payload={
                "incoming_message": context.incoming_message,
                "parsed": parsed,
                "model": llm_response.model,
                "input_tokens": llm_response.input_tokens,
                "output_tokens": llm_response.output_tokens,
                "grounding_failures": grounding_failures,
            },
            cost_usd=llm_response.cost_usd,
            hops_used=1,
            error=None,
        )

        return AgentResult(
            reply_text=parsed.get("reply_text"),
            tool_calls_made=[],
            cost_usd=llm_response.cost_usd,
            hops_used=1,
            escalated=False,
            error=None,
        )

    def _fail(
        self,
        action_type: str,
        context: AgentContext,
        error: str,
        cost_usd: float = 0.0,
    ) -> AgentResult:
        try:
            self._action_logger.log(
                agent_name=self.agent_name,
                conversation_id=context.conversation_id,
                action_type=action_type,
                payload={"incoming_message": context.incoming_message, "error": error},
                cost_usd=cost_usd,
                hops_used=0,
                error=error,
            )
        except Exception:
            # Logging the failure must not raise. Swallow.
            pass
        return AgentResult(
            reply_text=None,
            tool_calls_made=[],
            cost_usd=cost_usd,
            hops_used=0,
            escalated=False,
            error=error,
        )
