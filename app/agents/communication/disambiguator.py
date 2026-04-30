import json
from app.core.llm import llm_call, load_prompt

_FALLBACKS = {
    "te": "క్షమించండి, మరోసారి చెప్పగలరా?",
    "hi": "कमा करें, कृपया दोबारा बताएं।",
    "en": "Sorry, could you please rephrase?",
}


def draft_disambiguation_reply(
    current_state: str,
    last_bot_message: str | None,
    user_message: str,
    preferred_language: str,
) -> str:
    lang = preferred_language if preferred_language in _FALLBACKS else "en"
    try:
        system_prompt = load_prompt("communication_disambiguator")
        user_prompt = json.dumps(
            {
                "current_state": current_state,
                "last_bot_message": last_bot_message or "",
                "user_message": user_message,
                "preferred_language": lang,
            },
            ensure_ascii=False,
        )
        result = llm_call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format="json",
            metadata={"agent_name": "communication", "purpose": "disambiguation"},
        )
        if result.success and isinstance(result.parsed_json, dict):
            reply = result.parsed_json.get("reply_text", "")
            if reply:
                return reply
    except Exception:
        pass
    return _FALLBACKS[lang]
