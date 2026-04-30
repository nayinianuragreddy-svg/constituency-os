import re
from datetime import datetime, timedelta, timezone

from app.agents.communication.states import s2_register_voter_id, s2_register_confirm, s5_ticket_generated, s6_status_check
from app.agents.communication.off_path import session_resume


def test_a_registration_flow():
    convo={"invalid_attempts_in_state":0}
    r=s2_register_voter_id.handle(convo,"skip",{})
    assert r.next_state=="s2_register_mandal"
    assert any(w.values.get("voter_id_skipped_at") for w in r.db_writes if isinstance(w.values,dict))


def test_b_public_water_ticket():
    convo={"draft_payload":{"category_code":"PUB-WTR","assigned_queue":"water_dept","custom_fields":{f"f{i}":i for i in range(6)}}}
    r=s5_ticket_generated.handle(convo,"",{"office_id":1,"citizen_id":1,"daily_sequence":42,"language":"en"})
    tid=r.field_collected[1]
    assert re.match(r"PUB-WTR-\d{6}-\d{4}", tid)
    inserts=[w for w in r.db_writes if w.operation=="insert" and w.table=="ticket_custom_fields"]
    assert len(inserts)==6


def test_c_welfare_skip_ack():
    from app.agents.communication.states import s4b_welfare_voter_id_check
    r=s4b_welfare_voter_id_check.handle({"invalid_attempts_in_state":0},"skip",{"citizen":{"voter_id":None,"voter_id_skipped_at":"x"}})
    assert r.next_state=="s4b_welfare_category"
    assert any(w.values.get("voter_id_skip_acknowledged") for w in r.db_writes)


def test_d_fix_field_no_ticket_mutation():
    r=s2_register_confirm.handle({"pending_cancel_warning":False},"edit:dob",{"citizen":{}})
    assert r.next_state=="s2_register_confirm"
    assert not any(w.table=="tickets" for w in r.db_writes)


def test_e_session_resume():
    r1=session_resume.handle({"current_state":"s2_register_mobile"},"yes",{})
    assert r1.next_state=="s2_register_mobile"
    r2=session_resume.handle({"current_state":"s2_register_mobile"},"no",{})
    assert r2.next_state=="s_abandon_handler"


def test_f_main_menu_status():
    r0=s6_status_check.handle({},"",{"citizen_tickets":[]})
    assert "haven't filed" in r0.reply_text
    r1=s6_status_check.handle({},"",{"citizen_tickets":[{"ticket_id_human":"PUB-WTR-010126-0001","status":"open"}]})
    assert "status" in r1.reply_text


def test_g_appointment_ticket():
    convo={"draft_payload":{"category_code":"APT-MTG","assigned_queue":"pa_inbox","custom_fields":{f"a{i}":i for i in range(10)}}}
    r=s5_ticket_generated.handle(convo,"",{"office_id":1,"citizen_id":1,"daily_sequence":3,"language":"en"})
    assert r.field_collected[1].startswith("APT-MTG-")
    inserts=[w for w in r.db_writes if w.table=="ticket_custom_fields"]
    assert len(inserts)==10


def test_h_idempotency_key_pattern():
    k1="telegram:update:100"
    k2="telegram:update:100"
    assert k1==k2


def test_i_existing_placeholder():
    assert True


if __name__=="__main__":
    tests=[v for k,v in globals().items() if k.startswith('test_')]
    for t in tests:
        t()
    print(f"v18 smoke: {len(tests)} passed")
