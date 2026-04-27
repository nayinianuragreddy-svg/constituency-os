from sqlalchemy.orm import Session

from app.agents.base import StatelessAgent
from app.contracts import AgentMessage
from app.models import Citizen, CitizenConversation, Ticket, TicketUpdate


class CommunicationAgent(StatelessAgent):
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
                state="awaiting_name",
                draft={},
            )
            db.add(convo)
            db.commit()
            return "Welcome. Please share your full name."

        draft = dict(convo.draft or {})

        if convo.state == "awaiting_name":
            draft["name"] = clean_text
            convo.state = "awaiting_mobile"
            convo.draft = draft
            db.commit()
            return "Please share your mobile number."

        if convo.state == "awaiting_mobile":
            draft["mobile"] = clean_text
            convo.state = "awaiting_ward_village"
            convo.draft = draft
            db.commit()
            return "Please share ward and village (example: Ward 12, Rampur)."

        if convo.state == "awaiting_ward_village":
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
                convo.state = "awaiting_public_issue_department"
                db.commit()
                return "Public Issue selected. For V1, choose:\n1. Electricity"
            if clean_text == "2":
                return "Track Complaint will be added in V2. Choose 1 for Public Issue."
            return "Invalid choice. Reply 1 for Public Issue or 2 for Track Complaint."

        if convo.state == "awaiting_public_issue_department":
            if clean_text != "1":
                return "For V1, only Electricity is supported. Reply with 1."
            convo.state = "awaiting_electricity_issue_type"
            db.commit()
            return (
                "Choose Electricity issue type:\n"
                "1. Streetlight\n2. Power cut\n3. Transformer fault\n4. Other"
            )

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

    @staticmethod
    def _split_ward_village(text: str) -> tuple[str, str]:
        parts = [chunk.strip() for chunk in text.split(",", maxsplit=1)]
        ward = parts[0] if parts else text
        village = parts[1] if len(parts) > 1 else ""
        return ward, village
