"""Tool contract for V2.0 agents.

Every tool is a callable class with a name, description, JSON schema for inputs,
and an execute method. The agent's dispatch loop builds the OpenAI tool list
from these, parses tool calls from the LLM response, and routes each call to
the matching execute method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.engine import Engine


class ToolError(Exception):
    """Raised when a tool execution fails. The agent catches this and surfaces it
    in agent_actions. Does not crash the dispatch loop."""


@dataclass
class ToolResult:
    success: bool
    data: dict
    error: Optional[str] = None


class Tool(ABC):
    """Base class for V2.0 tools.

    Subclasses must define:
      name: str            — the tool name as seen by the LLM
      description: str     — short description for the LLM
      input_schema: dict   — JSON schema for the tool's inputs (per OpenAI tool format)

    And implement:
      execute(self, inputs: dict, engine: Engine, conversation_id: str) -> ToolResult
    """

    name: str = ""
    description: str = ""
    input_schema: dict = {}

    def __init__(self) -> None:
        if not self.name:
            raise ToolError(f"{type(self).__name__} must define name")
        if not self.description:
            raise ToolError(f"{type(self).__name__} must define description")
        if not self.input_schema:
            raise ToolError(f"{type(self).__name__} must define input_schema")

    @abstractmethod
    def execute(self, inputs: dict, engine: Engine, conversation_id: str) -> ToolResult:
        """Run the tool. Return ToolResult, do not raise except for catastrophic errors."""

    def to_openai_tool(self) -> dict:
        """Format for the OpenAI tools array."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
                "strict": True,
            },
        }
