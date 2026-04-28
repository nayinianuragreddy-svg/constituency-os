from sqlalchemy.orm import Session

from app.agents.base import StatelessAgent
from app.contracts import AgentMessage
from app.models import Citizen, CitizenConversation, Ticket, TicketUpdate


class CommunicationAgent(StatelessAgent):
    GREETING_WORDS = {"hi", "hello", "hey", "namaste", "namaskaram"}

    def process(self, message: AgentMessage) -> AgentMessage:
        return AgentMessage(
            sender=self.name,
            receiver=message.receiver,
            body=f"communication_dispatch::{message.body}",
        )

    def handle_citizen_message(self, db: Session, telegram_chat_id: str, text: str) -> str:
        clean_text = text.strip()
        convo = (
            db.query(CitizenConversation)
            .filter(CitizenConversation.telegram_chat_id == telegram_chat_id)
            .first()
        )
        if convo is None:
            convo = CitizenConversation(
                telegram_chat_id=telegram_chat_id,
                state="welcomed",
                draft={},
            )
            db.add(convo)
            db.commit()
            return (
                "Namaskaram. This is the digital assistant for the MLA office. "
                "You can use this chat to raise public issues and track complaints. "
                "Before we continue, I need to register your details once. "
                "Please share your full name."
            )

        command = clean_text.lower()
        if command == "restart":
            convo.state = "awaiting_name"
            convo.citizen_id = None
            convo.draft = {}
            db.commit()
            return "Registration restarted. Please share your full name."

        if command in {"back", "go back", "edit"}:
            back_reply = self._go_back_one_step(convo)
            db.commit()
            return back_reply

        draft = dict(convo.draft or {})

        if convo.state == "welcomed":
            convo.state = "awaiting_name"
            db.commit()
            return self.handle_citizen_message(db=db, telegram_chat_id=telegram_chat_id, text=clean_text)

        if convo.state == "awaiting_name":
            if not self._is_valid_name(clean_text):
                return "Please share your full name, not a greeting. Example: Asha Singh."
            draft["name"] = clean_text
            convo.state = "awaiting_mobile"
            convo.draft = draft
            db.commit()
            return "Please share your mobile number."

        if convo.state == "awaiting_mobile":
            if not self._is_valid_mobile(clean_text):
                return "Please share a valid 10-digit mobile number."
            draft["mobile"] = self._digits_only(clean_text)
            convo.state = "awaiting_ward"
            convo.draft = draft
            db.commit()
            return "Please share ward and village/locality. Example: Ward 12, Rampur."

        if convo.state in {"awaiting_ward", "awaiting_ward_village"}:
            if not self._is_valid_ward(clean_text):
                return "Please share your ward and village/locality. Example: Ward 12, Rampur."
            ward, village = self._split_ward_village(clean_text)
            citizen = Citizen(
                name=draft["name"],
                mobile=draft["mobile"],
                ward=ward,
                village=village,
                location_text=clean_text,
                telegram_chat_id=telegram_chat_id,
            )
            db.add(citizen)
            db.flush()
            convo.citizen_id = citizen.id
            draft["ward"] = ward
            draft["village"] = village
            convo.draft = draft
            convo.state = "awaiting_main_menu"
            db.commit()
            return "Menu:\n1. Public Issue\n2. Track Complaint"

        if convo.state == "awaiting_main_menu":
            if clean_text == "1":
                convo.state = "awaiting_electricity_issue_type"
                db.commit()
                return (
                    "Public Issue selected. Please select issue type: "
                    "Streetlight / Power cut / Transformer fault / Other."
                )
            if clean_text == "2":
                return "Track Complaint will be added in V2. Choose 1 for Public Issue."
            return "Invalid choice. Reply 1 for Public Issue or 2 for Track Complaint."

        if convo.state == "awaiting_electricity_issue_type":
            options = {
                "1": "Streetlight",
                "2": "Power cut",
                "3": "Transformer fault",
                "4": "Other",
            }
            subcategory = options.get(clean_text)
            if subcategory is None:
                return "Invalid choice. Reply with 1, 2, 3, or 4."
            draft["category"] = "Public Issue"
            draft["department"] = "electricity"
            draft["subcategory"] = subcategory
            convo.draft = draft
            convo.state = "awaiting_description"
            db.commit()
            return "Please describe the issue."

        if convo.state == "awaiting_description":
            ticket = Ticket(
                citizen_id=convo.citizen_id,
                category=draft["category"],
                subcategory=draft["subcategory"],
                description=clean_text,
                urgency="normal",
                status="new",
                department=draft["department"],
            )
            db.add(ticket)
            db.flush()
            db.add(
                TicketUpdate(
                    ticket_id=ticket.id,
                    status="new",
                    note="Ticket created from citizen chat",
                    source="communication_agent",
                )
            )
            convo.state = "awaiting_main_menu"
            convo.draft = {}
            db.commit()
            return f"Complaint registered. Ticket ID: {ticket.id}"

        convo.state = "awaiting_main_menu"
        db.commit()
        return "Menu:\n1. Public Issue\n2. Track Complaint"

    @classmethod
    def _is_valid_name(cls, text: str) -> bool:
        candidate = text.strip()
        if not candidate:
            return False
        if candidate.lower() in cls.GREETING_WORDS:
            return False
        return any(char.isalpha() for char in candidate)

    @staticmethod
    def _digits_only(text: str) -> str:
        return "".join(char for char in text if char.isdigit())

    @classmethod
    def _is_valid_mobile(cls, text: str) -> bool:
        digits = cls._digits_only(text.strip())
        return len(digits) == 10

    @staticmethod
    def _is_valid_ward(text: str) -> bool:
        candidate = text.strip()
        if len(candidate) < 3:
            return False
        has_alpha = any(char.isalpha() for char in candidate)
        has_digit = any(char.isdigit() for char in candidate)
        return (has_alpha and has_digit) or len(candidate) >= 3

    @staticmethod
    def _go_back_one_step(convo: CitizenConversation) -> str:
        state_back_map = {
            "welcomed": ("awaiting_name", "Please share your full name."),
            "awaiting_name": ("awaiting_name", "Please share your full name."),
            "awaiting_mobile": ("awaiting_name", "Okay, let's update your name. Please share your full name."),
            "awaiting_ward": (
                "awaiting_mobile",
                "Okay, let's update your mobile number. Please share a valid 10-digit mobile number.",
            ),
            "awaiting_ward_village": (
                "awaiting_mobile",
                "Okay, let's update your mobile number. Please share a valid 10-digit mobile number.",
            ),
            "awaiting_main_menu": (
                "awaiting_ward",
                "Okay, let's update your ward and village/locality. Example: Ward 12, Rampur.",
            ),
        }
        next_state, prompt = state_back_map.get(
            convo.state,
            ("awaiting_name", "Please share your full name."),
        )
        convo.state = next_state
        return prompt

    @staticmethod
    def _split_ward_village(text: str) -> tuple[str, str]:
        parts = [chunk.strip() for chunk in text.split(",", maxsplit=1)]
        ward = parts[0] if parts else text
        village = parts[1] if len(parts) > 1 else ""
        return ward, village
