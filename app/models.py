from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base




class Office(Base):
    __tablename__ = "offices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="Default Office")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

class RuntimeEvent(Base):
    __tablename__ = "runtime_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor: Mapped[str] = mapped_column(String(128), index=True)
    message: Mapped[str] = mapped_column(String(1000))
    office_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Citizen(Base):
    __tablename__ = "citizens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    mobile: Mapped[str] = mapped_column(String(40), index=True)
    ward: Mapped[str] = mapped_column(String(100), index=True)
    village: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    location_text: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    telegram_chat_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    office_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    citizen_id: Mapped[int] = mapped_column(ForeignKey("citizens.id"), index=True)
    category: Mapped[str] = mapped_column(String(100), index=True)
    subcategory: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str] = mapped_column(Text)
    urgency: Mapped[str] = mapped_column(String(50), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(100), default="new", nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(100), index=True)
    office_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TicketUpdate(Base):
    __tablename__ = "ticket_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    status: Mapped[str] = mapped_column(String(100), index=True)
    note: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100), index=True)
    office_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OfficerMapping(Base):
    __tablename__ = "officer_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    department: Mapped[str] = mapped_column(String(100), index=True)
    ward: Mapped[str] = mapped_column(String(100), index=True)
    officer_name: Mapped[str] = mapped_column(String(255))
    officer_contact_type: Mapped[str] = mapped_column(String(50), default="email", nullable=False)
    officer_contact_value: Mapped[str] = mapped_column(String(255))
    office_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class OfficerMessage(Base):
    __tablename__ = "officer_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    officer_mapping_id: Mapped[int] = mapped_column(ForeignKey("officer_mappings.id"), index=True)
    direction: Mapped[str] = mapped_column(String(20), index=True)
    message_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="queued", nullable=False)
    office_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HumanApproval(Base):
    __tablename__ = "human_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    requested_action: Mapped[str] = mapped_column(String(255))
    proposed_message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    approved_by: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    office_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentAlert(Base):
    __tablename__ = "agent_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_agent: Mapped[str] = mapped_column(String(100), index=True)
    alert_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="new", nullable=False, index=True)
    office_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    channel: Mapped[str] = mapped_column(String(50), index=True)
    action_type: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(50), default="processing", nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    response_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    office_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

class CitizenConversation(Base):
    __tablename__ = "citizen_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    office_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    citizen_id: Mapped[int | None] = mapped_column(ForeignKey("citizens.id"), nullable=True)
    telegram_chat_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    current_state: Mapped[str] = mapped_column(String(100), default="s0_identity_check", nullable=False)
    return_to_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    draft_ticket_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    draft_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    last_inbound_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_bot_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_state_change_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    invalid_attempts_in_state: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def state(self):
        return self.current_state

    @state.setter
    def state(self, value):
        self.current_state = value

    @property
    def draft(self):
        return self.draft_payload

    @draft.setter
    def draft(self, value):
        self.draft_payload = value