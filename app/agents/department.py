from sqlalchemy.orm import Session

from app.agents.base import StatelessAgent
from app.models import AgentAlert, Citizen, OfficerMapping, OfficerMessage, Ticket, TicketUpdate
from app.tools import ToolGateway


class DepartmentCoordinationAgent(StatelessAgent):
    def coordinate_new_electricity_tickets(self, db: Session, tools: ToolGateway) -> list[int]:
        tickets = (
            db.query(Ticket)
            .filter(Ticket.department == "electricity", Ticket.status == "new")
            .order_by(Ticket.id.asc())
            .all()
        )
        processed: list[int] = []
        for ticket in tickets:
            citizen = db.query(Citizen).filter(Citizen.id == ticket.citizen_id).first()
            if citizen is None:
                continue
            mapping = (
                db.query(OfficerMapping)
                .filter(
                    OfficerMapping.department == "electricity",
                    OfficerMapping.ward == citizen.ward,
                )
                .first()
            )
            if mapping is None:
                continue

            outbound_text = f"Ticket {ticket.id}: {ticket.subcategory} - {ticket.description}"
            delivery_status = tools.send_officer_message(
                db,
                target=f"{mapping.officer_contact_type}:{mapping.officer_contact_value}",
                message=outbound_text,
                office_id=ticket.office_id,
            )
            db.add(
                OfficerMessage(
                    ticket_id=ticket.id,
                    officer_mapping_id=mapping.id,
                    direction="outbound",
                    message_text=outbound_text,
                    status=delivery_status,
                    office_id=ticket.office_id,
                )
            )
            ticket.status = "sent_to_department"
            db.add(
                TicketUpdate(
                    ticket_id=ticket.id,
                    status="sent_to_department",
                    note="Escalated to electricity department officer",
                    source="department_coordination_agent",
                    office_id=ticket.office_id,
                )
            )
            db.add(
                AgentAlert(
                    source_agent=self.name,
                    alert_type="department_escalation_sent",
                    payload={"ticket_id": ticket.id},
                    office_id=ticket.office_id,
                )
            )
            processed.append(ticket.id)
        db.commit()
        return processed
