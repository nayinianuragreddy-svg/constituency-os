from app.agents.base import StatelessAgent
from app.contracts import AgentMessage


class MasterAgent(StatelessAgent):
    def process(self, message: AgentMessage) -> AgentMessage:
        return AgentMessage(
            sender=self.name,
            receiver=message.receiver,
            body=f"master_orchestration::{message.body}",
        )
