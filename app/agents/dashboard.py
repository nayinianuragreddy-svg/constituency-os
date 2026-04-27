from app.agents.base import StatelessAgent
from app.contracts import AgentMessage


class DashboardAgent(StatelessAgent):
    def process(self, message: AgentMessage) -> AgentMessage:
        return AgentMessage(
            sender=self.name,
            receiver=message.receiver,
            body=f"dashboard_projection::{message.body}",
        )
