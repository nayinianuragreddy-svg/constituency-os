from app.agents.communication.types import ActionLog, Button, DbWrite, StateResult

STATE_NAME="s4b_private_subcategory"
CHOICES={
"police":("PRV-POL","police_liaison","s4b_police_nature"),
"revenue":("PRV-REV","revenue_dept","s4b_revenue_issue_type"),
"welfare":("PRV-WEL","welfare_dept","s4b_welfare_voter_id_check"),
"medical":("PRV-MED","medical_liaison","s4b_medical_patient_name"),
"education":("PRV-EDU","education_liaison","s4b_education_institution"),
"others":("PRV-OTH","pa_inbox","s4b_others_title"),
}

def handle(conversation,message,context)->StateResult:
    text=(message or '').strip().lower()
    if text not in CHOICES:
        return StateResult(next_state=STATE_NAME,reply_text='Choose one: Police, Revenue, Welfare, Medical, Education, Others.',reply_buttons=[Button('Police','police'),Button('Revenue','revenue'),Button('Welfare','welfare'),Button('Medical','medical'),Button('Education','education'),Button('Others','others')],db_writes=[DbWrite('update','citizen_conversations',values={'invalid_attempts_in_state':conversation.get('invalid_attempts_in_state',0)+1})])
    code,queue,nxt=CHOICES[text]
    return StateResult(next_state=nxt,reply_text=f'Selected {text.title()}.',db_writes=[DbWrite('update','citizen_conversations',values={'invalid_attempts_in_state':0}),DbWrite('update','citizen_conversations',values={'draft_payload':{'$merge':{'category_code':code,'assigned_queue':queue}}})],agent_actions_to_log=[ActionLog('field.collected',{'field':'category_code','value':code})])
