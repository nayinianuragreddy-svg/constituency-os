"""
Live smoke test for draft_disambiguation_reply: hits the real OpenAI API.

Skips cleanly (exit 0) if OPENAI_API_KEY is not set.
Run after setting OPENAI_API_KEY and LLM_ENABLED=true.
"""
import importlib.util
import os
import sys
from pathlib import Path

BASE = Path(__file__).parent

_HINDI_FALLBACK = "क्षमा करें, कृपया दोबारा बताएं।"
_ENGLISH_FALLBACK = "Sorry, could you please rephrase?"
_TELUGU_RANGE = range(0x0C00, 0x0C80)


def _load_module(dotted_name: str, rel_path: str):
    abs_path = (BASE / rel_path).resolve()
    spec = importlib.util.spec_from_file_location(dotted_name, abs_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _has_telugu(text: str) -> bool:
    return any(ord(ch) in _TELUGU_RANGE for ch in text)


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set, skipping live disambiguator test.")
        sys.exit(0)

    os.environ["LLM_ENABLED"] = "true"
    os.environ.setdefault("LLM_TIMEOUT_SECONDS", "30")
    os.environ.setdefault("LLM_MAX_CALLS_PER_MINUTE", "100")

    llm_mod = _load_module("app.core.llm", "app/core/llm.py")
    llm_mod._call_times.clear()
    llm_mod._daily_cost.clear()

    disambig_mod = _load_module(
        "app.agents.communication.disambiguator",
        "app/agents/communication/disambiguator.py",
    )
    draft = disambig_mod.draft_disambiguation_reply

    print("Running live disambiguator test (English)...")
    reply_en = draft(
        current_state="s2_register_dob",
        last_bot_message="Please share your date of birth in DD/MM/YYYY format.",
        user_message="kjlaksdjf",
        preferred_language="en",
    )
    print(f"  LLM reply (en): {reply_en!r}")
    assert reply_en, "English reply must be non-empty"
    assert len(reply_en) > 10, f"English reply too short: {reply_en!r}"
    assert "—" not in reply_en, "English reply must not contain em-dashes"
    assert "I didn't understand" not in reply_en, "English reply must not contain the banned phrase"
    assert reply_en != _ENGLISH_FALLBACK, (
        "English reply equals the hardcoded fallback, LLM call likely failed silently"
    )

    print("Running live disambiguator test (Telugu)...")
    llm_mod._call_times.clear()
    llm_mod._daily_cost.clear()
    reply_te = draft(
        current_state="s2_register_dob",
        last_bot_message="Please share your date of birth in DD/MM/YYYY format.",
        user_message="నాకు అర్థం కాలేదు",
        preferred_language="te",
    )
    print(f"  LLM reply (te): {reply_te!r}")
    assert reply_te, "Telugu reply must be non-empty"
    assert "—" not in reply_te, "Telugu reply must not contain em-dashes"
    assert _has_telugu(reply_te), (
        f"Telugu reply must contain at least one Telugu Unicode character (U+0C00-U+0C7F), got: {reply_te!r}"
    )

    print("Live disambiguator smoke test passed.")


if __name__ == "__main__":
    main()
