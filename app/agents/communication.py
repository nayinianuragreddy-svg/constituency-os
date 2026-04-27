from app.agents.base import StatelessAgent
from app.contracts import AgentMessage


class CommunicationAgent(StatelessAgent):
    def process(self, message: AgentMessage) -> AgentMessage:
        return AgentMessage(
            sender=self.name,
            receiver=message.receiver,
            body=f"communication_dispatch::{message.body}",
        )
