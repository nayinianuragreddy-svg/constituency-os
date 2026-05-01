# TEST PROMPT TEMPLATE
# Used solely by tests/unit/test_prompt_renderer.py to exercise every placeholder.
# Do NOT use this in production. The real Communication Agent prompt lives at
# app/agents/communication/prompts/system_v2_1.md (created in PR 5).

You are the assistant for {MLA_NAME}, representing {CONSTITUENCY_NAME}.

Citizen language preference: {preferred_language}
Citizen last message script: {last_message_script}

CURRENT CONVERSATION STATE:
{conversation_summary}

CURRENT CATEGORY SCHEMA:
{current_category_schema}

CURRENT DATE (IST):
{current_date_ist}

End of test template.
