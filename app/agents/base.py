"""BaseAgent: the runtime contract every V2.0 agent extends.

This file is the SKELETON. Method signatures and class structure only.
Real implementations land in PRs 4b through 4e.

Doc B v2.1 §2 defines the runtime components this BaseAgent will compose:
- PromptRenderer (PR 4b)
- StructuredDataValidator (PR 4c)
- SubstringGroundingChecker (PR 4d)
- Full dispatch loop (PR 4e)

StatelessAgent below is retained for V1.9 compatibility; it is deleted in PR 7.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


# ---------------------------------------------------------------------------
# V1.9 base class — retained for compatibility, deleted in PR 7
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StatelessAgent:
    name: str

    def process(self, message: Any) -> Any:
        raise NotImplementedError


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
      max_hops: int
      max_session_turns: int
      cost_ceiling_usd_per_day: float
      tools: list[str]
      system_prompt_path: str

    See Doc C v2.1 §3 for the Communication Agent's specific config.
    """

    agent_name: str = ""
    runtime_pattern: str = ""
    max_hops: int = 3
    max_session_turns: int = 40
    cost_ceiling_usd_per_day: float = 2.00
    tools: list[str] = []
    system_prompt_path: str = ""

    def __init__(self) -> None:
        if not self.agent_name:
            raise ValueError(f"{type(self).__name__} must define agent_name")
        if not self.runtime_pattern:
            raise ValueError(f"{type(self).__name__} must define runtime_pattern")

    @abstractmethod
    def dispatch(self, context: AgentContext) -> AgentResult:
        """Run one turn of the agent. Implemented in PR 4e."""
        raise NotImplementedError("dispatch is implemented in PR 4e")

    def read_state(self, context: AgentContext) -> dict:
        """Load conversation summary from DB. Implemented in PR 4e."""
        raise NotImplementedError("read_state is implemented in PR 4e")

    def call_llm(self, messages: list[dict], tools: list[dict]) -> Any:
        """Single LLM call. Implemented in PR 4e using app/core/llm.py."""
        raise NotImplementedError("call_llm is implemented in PR 4e")

    def log_action(self, action: dict) -> None:
        """Write to agent_actions table. Implemented in PR 4e."""
        raise NotImplementedError("log_action is implemented in PR 4e")
