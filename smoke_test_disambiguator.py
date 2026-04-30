"""
Smoke test for the disambiguation reply drafter.

Loads the disambiguator module directly so it does not trigger the package
__init__.py, which requires a live database connection.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).parent


def _load_module(dotted_name: str, rel_path: str):
    """Load a module from a file path without triggering package __init__."""
    abs_path = (BASE / rel_path).resolve()
    spec = importlib.util.spec_from_file_location(dotted_name, abs_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    os.environ["LLM_ENABLED"] = "true"
    os.environ["LLM_TIMEOUT_SECONDS"] = "10"
    os.environ["LLM_MAX_CALLS_PER_MINUTE"] = "100"

    llm_mod = _load_module("app.core.llm", "app/core/llm.py")
    llm_mod._call_times.clear()
    llm_mod._daily_cost.clear()

    disambig_mod = _load_module(
        "app.agents.communication.disambiguator",
        "app/agents/communication/disambiguator.py",
    )
    draft_disambiguation_reply = disambig_mod.draft_disambiguation_reply

    def _provider_happy(*, model, system_prompt, user_prompt, temperature, tools=None, metadata=None):
        return {"text": json.dumps({"reply_text": "It seems you may have typed something by mistake. Could you share your date of birth in DD/MM/YYYY format, for example 15/06/1987?"})}

    def _provider_bad_json(*, model, system_prompt, user_prompt, temperature, tools=None, metadata=None):
        return {"text": "not json at all"}

    def _provider_empty_reply(*, model, system_prompt, user_prompt, temperature, tools=None, metadata=None):
        return {"text": json.dumps({"reply_text": ""})}

    original_llm = disambig_mod.llm_call

    disambig_mod.llm_call = lambda **kw: original_llm(**{**kw, "provider_call": _provider_happy})
    llm_mod._call_times.clear()
    llm_mod._daily_cost.clear()

    reply = draft_disambiguation_reply(
        current_state="s2_register_dob",
        last_bot_message="Please share your DOB in DD/MM/YYYY.",
        user_message="kjlaksdjf",
        preferred_language="en",
    )
    assert reply, "reply must be non-empty"
    assert "—" not in reply, "reply must not contain em-dashes"
    assert "I didn't understand" not in reply, "reply must not contain the banned phrase"
    print(f"  LLM reply: {reply!r}")

    disambig_mod.llm_call = lambda **kw: original_llm(**{**kw, "provider_call": _provider_bad_json})
    llm_mod._call_times.clear()
    llm_mod._daily_cost.clear()

    fallback_en = draft_disambiguation_reply(
        current_state="s2_register_dob",
        last_bot_message="Please share your DOB.",
        user_message="asdfjkl",
        preferred_language="en",
    )
    assert fallback_en == "Sorry, could you please rephrase?", f"expected English fallback, got {fallback_en!r}"
    print(f"  English fallback: {fallback_en!r}")

    disambig_mod.llm_call = lambda **kw: original_llm(**{**kw, "provider_call": _provider_empty_reply})
    llm_mod._call_times.clear()
    llm_mod._daily_cost.clear()

    fallback_te = draft_disambiguation_reply(
        current_state="s2_register_name",
        last_bot_message="Please share your full name.",
        user_message="???",
        preferred_language="te",
    )
    assert fallback_te == "క్షమించండి, మరోసారి చెప్పగలరా?", f"expected Telugu fallback, got {fallback_te!r}"
    print(f"  Telugu fallback: {fallback_te!r}")

    disambig_mod.llm_call = original_llm
    print("Disambiguator smoke test passed.")


if __name__ == "__main__":
    main()
