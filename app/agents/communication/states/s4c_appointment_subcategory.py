from app.agents.communication.types import ActionLog, Button, DbWrite, StateResult

STATE_NAME='s4c_appointment_subcategory'
CHOICES={
'meeting':('APT-MTG','pa_inbox','s4c_appointment_type'),
'event':('APT-EVT','pa_inbox','s4c_appointment_type'),
'felicitation':('APT-FEL','pa_inbox','s4c_appointment_type'),
}

def handle(conversation,message,context)->StateResult:
    text=(message or '').strip().lower()
    if text not in CHOICES:
        return StateResult(next_state=STATE_NAME,reply_text='Choose one: Meeting, Event, Felicitation.',reply_buttons=[Button('Meeting','meeting'),Button('Event','event'),Button('Felicitation','felicitation')],db_writes=[DbWrite('update','citizen_conversations',values={'invalid_attempts_in_state':conversation.get('invalid_attempts_in_state',0)+1})])
    code,queue,nxt=CHOICES[text]
    return StateResult(next_state=nxt,reply_text='Please confirm appointment type.',db_writes=[DbWrite('update','citizen_conversations',values={'invalid_attempts_in_state':0}),DbWrite('update','citizen_conversations',values={'draft_payload':{'$merge':{'category_code':code,'assigned_queue':queue}}})],agent_actions_to_log=[ActionLog('field.collected',{'field':'category_code','value':code})])
