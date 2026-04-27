from typing import Any

from pydantic import BaseModel, Field


class RuntimeRequest(BaseModel):
    action: str = Field(..., examples=["broadcast_update"])
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentMessage(BaseModel):
    sender: str
    receiver: str
    body: str


class RuntimeResponse(BaseModel):
    status: str
    communication: AgentMessage
    dashboard: AgentMessage
    master: AgentMessage
