from typing import Any

from fastapi import FastAPI, HTTPException

from app.contracts import (
    CitizenMessageRequest,
    CitizenMessageResponse,
    HumanApprovalRequest,
    OfficerReplyRequest,
    RuntimeRequest,
    RuntimeResponse,
)
from app.db import SessionLocal, init_db
from app.runtime import RuntimeOrchestrator
from app.telegram_adapter import TelegramApiClient, process_incoming_update
from app.tools import ToolGateway
from app.config import TELEGRAM_BOT_TOKEN
from app.v1 import (
    approve_human_approval,
    consume_master_alerts,
    handle_citizen_message,
    process_department_queue,
    simulate_officer_reply,
)

app = FastAPI(title="Constituency OS V1", version="0.2.0")
runtime = RuntimeOrchestrator()
tools = ToolGateway()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runtime/dispatch", response_model=RuntimeResponse)
def dispatch_runtime(request: RuntimeRequest) -> RuntimeResponse:
    return runtime.dispatch(request)


@app.post("/v1/citizen/message", response_model=CitizenMessageResponse)
def citizen_message(request: CitizenMessageRequest) -> CitizenMessageResponse:
    db = SessionLocal()
    try:
        reply = handle_citizen_message(db, request.telegram_chat_id, request.text)
        return CitizenMessageResponse(reply=reply)
    finally:
        db.close()


@app.post("/v1/department/process")
def process_department() -> dict[str, list[int]]:
    db = SessionLocal()
    try:
        processed = process_department_queue(db, tools=tools)
        return {"processed_ticket_ids": processed}
    finally:
        db.close()


@app.post("/v1/officer/reply")
def officer_reply(request: OfficerReplyRequest) -> dict[str, int]:
    db = SessionLocal()
    try:
        approval_id = simulate_officer_reply(db, request.ticket_id, request.reply_text)
        return {"human_approval_id": approval_id}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        db.close()


@app.post("/v1/human-approvals/{approval_id}/approve")
def approve(approval_id: int, request: HumanApprovalRequest) -> dict[str, str]:
    db = SessionLocal()
    try:
        result = approve_human_approval(
            db,
            approval_id=approval_id,
            approved_by=request.approved_by,
            tools=tools,
        )
        return {"result": result}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        db.close()


@app.post("/v1/master/consume")
def master_consume() -> dict[str, list[dict]]:
    db = SessionLocal()
    try:
        alerts = consume_master_alerts(db)
        return {"alerts": alerts}
    finally:
        db.close()


@app.post("/v1/telegram/webhook")
def telegram_webhook(update: dict[str, Any]) -> dict[str, Any]:
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="TELEGRAM_BOT_TOKEN is missing. Set it before using Telegram webhook mode.",
        )

    db = SessionLocal()
    try:
        sender = TelegramApiClient(bot_token=TELEGRAM_BOT_TOKEN)
        return process_incoming_update(db=db, update=update, sender=sender)
    finally:
        db.close()
