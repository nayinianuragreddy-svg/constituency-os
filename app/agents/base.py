from dataclasses import dataclass

from app.contracts import AgentMessage


@dataclass(frozen=True)
class StatelessAgent:
    name: str

    def process(self, message: AgentMessage) -> AgentMessage:
        raise NotImplementedError
