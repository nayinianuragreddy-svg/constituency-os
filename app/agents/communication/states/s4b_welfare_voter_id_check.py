from datetime import datetime, timezone
from app.agents.communication.types import ActionLog, Button, DbWrite, StateResult, ValidationResult
from app.agents.communication.validators import validate_voter_id

STATE_NAME='s4b_welfare_voter_id_check'

def handle(conversation,message,context)->StateResult:
    citizen=context.get('citizen') or {}
    if citizen.get('voter_id'):
        return StateResult(next_state='s4b_welfare_category',reply_text='Proceeding to welfare details.')
    text=(message or '').strip()
    if text.lower() in {'skip','na',''}:
        return StateResult(next_state='s4b_welfare_category',reply_text='Okay, proceeding without voter ID.',db_writes=[DbWrite('upsert','citizens',values={'voter_id_skip_acknowledged':True}),DbWrite('update','citizen_conversations',values={'invalid_attempts_in_state':0})],agent_actions_to_log=[ActionLog('voter_id.skipped',{'welfare_reprompt':True})],reply_buttons=[Button('Continue','continue')])
    result=validate_voter_id(text)
    if not result.is_valid:
        return StateResult(next_state=STATE_NAME,reply_text=result.error_hint,reply_buttons=[Button('Skip','skip')],db_writes=[DbWrite('update','citizen_conversations',values={'invalid_attempts_in_state':conversation.get('invalid_attempts_in_state',0)+1})])
    return StateResult(next_state='s4b_welfare_category',reply_text='Thanks. Voter ID saved.',field_collected=('voter_id',result.normalized_value),db_writes=[DbWrite('upsert','citizens',values={'voter_id':result.normalized_value,'voter_id_skipped_at':None,'voter_id_skip_acknowledged':True}),DbWrite('update','citizen_conversations',values={'invalid_attempts_in_state':0})],agent_actions_to_log=[ActionLog('field.collected',{'field':'voter_id','value':result.normalized_value})])
