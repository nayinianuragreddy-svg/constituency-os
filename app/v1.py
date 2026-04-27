from sqlalchemy.orm import Session

from app.agents.communication import CommunicationAgent
from app.agents.department import DepartmentCoordinationAgent
from app.agents.master import MasterAgent
from app.models import AgentAlert, HumanApproval, OfficerMapping, OfficerMessage, Ticket, TicketUpdate
from app.tools import ToolGateway


def handle_citizen_message(db: Session, telegram_chat_id: str, text: str) -> str:
    agent = CommunicationAgent(name="CommunicationAgent")
    return agent.handle_citizen_message(db=db, telegram_chat_id=telegram_chat_id, text=text)


def process_department_queue(db: Session, tools: ToolGateway) -> list[int]:
    agent = DepartmentCoordinationAgent(name="DepartmentCoordinationAgent")
    return agent.coordinate_new_electricity_tickets(db=db, tools=tools)


def simulate_officer_reply(db: Session, ticket_id: int, reply_text: str) -> int:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id} not found")

    mapping = (
        db.query(OfficerMapping)
        .join(OfficerMessage, OfficerMessage.officer_mapping_id == OfficerMapping.id)
        .filter(OfficerMessage.ticket_id == ticket_id)
        .order_by(OfficerMessage.id.desc())
        .first()
    )
    if mapping is None:
        raise ValueError(f"No officer mapping found for ticket {ticket_id}")

    db.add(
        OfficerMessage(
            ticket_id=ticket_id,
            officer_mapping_id=mapping.id,
            direction="inbound",
            message_text=reply_text,
            status="received",
            office_id=ticket.office_id,
        )
    )
    ticket.status = "department_replied"
    db.add(
        TicketUpdate(
            ticket_id=ticket_id,
            status="department_replied",
            note=reply_text,
            source="officer_reply_simulation",
            office_id=ticket.office_id,
        )
    )
    approval = HumanApproval(
        ticket_id=ticket_id,
        requested_action="send_update_to_citizen",
        proposed_message=f"Department update for ticket {ticket_id}: {reply_text}",
        status="pending",
        office_id=ticket.office_id,
    )
    db.add(approval)
    db.flush()
    db.add(
        AgentAlert(
            source_agent="OfficerReplySimulation",
            alert_type="human_approval_requested",
            payload={"ticket_id": ticket_id, "human_approval_id": approval.id},
            office_id=ticket.office_id,
        )
    )
    db.commit()
    return approval.id


def approve_human_approval(db: Session, approval_id: int, approved_by: str, tools: ToolGateway) -> str:
    approval = db.query(HumanApproval).filter(HumanApproval.id == approval_id).first()
    if approval is None:
        raise ValueError(f"Human approval {approval_id} not found")
    if approval.status == "approved":
        return "already_approved"

    ticket = db.query(Ticket).filter(Ticket.id == approval.ticket_id).first()
    if ticket is None:
        raise ValueError(f"Ticket {approval.ticket_id} not found")

    from app.models import Citizen

    citizen = db.query(Citizen).filter(Citizen.id == ticket.citizen_id).first()
    if citizen is None:
        raise ValueError(f"Citizen for ticket {ticket.id} not found")

    approval.status = "approved"
    approval.approved_by = approved_by
    ticket.status = "approved_for_citizen_update"
    db.add(
        TicketUpdate(
            ticket_id=ticket.id,
            status="approved_for_citizen_update",
            note="Human approved citizen-facing update",
            source="human_approval_simulation",
            office_id=ticket.office_id,
        )
    )
    db.commit()

    tools.send_citizen_update(
        db,
        chat_id=citizen.telegram_chat_id,
        message=approval.proposed_message,
        office_id=ticket.office_id,
    )
    return "approved_and_sent"


def consume_master_alerts(db: Session) -> list[dict]:
    agent = MasterAgent(name="MasterAgent")
    return agent.consume_alert_queue(db=db)
