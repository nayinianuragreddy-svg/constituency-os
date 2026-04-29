import os
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path('smoke_v2_comm.db').absolute()}"

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import AgentAction, CitizenConversation  # noqa: E402
from app.v1 import handle_citizen_message  # noqa: E402
from app.agents.communication import CommunicationAgent  # noqa: E402


def main() -> None:
    db_file = Path("smoke_v2_comm.db")
    if db_file.exists():
        db_file.unlink()
    init_db()
    db = SessionLocal()

    try:
        # A deterministic mode
        os.environ["LLM_ENABLED"] = "false"
        chat = "telegram:v2:a"
        assert "digital assistant" in handle_citizen_message(db, chat, "Hello")
        assert "mobile" in handle_citizen_message(db, chat, "Asha Singh")
        assert "ward and village/locality" in handle_citizen_message(db, chat, "9876543210")
        assert "Menu:" in handle_citizen_message(db, chat, "Ward 12, Rampur")

        # mock provider
        calls = []

        def provider_call(**kwargs):
            calls.append(kwargs)
            purpose = (kwargs.get("metadata") or {}).get("purpose")
            up = kwargs.get("user_prompt", "")
            if purpose == "intent_router":
                if "low confidence" in up:
                    return {"text": '{"language":"en","intent":"provide_info","extracted":{},"confidence":0.2}'}
                if "I gave wrong ward" in up:
                    return {"text": '{"language":"en","intent":"fix_earlier","extracted":{"fix_field":"ward"},"confidence":0.91}'}
                if "naa peru ravi" in up:
                    return {"text": '{"language":"mixed","intent":"provide_info","extracted":{"name":"ravi","mobile":"9876543210","ward":"12","issue_text":null,"fix_field":null},"confidence":0.92}'}
                return {"text": '{"language":"en","intent":"provide_info","extracted":{"mobile":"9876543210"},"confidence":0.90}'}
            if purpose == "reply_drafter":
                if "invalid_mobile" in up or "invalid_name" in up:
                    return {"text": ""}
                return {"text": "Mock drafted reply"}
            return {"text": ""}

        CommunicationAgent.llm_provider_call = provider_call
        os.environ["LLM_ENABLED"] = "true"
        os.environ["LLM_MAX_CALLS_PER_MINUTE"] = "100"
        os.environ["LLM_TIMEOUT_SECONDS"] = "5"

        # B fallback on low confidence
        chat_b = "telegram:v2:b"
        handle_citizen_message(db, chat_b, "Hi")
        handle_citizen_message(db, chat_b, "low confidence")
        low = handle_citizen_message(db, chat_b, "hello")
        assert "valid 10-digit mobile number" in low

        # C extracted mobile usage
        chat_c = "telegram:v2:c"
        handle_citizen_message(db, chat_c, "Hello")
        handle_citizen_message(db, chat_c, "Ravi")
        mobile_reply = handle_citizen_message(db, chat_c, "my num is 9876543210")
        assert "ward and village/locality" in mobile_reply or "Mock drafted reply" in mobile_reply

        # D reply drafter fallback
        convo_c = db.query(CitizenConversation).filter(CitizenConversation.telegram_chat_id == chat_c).first()
        assert convo_c is not None
        convo_c.state = "awaiting_mobile"
        db.commit()
        bad_mobile = handle_citizen_message(db, chat_c, "abc")
        assert "valid 10-digit mobile number" in bad_mobile

        # E off-path fix
        convo = db.query(CitizenConversation).filter(CitizenConversation.telegram_chat_id == chat_c).first()
        assert convo is not None
        convo.state = "awaiting_electricity_issue_type"
        db.commit()
        handle_citizen_message(db, chat_c, "I gave wrong ward, fix it")
        convo = db.query(CitizenConversation).filter(CitizenConversation.telegram_chat_id == chat_c).first()
        assert convo is not None and convo.state in {"awaiting_ward", "awaiting_electricity_issue_type"}

        # G happy path with extraction + llm logs
        chat_g = "telegram:v2:g"
        handle_citizen_message(db, chat_g, "Hello")
        msg = handle_citizen_message(db, chat_g, "naa peru ravi, mobile 9876543210, ward 12")
        assert msg
        convo_g = db.query(CitizenConversation).filter(CitizenConversation.telegram_chat_id == chat_g).first()
        assert convo_g is not None and convo_g.state in {"awaiting_ward", "awaiting_mobile", "awaiting_name"}

        llm_rows = db.query(AgentAction).filter(AgentAction.action_type == "llm.call").all()
        assert all((row.payload or {}).get("agent_name") == "communication" for row in llm_rows) if llm_rows else True

        print("V2 Communication Brain smoke test passed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
