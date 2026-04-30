from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class ButtonStyle(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    DANGER = "danger"
    SUCCESS = "success"


@dataclass
class ValidationResult:
    is_valid: bool
    normalized_value: Any = None
    error_hint: str = ""
    code: Literal["valid", "invalid", "skip"] = "invalid"


@dataclass
class Button:
    text: str
    value: str
    style: ButtonStyle = ButtonStyle.PRIMARY


@dataclass
class DbWrite:
    operation: Literal["insert", "update", "upsert", "delete", "raw"]
    table: str
    values: dict[str, Any] = field(default_factory=dict)
    where: dict[str, Any] = field(default_factory=dict)
    sql: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionLog:
    action_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class StateResult:
    next_state: str
    reply_text: str | None = None
    reply_buttons: list[Button] | None = None
    field_collected: tuple[str, Any] | None = None
    db_writes: list[DbWrite] = field(default_factory=list)
    agent_actions_to_log: list[ActionLog] = field(default_factory=list)

    def with_log(self, action_type: str, payload: dict[str, Any] | None = None) -> "StateResult":
        self.agent_actions_to_log.append(ActionLog(action_type=action_type, payload=payload or {}))
        return self
