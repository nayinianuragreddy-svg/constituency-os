from app.agents.communication.types import ActionLog, Button, DbWrite, StateResult
from app.agents.communication.transitions import resolve_next

STATE_NAME = "s4a_public_subcategory"
CHOICES = {
    "water": ("PUB-WTR", "water_dept", "s4a_water_issue_type"),
    "electricity": ("PUB-ELC", "electricity_dept", "s4a_electricity_issue_type"),
    "sanitation": ("PUB-SAN", "sanitation_dept", "s4a_sanitation_issue_type"),
    "rnb": ("PUB-RNB", "rnb_dept", "s4a_rnb_issue_type"),
    "others": ("PUB-OTH", "pa_inbox", "s4a_others_title"),
}

def handle(conversation, message, context) -> StateResult:
    text=(message or "").strip().lower()
    if text not in CHOICES:
        return StateResult(next_state=STATE_NAME, reply_text="Choose one: Water, Electricity, Sanitation, R&B, Others.", reply_buttons=[Button("Water","water"),Button("Electricity","electricity"),Button("Sanitation","sanitation"),Button("R&B","rnb"),Button("Others","others")], db_writes=[DbWrite("update","citizen_conversations",values={"invalid_attempts_in_state":conversation.get("invalid_attempts_in_state",0)+1})])
    code, queue, next_state = CHOICES[text]
    return StateResult(next_state=next_state, reply_text=f"Selected {text.title()}.", db_writes=[DbWrite("update","citizen_conversations",values={"invalid_attempts_in_state":0}), DbWrite("update","citizen_conversations",values={"draft_payload":{"$merge":{"category_code":code,"assigned_queue":queue}}})], agent_actions_to_log=[ActionLog("field.collected",{"field":"category_code","value":code})])
