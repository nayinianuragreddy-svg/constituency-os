from sqlalchemy.orm import Session

from app.models import RuntimeEvent


class ToolGateway:
    """Tool layer for external communication; currently dry-run only."""

    def send_officer_message(self, db: Session, target: str, message: str, office_id: int = 1) -> str:
        status = f"dry_run_sent::{target}::{message}"
        db.add(RuntimeEvent(actor="ToolGateway", message=f"officer::{status}", office_id=office_id))
        db.commit()
        return status

    def send_citizen_update(self, db: Session, chat_id: str, message: str, office_id: int = 1) -> str:
        status = f"dry_run_sent::{chat_id}::{message}"
        db.add(RuntimeEvent(actor="ToolGateway", message=f"citizen::{status}", office_id=office_id))
        db.commit()
        return status
