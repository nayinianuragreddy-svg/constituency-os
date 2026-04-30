from app.agents.communication.types import Button, StateResult

STATE_NAME = "s6_status_check"


def handle(conversation, message, context) -> StateResult:
    tickets = context.get("citizen_tickets") or []
    if len(tickets) == 0:
        return StateResult(
            next_state="s6_returning_user_menu",
            reply_text="You haven't filed any complaints yet. Would you like to file one now?",
            reply_buttons=[Button("🆕 New Complaint", "new_complaint"), Button("⬅️ Main Menu", "main_menu")],
        )
    if len(tickets) == 1:
        t = tickets[0]
        return StateResult(
            next_state="s6_returning_user_menu",
            reply_text=f"Latest ticket {t.get('ticket_id_human', t.get('id'))}: status {t.get('status', 'open')}.",
            reply_buttons=[Button("⬅️ Main Menu", "main_menu")],
        )
    lines = ["I found multiple tickets. Recent ones:"]
    for t in tickets[:5]:
        lines.append(f"- {t.get('ticket_id_human', t.get('id'))}: {t.get('status', 'open')}")
    lines.append("Reply with a ticket ID for details, or choose Main Menu.")
    return StateResult(
        next_state="s6_returning_user_menu",
        reply_text="\n".join(lines),
        reply_buttons=[Button("⬅️ Main Menu", "main_menu")],
    )
