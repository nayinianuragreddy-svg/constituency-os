"""
Constituency OS — Admin Activity View (v2, matched to actual schema)
====================================================================

Read-only HTML page for live demos of the V1 office loop.

Drop this file into `app/` and register the router in `app/main.py`:

    from app.admin_view import router as admin_router
    app.include_router(admin_router)

Then in .env:

    ADMIN_VIEW_ENABLED=true

Open: http://localhost:8000/admin/activity

This version is matched to the actual model column names used in
`app/models.py`. It shows:

    - Counts banner (citizens, tickets, conversations, actions, alerts)
    - Citizens (latest 10)
    - Tickets (latest 10)
    - Live Conversations (latest 10) — the state machine of in-flight chats
    - Officer Messages (latest 10) — escalations to government officers
    - Agent Actions (latest 20) — audit trail
    - Agent Alerts (latest 10) — Master's queue

Read-only. No mutations. V1.5 internal demo only.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from html import escape
from typing import Any, Iterable

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app import models


router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_db() -> Iterable[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _require_enabled() -> None:
    if os.getenv("ADMIN_VIEW_ENABLED", "").lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=404, detail="Not found")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_query(db: Session, model_name: str, order_attr: str, limit: int) -> list[Any]:
    model = getattr(models, model_name, None)
    if model is None:
        return []
    order_col = getattr(model, order_attr, None) or getattr(model, "id", None)
    if order_col is None:
        return []
    try:
        return db.query(model).order_by(order_col.desc()).limit(limit).all()
    except Exception:
        return []


def _val(obj: Any, *names: str, default: str = "") -> str:
    for n in names:
        if hasattr(obj, n):
            v = getattr(obj, n)
            if v is None:
                continue
            if isinstance(v, datetime):
                return v.strftime("%Y-%m-%d %H:%M:%S")
            return str(v)
    return default


def _val_json(obj: Any, *names: str, default: str = "") -> str:
    """Pluck a JSON column and return a compact one-line string."""
    for n in names:
        if hasattr(obj, n):
            v = getattr(obj, n)
            if v is None or v == {} or v == "":
                continue
            try:
                if isinstance(v, (dict, list)):
                    return json.dumps(v, ensure_ascii=False, separators=(", ", ": "))
                return str(v)
            except Exception:
                return str(v)
    return default


def _truncate(s: str, n: int = 80) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def _row(cells: list[str]) -> str:
    return "<tr>" + "".join(f"<td>{escape(c)}</td>" for c in cells) + "</tr>"


def _table(headers: list[str], rows: list[str], empty_msg: str) -> str:
    if not rows:
        return f'<div class="empty">{escape(empty_msg)}</div>'
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    return (
        '<div class="table-wrap"><table>'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )


# ---------------------------------------------------------------------------
# Section renderers (matched to actual schema)
# ---------------------------------------------------------------------------

def render_citizens(db: Session) -> str:
    rows_obj = _safe_query(db, "Citizen", "created_at", 10)
    rows = [
        _row([
            _val(c, "id"),
            _val(c, "name"),
            _val(c, "mobile"),
            _val(c, "ward"),
            _val(c, "village"),
            _val(c, "created_at"),
        ])
        for c in rows_obj
    ]
    return _table(
        ["ID", "Name", "Mobile", "Ward", "Village", "Registered"],
        rows,
        "No citizens registered yet. Send 'hi' to the Telegram bot.",
    )


def render_tickets(db: Session) -> str:
    rows_obj = _safe_query(db, "Ticket", "created_at", 10)
    rows = [
        _row([
            _val(t, "id"),
            _val(t, "citizen_id"),
            _val(t, "category"),
            _val(t, "subcategory"),
            _val(t, "status"),
            _val(t, "department"),
            _val(t, "urgency"),
            _val(t, "created_at"),
        ])
        for t in rows_obj
    ]
    return _table(
        ["ID", "Citizen", "Category", "Issue", "Status", "Department", "Urgency", "Created"],
        rows,
        "No tickets yet.",
    )


def render_conversations(db: Session) -> str:
    rows_obj = _safe_query(db, "CitizenConversation", "updated_at", 10)
    rows = [
        _row([
            _val(c, "id"),
            _val(c, "telegram_chat_id"),
            _val(c, "state"),
            _val(c, "citizen_id", default="—"),
            _truncate(_val_json(c, "draft"), 70),
            _val(c, "updated_at"),
        ])
        for c in rows_obj
    ]
    return _table(
        ["ID", "Telegram Chat", "State", "Citizen", "Draft", "Updated"],
        rows,
        "No active conversations. Open Telegram and message the bot.",
    )


def render_officer_messages(db: Session) -> str:
    rows_obj = _safe_query(db, "OfficerMessage", "created_at", 10)
    rows = [
        _row([
            _val(m, "id"),
            _val(m, "ticket_id"),
            _val(m, "officer_mapping_id"),
            _val(m, "direction"),
            _truncate(_val(m, "message_text"), 80),
            _val(m, "status"),
            _val(m, "created_at"),
        ])
        for m in rows_obj
    ]
    return _table(
        ["ID", "Ticket", "Officer Map", "Direction", "Message", "Status", "Time"],
        rows,
        "No officer messages yet. Trigger the department queue to see escalations.",
    )


def render_agent_actions(db: Session) -> str:
    rows_obj = _safe_query(db, "AgentAction", "created_at", 20)
    rows = [
        _row([
            _val(a, "id"),
            _val(a, "channel"),
            _val(a, "action_type"),
            _truncate(_val(a, "idempotency_key"), 28),
            _val(a, "status"),
            _val(a, "created_at"),
        ])
        for a in rows_obj
    ]
    return _table(
        ["ID", "Channel", "Action Type", "Idempotency Key", "Status", "Time"],
        rows,
        "No agent actions logged yet.",
    )


def render_agent_alerts(db: Session) -> str:
    rows_obj = _safe_query(db, "AgentAlert", "created_at", 10)
    rows = [
        _row([
            _val(a, "id"),
            _val(a, "source_agent"),
            _val(a, "alert_type"),
            _truncate(_val_json(a, "payload"), 70),
            _val(a, "status"),
            _val(a, "created_at"),
        ])
        for a in rows_obj
    ]
    return _table(
        ["ID", "Source Agent", "Alert Type", "Payload", "Status", "Created"],
        rows,
        "No alerts in queue. Master is idle.",
    )


# ---------------------------------------------------------------------------
# Counts banner
# ---------------------------------------------------------------------------

def render_counts(db: Session) -> str:
    def count_of(model_name: str) -> str:
        model = getattr(models, model_name, None)
        if model is None:
            return "—"
        try:
            return str(db.query(model).count())
        except Exception:
            return "—"

    pairs = [
        ("Citizens", count_of("Citizen")),
        ("Tickets", count_of("Ticket")),
        ("Conversations", count_of("CitizenConversation")),
        ("Agent Actions", count_of("AgentAction")),
        ("Alerts", count_of("AgentAlert")),
    ]
    cells = "".join(
        f'<div class="stat"><div class="stat-num">{escape(v)}</div>'
        f'<div class="stat-label">{escape(k)}</div></div>'
        for k, v in pairs
    )
    return f'<div class="stats">{cells}</div>'


# ---------------------------------------------------------------------------
# Page template
# ---------------------------------------------------------------------------

PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="3">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Constituency OS — Live Activity</title>
<style>
  :root {{
    --bg:        #F5F1EA;
    --card:      #FFFFFF;
    --navy:      #1F2D3D;
    --teal:      #4A8589;
    --gold:      #B5946A;
    --body:      #3F4A55;
    --muted:     #8B9099;
    --line:      #D9D2C5;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--body);
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 28px 36px 60px;
  }}
  header {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    border-bottom: 1px solid var(--line);
    padding-bottom: 14px;
    margin-bottom: 24px;
  }}
  .brand {{
    font-size: 11px; font-weight: 700; letter-spacing: 5px; color: var(--gold);
  }}
  h1 {{ font-size: 26px; font-weight: 700; color: var(--navy); margin: 4px 0 0 0; }}
  .meta {{ font-size: 12px; color: var(--muted); text-align: right; }}
  .meta strong {{ color: var(--navy); font-weight: 600; }}
  .live-dot {{
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    background: var(--teal); margin-right: 6px;
    animation: pulse 1.5s ease-in-out infinite; vertical-align: middle;
  }}
  @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.35; }} }}

  .stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 28px; }}
  .stat {{
    background: var(--card); border: 1px solid var(--line);
    border-top: 3px solid var(--gold); padding: 16px 18px;
  }}
  .stat-num {{ font-size: 30px; font-weight: 700; color: var(--navy); font-variant-numeric: tabular-nums; }}
  .stat-label {{ font-size: 10px; letter-spacing: 3px; color: var(--muted); text-transform: uppercase; margin-top: 4px; }}

  section {{ margin-bottom: 28px; }}
  .section-head {{ display: flex; align-items: baseline; gap: 12px; margin-bottom: 10px; }}
  h2 {{ font-size: 12px; font-weight: 700; letter-spacing: 5px; color: var(--gold); margin: 0; text-transform: uppercase; }}
  .section-sub {{ font-size: 13px; color: var(--muted); font-style: italic; }}

  .table-wrap {{ background: var(--card); border: 1px solid var(--line); overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead th {{
    text-align: left; font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
    font-weight: 700; color: var(--muted);
    padding: 10px 14px; border-bottom: 1px solid var(--line); background: #FBF8F2;
  }}
  tbody td {{ padding: 10px 14px; border-bottom: 1px solid var(--line); color: var(--navy); font-variant-numeric: tabular-nums; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  tbody tr:hover {{ background: #FBF8F2; }}

  .empty {{
    background: var(--card); border: 1px dashed var(--line);
    padding: 18px; color: var(--muted); font-style: italic; text-align: center;
  }}

  footer {{
    margin-top: 36px; padding-top: 14px; border-top: 1px solid var(--line);
    font-size: 11px; color: var(--muted); display: flex; justify-content: space-between;
  }}
  footer .right {{ letter-spacing: 4px; font-weight: 700; color: var(--gold); }}
</style>
</head>
<body>

<header>
  <div>
    <div class="brand">CONSTITUENCY OS</div>
    <h1>Live Office Activity</h1>
  </div>
  <div class="meta">
    <span class="live-dot"></span><strong>Live</strong> — auto-refresh every 3s<br>
    Snapshot: {snapshot_time}
  </div>
</header>

{counts}

<section>
  <div class="section-head">
    <h2>Citizens</h2>
    <span class="section-sub">Latest 10 registered through the office.</span>
  </div>
  {citizens}
</section>

<section>
  <div class="section-head">
    <h2>Tickets</h2>
    <span class="section-sub">Latest 10 complaints captured by the system.</span>
  </div>
  {tickets}
</section>

<section>
  <div class="section-head">
    <h2>Live Conversations</h2>
    <span class="section-sub">In-flight chats. Watch the state machine move as citizens reply on Telegram.</span>
  </div>
  {conversations}
</section>

<section>
  <div class="section-head">
    <h2>Officer Messages</h2>
    <span class="section-sub">Escalations and replies on the department coordination loop.</span>
  </div>
  {officer_messages}
</section>

<section>
  <div class="section-head">
    <h2>Agent Actions</h2>
    <span class="section-sub">Latest 20 actions across all agents. The audit trail.</span>
  </div>
  {actions}
</section>

<section>
  <div class="section-head">
    <h2>Master Alert Queue</h2>
    <span class="section-sub">Alerts produced by other agents. Master polls and consumes.</span>
  </div>
  {alerts}
</section>

<footer>
  <div>Read-only view. Set ADMIN_VIEW_ENABLED=false to disable. V1.5 internal demo surface.</div>
  <div class="right">CONSTITUENCY OS</div>
</footer>

</body>
</html>
"""


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get(
    "/activity",
    response_class=HTMLResponse,
    dependencies=[Depends(_require_enabled)],
    summary="Live read-only view of the office loop. Internal demo only.",
)
def activity(db: Session = Depends(get_db)) -> HTMLResponse:
    snapshot = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    html = PAGE_TEMPLATE.format(
        snapshot_time=escape(snapshot),
        counts=render_counts(db),
        citizens=render_citizens(db),
        tickets=render_tickets(db),
        conversations=render_conversations(db),
        officer_messages=render_officer_messages(db),
        actions=render_agent_actions(db),
        alerts=render_agent_alerts(db),
    )
    return HTMLResponse(content=html)
