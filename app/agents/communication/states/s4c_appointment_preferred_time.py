from app.agents.communication.types import ActionLog, DbWrite, StateResult, ValidationResult
from app.agents.communication.validators import validate_preferred_time
from app.agents.communication.transitions import resolve_next

STATE_NAME='s4c_appointment_preferred_time'

def handle(conversation,message,context)->StateResult:
    text=(message or '').strip()
    if text.lower() in {'skip','na',''}:
        result=ValidationResult(is_valid=True, normalized_value=None, error_hint='', code='skip')
    else:
        result=validate_preferred_time(text)
    if not result.is_valid:
        return StateResult(next_state=STATE_NAME,reply_text=result.error_hint,db_writes=[DbWrite('update','citizen_conversations',values={'invalid_attempts_in_state':conversation.get('invalid_attempts_in_state',0)+1})])
    next_state=resolve_next(STATE_NAME,result.code)
    return StateResult(next_state=next_state,reply_text='Venue/Location?',field_collected=('appointment_preferred_time',result.normalized_value),db_writes=[DbWrite('update','citizen_conversations',values={'invalid_attempts_in_state':0}),DbWrite('update','citizen_conversations',values={'draft_payload':{'$merge':{'appointment_preferred_time':result.normalized_value}}})],agent_actions_to_log=[ActionLog('field.collected',{'field':'appointment_preferred_time','value':result.normalized_value})])
