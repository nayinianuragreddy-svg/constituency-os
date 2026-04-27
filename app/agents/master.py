from sqlalchemy.orm import Session

from app.agents.base import StatelessAgent
from app.contracts import AgentMessage
from app.models import AgentAlert


class MasterAgent(StatelessAgent):
    def process(self, message: AgentMessage) -> AgentMessage:
        return AgentMessage(
            sender=self.name,
            receiver=message.receiver,
            body=f"master_orchestration::{message.body}",
        )

    def consume_alert_queue(self, db: Session) -> list[dict]:
        alerts = (
            db.query(AgentAlert)
            .filter(AgentAlert.status == "new")
            .order_by(AgentAlert.id.asc())
            .all()
        )
        consumed: list[dict] = []
        for alert in alerts:
            alert.status = "processed"
            consumed.append(
                {
                    "id": alert.id,
                    "source_agent": alert.source_agent,
                    "alert_type": alert.alert_type,
                    "payload": alert.payload,
                }
            )
        db.commit()
        return consumed
