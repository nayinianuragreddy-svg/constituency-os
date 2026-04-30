"""Explicit branching transition table for communication V1.8 state machine."""

TRANSITIONS: dict[tuple[str, str], str] = {
    # Stage 0
    ("s0_identity_check", "known_complete"): "s6_returning_user_menu",
    ("s0_identity_check", "known_incomplete"): "<resumed_register_state>",
    ("s0_identity_check", "unknown"): "s1_greet",

    # Stage 1
    ("s1_greet", "valid"): "s1_language_select",
    ("s1_language_select", "valid"): "s2_register_name",
    ("s1_language_select", "invalid"): "s1_language_select",

    # Stage 2
    ("s2_register_name", "valid"): "s2_register_dob",
    ("s2_register_name", "invalid"): "s2_register_name",
    ("s2_register_dob", "valid"): "s2_register_mobile",
    ("s2_register_dob", "invalid"): "s2_register_dob",
    ("s2_register_mobile", "valid"): "s2_register_voter_id",
    ("s2_register_mobile", "invalid"): "s2_register_mobile",
    ("s2_register_voter_id", "valid"): "s2_register_mandal",
    ("s2_register_voter_id", "skip"): "s2_register_mandal",
    ("s2_register_voter_id", "invalid"): "s2_register_voter_id",
    ("s2_register_mandal", "valid"): "s2_register_village_ward",
    ("s2_register_mandal", "invalid"): "s2_register_mandal",
    ("s2_register_village_ward", "valid"): "s2_register_ward_number",
    ("s2_register_village_ward", "invalid"): "s2_register_village_ward",
    ("s2_register_ward_number", "valid"): "s2_register_geo",
    ("s2_register_ward_number", "invalid"): "s2_register_ward_number",
    ("s2_register_geo", "valid"): "s2_register_confirm",
    ("s2_register_geo", "skip"): "s2_register_confirm",
    ("s2_register_geo", "invalid"): "s2_register_geo",
    ("s2_register_confirm", "confirm"): "s2_register_done",
    ("s2_register_confirm", "edit"): "<dispatched via fix_field>",
    ("s2_register_confirm", "cancel"): "s1_greet",
    ("s2_register_done", "valid"): "s3_category_select",

    # Stage 3
    ("s3_category_select", "public"): "s4a_public_subcategory",
    ("s3_category_select", "private"): "s4b_private_subcategory",
    ("s3_category_select", "appointment"): "s4c_appointment_subcategory",
    ("s3_category_select", "invalid"): "s3_category_select",

    # Stage 4A branch select
    ("s4a_public_subcategory", "water"): "s4a_water_issue_type",
    ("s4a_public_subcategory", "electricity"): "s4a_electricity_issue_type",
    ("s4a_public_subcategory", "sanitation"): "s4a_sanitation_issue_type",
    ("s4a_public_subcategory", "rnb"): "s4a_rnb_issue_type",
    ("s4a_public_subcategory", "others"): "s4a_others_title",
    ("s4a_public_subcategory", "invalid"): "s4a_public_subcategory",

    # 4A water
    ("s4a_water_issue_type", "valid"): "s4a_water_location",
    ("s4a_water_location", "valid"): "s4a_water_duration",
    ("s4a_water_duration", "valid"): "s4a_water_households",
    ("s4a_water_households", "valid"): "s4a_water_prev_complaint",
    ("s4a_water_prev_complaint", "valid"): "s4a_water_description",
    ("s4a_water_prev_complaint", "skip"): "s4a_water_description",
    ("s4a_water_description", "valid"): "s5_complaint_confirm",
    ("s4a_water_description", "skip"): "s5_complaint_confirm",

    # 4A electricity
    ("s4a_electricity_issue_type", "valid"): "s4a_electricity_location",
    ("s4a_electricity_location", "valid"): "s4a_electricity_duration",
    ("s4a_electricity_duration", "valid"): "s4a_electricity_households",
    ("s4a_electricity_households", "valid"): "s4a_electricity_discom_ref",
    ("s4a_electricity_discom_ref", "valid"): "s4a_electricity_description",
    ("s4a_electricity_discom_ref", "skip"): "s4a_electricity_description",
    ("s4a_electricity_description", "valid"): "s5_complaint_confirm",
    ("s4a_electricity_description", "skip"): "s5_complaint_confirm",

    # 4A sanitation
    ("s4a_sanitation_issue_type", "valid"): "s4a_sanitation_location",
    ("s4a_sanitation_location", "valid"): "s4a_sanitation_duration",
    ("s4a_sanitation_duration", "valid"): "s4a_sanitation_scale",
    ("s4a_sanitation_scale", "valid"): "s4a_sanitation_photo",
    ("s4a_sanitation_photo", "valid"): "s4a_sanitation_description",
    ("s4a_sanitation_photo", "skip"): "s4a_sanitation_description",
    ("s4a_sanitation_description", "valid"): "s5_complaint_confirm",
    ("s4a_sanitation_description", "skip"): "s5_complaint_confirm",

    # 4A rnb
    ("s4a_rnb_issue_type", "valid"): "s4a_rnb_location",
    ("s4a_rnb_location", "valid"): "s4a_rnb_severity",
    ("s4a_rnb_severity", "valid"): "s4a_rnb_duration",
    ("s4a_rnb_duration", "valid"): "s4a_rnb_photo",
    ("s4a_rnb_photo", "valid"): "s4a_rnb_description",
    ("s4a_rnb_photo", "skip"): "s4a_rnb_description",
    ("s4a_rnb_description", "valid"): "s5_complaint_confirm",
    ("s4a_rnb_description", "skip"): "s5_complaint_confirm",

    # 4A others
    ("s4a_others_title", "valid"): "s4a_others_dept",
    ("s4a_others_dept", "valid"): "s4a_others_location",
    ("s4a_others_dept", "skip"): "s4a_others_location",
    ("s4a_others_location", "valid"): "s4a_others_urgency",
    ("s4a_others_urgency", "valid"): "s4a_others_description",
    ("s4a_others_description", "valid"): "s4a_others_photo",
    ("s4a_others_photo", "valid"): "s5_complaint_confirm",
    ("s4a_others_photo", "skip"): "s5_complaint_confirm",

    # Stage 4B branch select
    ("s4b_private_subcategory", "police"): "s4b_police_nature",
    ("s4b_private_subcategory", "revenue"): "s4b_revenue_issue_type",
    ("s4b_private_subcategory", "welfare"): "s4b_welfare_voter_id_check",
    ("s4b_private_subcategory", "medical"): "s4b_medical_patient_name",
    ("s4b_private_subcategory", "education"): "s4b_education_institution",
    ("s4b_private_subcategory", "others"): "s4b_others_title",
    ("s4b_private_subcategory", "invalid"): "s4b_private_subcategory",

    # 4B police
    ("s4b_police_nature", "valid"): "s4b_police_incident_date",
    ("s4b_police_incident_date", "valid"): "s4b_police_station",
    ("s4b_police_station", "valid"): "s4b_police_fir_number",
    ("s4b_police_fir_number", "valid"): "s4b_police_parties",
    ("s4b_police_fir_number", "skip"): "s4b_police_parties",
    ("s4b_police_parties", "valid"): "s4b_police_urgency",
    ("s4b_police_urgency", "valid"): "s4b_police_description",
    ("s4b_police_description", "valid"): "s5_complaint_confirm",

    # 4B revenue
    ("s4b_revenue_issue_type", "valid"): "s4b_revenue_plot",
    ("s4b_revenue_plot", "valid"): "s4b_revenue_village_mandal",
    ("s4b_revenue_plot", "skip"): "s4b_revenue_village_mandal",
    ("s4b_revenue_village_mandal", "valid"): "s4b_revenue_status",
    ("s4b_revenue_status", "valid"): "s4b_revenue_documents",
    ("s4b_revenue_documents", "valid"): "s4b_revenue_description",
    ("s4b_revenue_documents", "skip"): "s4b_revenue_description",
    ("s4b_revenue_description", "valid"): "s5_complaint_confirm",

    # 4B welfare
    ("s4b_welfare_voter_id_check", "valid"): "s4b_welfare_category",
    ("s4b_welfare_voter_id_check", "skip"): "s4b_welfare_category",
    ("s4b_welfare_category", "valid"): "s4b_welfare_scheme",
    ("s4b_welfare_scheme", "valid"): "s4b_welfare_issue_type",
    ("s4b_welfare_scheme", "skip"): "s4b_welfare_issue_type",
    ("s4b_welfare_issue_type", "valid"): "s4b_welfare_app_number",
    ("s4b_welfare_app_number", "valid"): "s4b_welfare_pending_duration",
    ("s4b_welfare_app_number", "skip"): "s4b_welfare_pending_duration",
    ("s4b_welfare_pending_duration", "valid"): "s4b_welfare_description",
    ("s4b_welfare_description", "valid"): "s5_complaint_confirm",

    # 4B medical
    ("s4b_medical_patient_name", "valid"): "s4b_medical_patient_age",
    ("s4b_medical_patient_age", "valid"): "s4b_medical_relation",
    ("s4b_medical_relation", "valid"): "s4b_medical_nature",
    ("s4b_medical_nature", "valid"): "s4b_medical_location",
    ("s4b_medical_location", "valid"): "s4b_medical_urgency",
    ("s4b_medical_urgency", "valid"): "s4b_medical_financial",
    ("s4b_medical_financial", "valid"): "s4b_medical_description",
    ("s4b_medical_description", "valid"): "s5_complaint_confirm",

    # 4B education
    ("s4b_education_institution", "valid"): "s4b_education_issue_type",
    ("s4b_education_issue_type", "valid"): "s4b_education_student_name",
    ("s4b_education_student_name", "valid"): "s4b_education_class",
    ("s4b_education_class", "valid"): "s4b_education_status",
    ("s4b_education_status", "valid"): "s4b_education_ref_number",
    ("s4b_education_ref_number", "valid"): "s4b_education_description",
    ("s4b_education_ref_number", "skip"): "s4b_education_description",
    ("s4b_education_description", "valid"): "s5_complaint_confirm",

    # 4B others
    ("s4b_others_title", "valid"): "s4b_others_nature",
    ("s4b_others_nature", "valid"): "s4b_others_urgency",
    ("s4b_others_urgency", "valid"): "s4b_others_documents",
    ("s4b_others_documents", "valid"): "s4b_others_description",
    ("s4b_others_documents", "skip"): "s4b_others_description",
    ("s4b_others_description", "valid"): "s5_complaint_confirm",

    # 4C appointment
    ("s4c_appointment_subcategory", "meeting"): "s4c_appointment_type",
    ("s4c_appointment_subcategory", "event"): "s4c_appointment_type",
    ("s4c_appointment_subcategory", "felicitation"): "s4c_appointment_type",
    ("s4c_appointment_subcategory", "invalid"): "s4c_appointment_subcategory",
    ("s4c_appointment_type", "valid"): "s4c_appointment_org_name",
    ("s4c_appointment_org_name", "valid"): "s4c_appointment_purpose",
    ("s4c_appointment_purpose", "valid"): "s4c_appointment_preferred_date",
    ("s4c_appointment_preferred_date", "valid"): "s4c_appointment_preferred_time",
    ("s4c_appointment_preferred_time", "valid"): "s4c_appointment_venue",
    ("s4c_appointment_preferred_time", "skip"): "s4c_appointment_venue",
    ("s4c_appointment_venue", "valid"): "s4c_appointment_attendees",
    ("s4c_appointment_attendees", "valid"): "s4c_appointment_contact_name",
    ("s4c_appointment_attendees", "skip"): "s4c_appointment_contact_name",
    ("s4c_appointment_contact_name", "valid"): "s4c_appointment_contact_number",
    ("s4c_appointment_contact_number", "valid"): "s4c_appointment_notes",
    ("s4c_appointment_notes", "valid"): "s5_complaint_confirm",
    ("s4c_appointment_notes", "skip"): "s5_complaint_confirm",

    # Stage 5
    ("s5_complaint_confirm", "confirm"): "s5_ticket_generated",
    ("s5_complaint_confirm", "edit"): "<dispatched via fix_field>",
    ("s5_complaint_confirm", "cancel"): "<dispatched via abandon>",
    ("s5_ticket_generated", "valid"): "s5_acknowledgement",
    ("s5_acknowledgement", "valid"): "s6_returning_user_menu",

    # Stage 6
    ("s6_returning_user_menu", "new_complaint"): "s3_category_select",
    ("s6_returning_user_menu", "check_status"): "s6_status_check",
    ("s6_returning_user_menu", "talk_office"): "<handoff to pa_inbox>",
    ("s6_returning_user_menu", "change_language"): "s1_language_select",
    ("s6_returning_user_menu", "help"): "s6_returning_user_menu",
    ("s6_status_check", "valid"): "s6_returning_user_menu",
}

FIX_FIELD_TO_STATE = {
    "name": "s2_register_name",
    "dob": "s2_register_dob",
    "mobile": "s2_register_mobile",
    "voter_id": "s2_register_voter_id",
    "mandal": "s2_register_mandal",
    "village_ward": "s2_register_village_ward",
    "ward_number": "s2_register_ward_number",
    "geo": "s2_register_geo",
}

ALLOWED_FIX_STATES = {
    "s2_register_name", "s2_register_dob", "s2_register_mobile", "s2_register_voter_id",
    "s2_register_mandal", "s2_register_village_ward", "s2_register_ward_number", "s2_register_geo",
    "s2_register_confirm", "s4a_public_subcategory", "s4a_water_issue_type", "s4a_water_location",
    "s4a_water_duration", "s4a_water_households", "s4a_water_prev_complaint", "s4a_water_description",
    "s4a_electricity_issue_type", "s4a_electricity_location", "s4a_electricity_duration",
    "s4a_electricity_households", "s4a_electricity_discom_ref", "s4a_electricity_description",
    "s4a_sanitation_issue_type", "s4a_sanitation_location", "s4a_sanitation_duration", "s4a_sanitation_scale",
    "s4a_sanitation_photo", "s4a_sanitation_description", "s4a_rnb_issue_type", "s4a_rnb_location",
    "s4a_rnb_severity", "s4a_rnb_duration", "s4a_rnb_photo", "s4a_rnb_description", "s4a_others_title",
    "s4a_others_dept", "s4a_others_location", "s4a_others_urgency", "s4a_others_description", "s4a_others_photo",
    "s4b_private_subcategory", "s4b_police_nature", "s4b_police_incident_date", "s4b_police_station",
    "s4b_police_fir_number", "s4b_police_parties", "s4b_police_urgency", "s4b_police_description",
    "s4b_revenue_issue_type", "s4b_revenue_plot", "s4b_revenue_village_mandal", "s4b_revenue_status",
    "s4b_revenue_documents", "s4b_revenue_description", "s4b_welfare_voter_id_check", "s4b_welfare_category",
    "s4b_welfare_scheme", "s4b_welfare_issue_type", "s4b_welfare_app_number", "s4b_welfare_pending_duration",
    "s4b_welfare_description", "s4b_medical_patient_name", "s4b_medical_patient_age", "s4b_medical_relation",
    "s4b_medical_nature", "s4b_medical_location", "s4b_medical_urgency", "s4b_medical_financial",
    "s4b_medical_description", "s4b_education_institution", "s4b_education_issue_type", "s4b_education_student_name",
    "s4b_education_class", "s4b_education_status", "s4b_education_ref_number", "s4b_education_description",
    "s4b_others_title", "s4b_others_nature", "s4b_others_urgency", "s4b_others_documents", "s4b_others_description",
    "s4c_appointment_subcategory", "s4c_appointment_type", "s4c_appointment_org_name", "s4c_appointment_purpose",
    "s4c_appointment_preferred_date", "s4c_appointment_preferred_time", "s4c_appointment_venue",
    "s4c_appointment_attendees", "s4c_appointment_contact_name", "s4c_appointment_contact_number",
    "s4c_appointment_notes", "s5_complaint_confirm"
}


def resolve_next(state_name: str, validation_result: str) -> str:
    return TRANSITIONS.get((state_name, validation_result), state_name)
