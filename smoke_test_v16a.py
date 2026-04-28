import os
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path('smoke_v16a.db').absolute()}"

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Citizen, CitizenConversation, Ticket  # noqa: E402
from app.v1 import handle_citizen_message  # noqa: E402


def main() -> None:
    db_file = Path("smoke_v16a.db")
    if db_file.exists():
        db_file.unlink()

    init_db()
    db = SessionLocal()

    try:
        chat_id = "telegram:citizen:v16a"

        welcome = handle_citizen_message(db, chat_id, "Hello")
        assert "digital assistant for the MLA office" in welcome
        convo = (
            db.query(CitizenConversation)
            .filter(CitizenConversation.telegram_chat_id == chat_id)
            .first()
        )
        assert convo is not None
        assert convo.state == "welcomed"

        invalid_name = handle_citizen_message(db, chat_id, "Hi")
        assert "full name, not a greeting" in invalid_name

        valid_name = handle_citizen_message(db, chat_id, "Asha Singh")
        assert "mobile number" in valid_name

        invalid_mobile = handle_citizen_message(db, chat_id, "Asha")
        assert "valid 10-digit mobile number" in invalid_mobile

        valid_mobile = handle_citizen_message(db, chat_id, "98765 43210")
        assert "ward and village/locality" in valid_mobile

        invalid_ward = handle_citizen_message(db, chat_id, "12")
        assert "both ward number and village/locality" in invalid_ward

        weak_ward = handle_citizen_message(db, chat_id, "Ward ward")
        assert "both ward number and village/locality" in weak_ward

        valid_ward = handle_citizen_message(db, chat_id, "Ward 12, Rampur")
        assert "Menu:" in valid_ward

        restart_reply = handle_citizen_message(db, chat_id, "restart")
        assert "Welcome back, Asha Singh" in restart_reply
        convo = (
            db.query(CitizenConversation)
            .filter(CitizenConversation.telegram_chat_id == chat_id)
            .first()
        )
        assert convo is not None
        assert convo.state == "awaiting_main_menu"

        post_restart_invalid = handle_citizen_message(db, chat_id, "hello")
        assert "Invalid choice" in post_restart_invalid

        post_restart_name = handle_citizen_message(db, chat_id, "Rekha Devi")
        assert "Invalid choice" in post_restart_name

        assert db.query(Citizen).filter(Citizen.telegram_chat_id == chat_id).count() == 1

        convo.state = "awaiting_ward"
        db.commit()
        duplicate_safe = handle_citizen_message(db, chat_id, "Ward 12, Rampur")
        assert "Welcome back, Asha Singh" in duplicate_safe
        assert db.query(Citizen).filter(Citizen.telegram_chat_id == chat_id).count() == 1

        flow_chat_id = "telegram:citizen:v16a-flow"
        assert "digital assistant" in handle_citizen_message(db, flow_chat_id, "Hi")
        assert "mobile" in handle_citizen_message(db, flow_chat_id, "Ravi Kumar")
        assert "ward and village/locality" in handle_citizen_message(db, flow_chat_id, "9999988888")
        assert "Menu" in handle_citizen_message(db, flow_chat_id, "Ward 9, Lakshmipur")
        flow_convo = (
            db.query(CitizenConversation)
            .filter(CitizenConversation.telegram_chat_id == flow_chat_id)
            .first()
        )
        assert flow_convo is not None
        flow_convo.state = "awaiting_name"
        db.commit()
        assert "Welcome back, Ravi Kumar" in handle_citizen_message(db, flow_chat_id, "Hi again")

        issue_type_prompt = handle_citizen_message(db, flow_chat_id, "1")
        assert "issue type" in issue_type_prompt

        describe_prompt = handle_citizen_message(db, flow_chat_id, "1")
        assert "describe" in describe_prompt

        ticket_reply = handle_citizen_message(db, flow_chat_id, "Frequent power cut in evening")
        assert "Ticket ID:" in ticket_reply

        citizen = db.query(Citizen).filter(Citizen.telegram_chat_id == flow_chat_id).first()
        assert citizen is not None

        ticket = db.query(Ticket).filter(Ticket.citizen_id == citizen.id).order_by(Ticket.id.desc()).first()
        assert ticket is not None
        assert ticket.subcategory == "Streetlight"

        print("V1.6A smoke test passed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
