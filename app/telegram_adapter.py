from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol
import inspect
import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.agents.communication.router import process_message
from app.agents.communication.helpers import execute_db_write, to_inline_keyboard
from app.models import AgentAction, CitizenConversation

class TelegramSender(Protocol):
    def send_message(self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]: ...

@dataclass
class TelegramApiClient:
    bot_token: str
    timeout_seconds: float = 30.0
    @property
    def _base_url(self) -> str: return f"https://api.telegram.org/bot{self.bot_token}"
    def get_updates(self, offset: int | None = None, timeout: int = 20) -> list[dict[str, Any]]:
        payload={"timeout":timeout};
        if offset is not None: payload["offset"]=offset
        return httpx.post(f"{self._base_url}/getUpdates",json=payload,timeout=self.timeout_seconds).json().get("result",[])
    def send_message(self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
        payload={"chat_id":chat_id,"text":text}
        if reply_markup: payload["reply_markup"]=reply_markup
        r=httpx.post(f"{self._base_url}/sendMessage",json=payload,timeout=self.timeout_seconds); r.raise_for_status(); return r.json()

def process_incoming_update(db: Session, update: dict[str, Any], sender: TelegramSender) -> dict[str, Any]:
    update_id=update.get("update_id")
    if update_id is None: return {"status":"ignored","reason":"missing_update_id"}
    idem=f"telegram:update:{update_id}"
    action=AgentAction(idempotency_key=idem,channel="telegram",action_type="incoming_update",status="processing",payload=update)
    db.add(action)
    try: db.flush()
    except IntegrityError:
        db.rollback(); old=db.query(AgentAction).filter(AgentAction.idempotency_key==idem).first();
        if old and old.status=="processed": return {"status":"duplicate_skipped","update_id":update_id}

    msg=update.get("message") or {}
    cb=update.get("callback_query") or {}
    if cb:
        msg=cb.get("message") or {}
        text=(cb.get("data") or "").strip()
    else:
        text=(msg.get("text") or "").strip()
    chat_id=((msg.get("chat") or {}).get("id"))
    if not chat_id: return {"status":"ignored","reason":"unsupported_update"}

    convo=db.query(CitizenConversation).filter(CitizenConversation.telegram_chat_id==str(chat_id)).first()
    if convo is None:
        convo=CitizenConversation(telegram_chat_id=str(chat_id), current_state="s0_identity_check", draft_payload={})
        db.add(convo); db.flush()

    media=None
    if msg.get("photo"): media={"file_id":msg["photo"][-1]["file_id"],"kind":"photo"}
    elif msg.get("document"): media={"file_id":msg["document"]["file_id"],"kind":"document"}
    elif msg.get("voice"): media={"file_id":msg["voice"]["file_id"],"kind":"voice"}
    if media:
        db.execute(__import__('sqlalchemy').text("INSERT INTO media_uploads (office_id,citizen_id,telegram_file_id,file_kind) VALUES (1,:citizen_id,:fid,:kind) ON CONFLICT (office_id,telegram_file_id) DO NOTHING"), {"citizen_id":getattr(convo,'citizen_id',None),"fid":media['file_id'],"kind":media['kind']})

    context={"telegram_chat_id":str(chat_id),"office_id":1,"idempotency_key":idem,"media":media or {},"media_file_id":(media or {}).get('file_id'),"llm_enabled":True}
    context["db_write"]=lambda w: execute_db_write(db,w,context)
    context["log_action"]=lambda a: db.add(AgentAction(idempotency_key=f"{idem}:{a['action_type']}:{__import__('uuid').uuid4().hex}",channel="internal",action_type=a["action_type"],status="processed",payload=a,response_payload={}))
    context["persist_state"]=lambda s: setattr(convo,'current_state',s)
    bucket={}
    context["send_reply"]=lambda t,b: bucket.update({"text":t or "","buttons":b})

    result=process_message({"current_state":convo.current_state,"invalid_attempts_in_state":0,"draft_payload":getattr(convo,'draft_payload',{}) or {}},text,context)
    convo.current_state=result.next_state
    db.commit()
    markup=to_inline_keyboard(bucket.get("buttons"))
    send_text = bucket.get("text") or result.reply_text or ""
    send_params = inspect.signature(sender.send_message).parameters
    if markup is not None and "reply_markup" in send_params:
        send_result = sender.send_message(str(chat_id), send_text, reply_markup=markup)
    else:
        send_result = sender.send_message(str(chat_id), send_text)
    action.status="processed"; action.response_payload={"send_result":send_result}; db.commit()
    return {"status":"processed","next_state":result.next_state,"update_id":update_id}
