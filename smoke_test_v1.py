import os
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path('smoke_v1.db').absolute()}"

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Citizen, HumanApproval, OfficerMapping, RuntimeEvent, Ticket  # noqa: E402
from app.tools import ToolGateway  # noqa: E402
from app.v1 import (  # noqa: E402
    approve_human_approval,
    consume_master_alerts,
    handle_citizen_message,
    process_department_queue,
    simulate_officer_reply,
)


def main() -> None:
    db_file = Path("smoke_v1.db")
    if db_file.exists():
        db_file.unlink()

    init_db()
    db = SessionLocal()
    tools = ToolGateway()

    try:
        db.add(
            OfficerMapping(
                department="electricity",
                ward="Ward 12",
                officer_name="Rajesh Kumar",
                officer_contact_type="email",
                officer_contact_value="ward12-electricity@example.org",
            )
        )
        db.commit()

        chat_id = "telegram:citizen:1001"
        assert "full name" in handle_citizen_message(db, chat_id, "Hi")
        assert "mobile" in handle_citizen_message(db, chat_id, "Asha Singh")
        assert "ward and village" in handle_citizen_message(db, chat_id, "9999999999")
        assert "Menu" in handle_citizen_message(db, chat_id, "Ward 12, Rampur")
        issue_type_prompt = handle_citizen_message(db, chat_id, "1")
assert "issue type" in issue_type_prompt
assert "Streetlight" in issue_type_prompt

describe_prompt = handle_citizen_message(db, chat_id, "Streetlight")
assert "describe" in describe_prompt

ticket_reply = handle_citizen_message(
    db, chat_id, "Streetlight near school is not working"
)
assert "Ticket ID:" in ticket_reply

        citizen = db.query(Citizen).filter(Citizen.telegram_chat_id == chat_id).first()
        assert citizen is not None

        ticket = db.query(Ticket).filter(Ticket.citizen_id == citizen.id).order_by(Ticket.id.desc()).first()
        assert ticket is not None
        assert ticket.status == "new"

        processed = process_department_queue(db, tools=tools)
        assert ticket.id in processed

        master_alerts = consume_master_alerts(db)
        assert any(alert["alert_type"] == "department_escalation_sent" for alert in master_alerts)

        approval_id = simulate_officer_reply(db, ticket.id, "Team scheduled repair by tonight")
        approval = db.query(HumanApproval).filter(HumanApproval.id == approval_id).first()
        assert approval is not None and approval.status == "pending"

        master_alerts = consume_master_alerts(db)
        assert any(alert["alert_type"] == "human_approval_requested" for alert in master_alerts)

        result = approve_human_approval(db, approval_id=approval_id, approved_by="master_operator", tools=tools)
        assert result == "approved_and_sent"

        db.refresh(ticket)
        assert ticket.status == "approved_for_citizen_update"

        citizen_events = db.query(RuntimeEvent).filter(RuntimeEvent.message.like("citizen::dry_run_sent%"))
        assert citizen_events.count() >= 1

        print("V1 smoke test passed.")
        print(f"Created ticket_id={ticket.id}, human_approval_id={approval_id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
