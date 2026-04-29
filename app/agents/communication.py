import re
import unicodedata
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.base import StatelessAgent
from app.contracts import AgentMessage
from app.core.llm import llm_call, load_prompt
from app.models import AgentAction, Citizen, CitizenConversation, Ticket, TicketUpdate


class CommunicationAgent(StatelessAgent):
    GREETING_WORDS = {"hi", "hello", "hey", "namaste", "namaskaram"}
    WELCOME_BACK_MENU = "Welcome back, {name}. What would you like to do today?\n1. Public Issue\n2. Track Complaint"
    MAIN_MENU = "Menu:\n1. Public Issue\n2. Track Complaint"
    INTENT_JSON_SCHEMA = {
        "language": "en|te|hi|mixed",
        "intent": "greet|provide_info|provide_complaint|fix_earlier|ask_status|abandon|unclear",
        "extracted": {"name": "string|null", "mobile": "string|null", "ward": "string|null", "issue_text": "string|null", "fix_field": "name|mobile|ward|issue|null"},
        "confidence": "float",
    }
    llm_provider_call = None

    def process(self, message: AgentMessage) -> AgentMessage:
        return AgentMessage(
            sender=self.name,
            receiver=message.receiver,
            body=f"communication_dispatch::{message.body}",
        )

    def handle_citizen_message(self, db: Session, telegram_chat_id: str, text: str) -> str:
        clean_text = text.strip()
        citizen = db.query(Citizen).filter(Citizen.telegram_chat_id == telegram_chat_id).first()
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
            if citizen:
                convo.citizen_id = citizen.id
                convo.state = "awaiting_main_menu"
                db.commit()
                return self.WELCOME_BACK_MENU.format(name=citizen.name)
            db.commit()
            return (
                "Namaskaram. This is the digital assistant for the MLA office. "
                "You can use this chat to raise public issues and track complaints. "
                "Before we continue, I need to register your details once. "
                "Please share your full name."
            )

        intent_data = self._route_intent(db=db, convo=convo, citizen=citizen, telegram_chat_id=telegram_chat_id, text=clean_text)

        if citizen and convo.state in {"welcomed", "awaiting_name", "awaiting_mobile", "awaiting_ward", "awaiting_ward_village"}:
            convo.citizen_id = citizen.id
            convo.state = "awaiting_main_menu"
            convo.draft = {}
            db.commit()
            return self.WELCOME_BACK_MENU.format(name=citizen.name)

        command = clean_text.lower()
        if command == "restart":
            if citizen:
                convo.citizen_id = citizen.id
                convo.state = "awaiting_main_menu"
                convo.draft = {}
                db.commit()
                return self.WELCOME_BACK_MENU.format(name=citizen.name)
            convo.state = "awaiting_name"
            convo.draft = {}
            db.commit()
            return "Registration restarted. Please share your full name."

        if command in {"back", "go back", "edit"}:
            back_reply = self._go_back_one_step(convo)
            db.commit()
            return back_reply

        draft = dict(convo.draft or {})
        state_intent_override = None

        if intent_data and intent_data.get("intent") == "fix_earlier":
            state_intent_override, direct_reply = self._apply_fix_earlier(convo=convo, fix_field=(intent_data.get("extracted") or {}).get("fix_field"))
            if direct_reply:
                db.commit()
                return self._draft_reply(db, telegram_chat_id, convo, state_intent_override, direct_reply, clean_text, citizen)
        elif intent_data and intent_data.get("intent") == "ask_status":
            latest = None
            if convo.citizen_id:
                latest = db.query(Ticket).filter(Ticket.citizen_id == convo.citizen_id).order_by(Ticket.id.desc()).first()
            if latest is None:
                reply = "I could not find a previous complaint yet. Please choose 1 to raise a Public Issue."
            else:
                reply = f"Latest complaint status for Ticket ID {latest.id}: {latest.status}."
            return self._draft_reply(db, telegram_chat_id, convo, "status_reply", reply, clean_text, citizen)
        elif intent_data and intent_data.get("intent") == "abandon":
            if citizen:
                convo.state = "awaiting_main_menu"
                convo.draft = {}
                db.commit()
                return self._draft_reply(db, telegram_chat_id, convo, "show_main_menu", self.WELCOME_BACK_MENU.format(name=citizen.name), clean_text, citizen)
            reply = "Would you like to restart registration? Reply restart."
            return self._draft_reply(db, telegram_chat_id, convo, "ask_clarifying_question", reply, clean_text, citizen)

        if convo.state == "welcomed":
            convo.state = "awaiting_name"
            db.commit()
            return self.handle_citizen_message(db=db, telegram_chat_id=telegram_chat_id, text=clean_text)

        if convo.state == "awaiting_name":
            clean_text = self._candidate_or_text(intent_data, clean_text, "name")
            if not self._is_valid_name(clean_text):
                return self._draft_reply(db, telegram_chat_id, convo, "invalid_name", "Please share your full name, not a greeting. Example: Asha Singh.", clean_text, citizen)
            draft["name"] = clean_text
            convo.state = "awaiting_mobile"
            convo.draft = draft
            db.commit()
            return self._draft_reply(db, telegram_chat_id, convo, "ask_mobile", "Please share your mobile number.", clean_text, citizen)

        if convo.state == "awaiting_mobile":
            clean_text = self._candidate_or_text(intent_data, clean_text, "mobile")
            if not self._is_valid_mobile(clean_text):
                return self._draft_reply(db, telegram_chat_id, convo, "invalid_mobile", "Please share a valid 10-digit mobile number.", clean_text, citizen)
            draft["mobile"] = self._digits_only(clean_text)
            convo.state = "awaiting_ward"
            convo.draft = draft
            db.commit()
            return self._draft_reply(db, telegram_chat_id, convo, "ask_ward", "Please share ward and village/locality. Example: Ward 12, Rampur.", clean_text, citizen)

        if convo.state in {"awaiting_ward", "awaiting_ward_village"}:
            clean_text = self._candidate_or_text(intent_data, clean_text, "ward")
            if not self._is_valid_ward(clean_text):
                return self._draft_reply(db, telegram_chat_id, convo, "invalid_ward", "Please share both ward number and village/locality. Example: Ward 12, Rampur.", clean_text, citizen)
            ward, village = self._split_ward_village(clean_text)
            citizen = db.query(Citizen).filter(Citizen.telegram_chat_id == telegram_chat_id).first()
            if citizen is None:
                citizen = Citizen(
                    name=draft["name"],
                    mobile=draft["mobile"],
                    ward=ward,
                    village=village,
                    location_text=clean_text,
                    telegram_chat_id=telegram_chat_id,
                )
                db.add(citizen)
                try:
                    db.flush()
                except IntegrityError:
                    db.rollback()
                    citizen = db.query(Citizen).filter(Citizen.telegram_chat_id == telegram_chat_id).first()
                    convo = (
                        db.query(CitizenConversation)
                        .filter(CitizenConversation.telegram_chat_id == telegram_chat_id)
                        .first()
                    )
                    if citizen is not None and convo is not None:
                        convo.citizen_id = citizen.id
                        convo.state = "awaiting_main_menu"
                        convo.draft = {}
                        db.commit()
                        return self.WELCOME_BACK_MENU.format(name=citizen.name)
                    raise
            convo.citizen_id = citizen.id
            draft["ward"] = ward
            draft["village"] = village
            convo.draft = draft
            convo.state = "awaiting_main_menu"
            db.commit()
            return self._draft_reply(db, telegram_chat_id, convo, "show_main_menu", self.MAIN_MENU, clean_text, citizen)

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
            return self._draft_reply(db, telegram_chat_id, convo, "ticket_created", f"Complaint registered. Ticket ID: {ticket.id}", clean_text, citizen, {"ticket_id": ticket.id})

        convo.state = "awaiting_main_menu"
        db.commit()
        return self.MAIN_MENU

    def _route_intent(self, db: Session, convo: CitizenConversation, citizen: Citizen | None, telegram_chat_id: str, text: str) -> dict[str, Any] | None:
        res = llm_call(user_prompt=text, system_prompt=load_prompt("communication_intent_router"), response_format="json", json_schema=self.INTENT_JSON_SCHEMA, metadata={"agent_name": "communication", "purpose": "intent_router", "office_id": 1, "citizen_id": citizen.id if citizen else None, "ticket_id": None, "idempotency_key": f"comm:intent:{telegram_chat_id}:{convo.id}:{convo.state}"}, provider_call=self.llm_provider_call)
        data = res.parsed_json if res.success and isinstance(res.parsed_json, dict) else None
        if not data or float(data.get("confidence", 0.0)) < 0.7:
            return None
        self._record_llm_action(db, f"llm:communication:intent:{telegram_chat_id}:{convo.id}:{convo.state}", "intent_router", data)
        return data

    def _draft_reply(self, db: Session, telegram_chat_id: str, convo: CitizenConversation, state_intent: str, fallback_text: str, user_message: str, citizen: Citizen | None, extra_data: dict[str, Any] | None = None) -> str:
        draft = self.draft_reply(state_intent=state_intent, citizen_context={"state": convo.state, "citizen_name": citizen.name if citizen else None, "user_message": user_message}, extra_data=extra_data, db=db, idempotency_key=f"llm:communication:reply:{telegram_chat_id}:{convo.id}:{state_intent}")
        return draft or fallback_text

    def draft_reply(self, state_intent: str, citizen_context: dict, extra_data: dict | None = None, db: Session | None = None, idempotency_key: str | None = None) -> str:
        payload = {"state_intent": state_intent, "citizen_context": citizen_context, "extra_data": extra_data or {}}
        res = llm_call(user_prompt=str(payload), system_prompt=load_prompt("communication_reply_drafter"), metadata={"agent_name": "communication", "purpose": "reply_drafter", "office_id": 1, "citizen_id": None, "ticket_id": (extra_data or {}).get("ticket_id"), "idempotency_key": idempotency_key}, provider_call=self.llm_provider_call)
        if res.success and not res.fallback_used and res.text.strip():
            if db and idempotency_key:
                self._record_llm_action(db, idempotency_key, "reply_drafter", {"state_intent": state_intent})
            return res.text.strip()
        return ""

    def _record_llm_action(self, db: Session, idempotency_key: str, purpose: str, payload: dict[str, Any]) -> None:
        if db.query(AgentAction).filter(AgentAction.idempotency_key == idempotency_key).first():
            return
        db.add(AgentAction(idempotency_key=idempotency_key, channel="internal", action_type="llm.call", status="completed", payload={"agent_name": "communication", "purpose": purpose, "parsed_json": payload}, response_payload={}))
        db.flush()

    def _candidate_or_text(self, intent_data: dict[str, Any] | None, original_text: str, field: str) -> str:
        if not intent_data:
            return original_text
        extracted = (intent_data.get("extracted") or {}).get(field)
        if not extracted:
            return original_text
        if self._contains_substring(original_text, extracted):
            return extracted
        return original_text

    def _apply_fix_earlier(self, convo: CitizenConversation, fix_field: str | None) -> tuple[str, str | None]:
        allowed_states = {"awaiting_name", "awaiting_mobile", "awaiting_ward", "awaiting_issue_type", "awaiting_description", "awaiting_confirmation", "awaiting_electricity_issue_type"}
        if convo.state == "awaiting_main_menu":
            return "ask_clarifying_question", None
        if convo.state not in allowed_states:
            return "fix_unavailable_ticket_created", "Changes are not available after ticket creation. Please ask staff to update your details."
        mapping = {"name": "awaiting_name", "mobile": "awaiting_mobile", "ward": "awaiting_ward", "issue": "awaiting_description"}
        if fix_field not in mapping:
            return "ask_clarifying_question", "Please tell me what to fix: name, mobile, ward, or issue."
        convo.state = mapping[fix_field]
        return "ask_clarifying_question", None

    @staticmethod
    def _contains_substring(message: str, candidate: str) -> bool:
        def norm(x: str) -> str:
            return "".join(ch for ch in unicodedata.normalize("NFKD", x.casefold()) if not unicodedata.combining(ch))
        return norm(candidate) in norm(message)

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
        parsed = CommunicationAgent._parse_ward_village(candidate)
        if parsed is None:
            return False
        ward_number, locality = parsed
        if not ward_number or not locality:
            return False
        words = re.findall(r"[A-Za-z]+", locality.lower())
        if not words:
            return False
        if max(len(word) for word in words) < 3:
            return False
        unique_words = {word for word in words}
        if len(unique_words) == 1 and len(words) > 1:
            return False
        return True

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
        parsed = CommunicationAgent._parse_ward_village(text.strip())
        if parsed is None:
            return text.strip(), ""
        ward_number, village = parsed
        return f"Ward {ward_number}", village

    @staticmethod
    def _parse_ward_village(text: str) -> tuple[str, str] | None:
        candidate = re.sub(r"\s+", " ", text.strip())
        match = re.match(
            r"^(?:ward\s+)?(?P<ward>\d{1,3})(?:\s*,?\s+)(?P<locality>[A-Za-z][A-Za-z\s-]*)$",
            candidate,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        return match.group("ward"), match.group("locality").strip()
