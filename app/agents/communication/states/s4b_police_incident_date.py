from app.agents.communication.types import ActionLog, DbWrite, StateResult
from app.agents.communication.validators import validate_incident_date
from app.agents.communication.transitions import resolve_next

STATE_NAME='s4b_police_incident_date'

def handle(conversation,message,context)->StateResult:
    text=(message or '').strip()
    result=validate_incident_date(text)
    if not result.is_valid:
        return StateResult(next_state=STATE_NAME,reply_text=result.error_hint,db_writes=[DbWrite('update','citizen_conversations',values={'invalid_attempts_in_state':conversation.get('invalid_attempts_in_state',0)+1})])
    next_state=resolve_next(STATE_NAME,result.code)
    return StateResult(next_state=next_state,reply_text='Police station name?',field_collected=('police_incident_date',result.normalized_value),db_writes=[DbWrite('update','citizen_conversations',values={'invalid_attempts_in_state':0}),DbWrite('update','citizen_conversations',values={'draft_payload':{'$merge':{'police_incident_date':result.normalized_value}}})],agent_actions_to_log=[ActionLog('field.collected',{'field':'police_incident_date','value':result.normalized_value})])
