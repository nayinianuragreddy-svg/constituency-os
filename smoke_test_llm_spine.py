import os
import time

from app.core.llm import _call_times, _daily_cost, llm_call, load_prompt


def main() -> None:
    os.environ["LLM_ENABLED"] = "false"
    r = llm_call(user_prompt="hi", system_prompt="sys", response_format="json")
    assert r.success is True
    assert r.parsed_json == {}

    os.environ["LLM_ENABLED"] = "true"
    os.environ["LLM_TIMEOUT_SECONDS"] = "0.01"

    def slow_provider(**kwargs):
        time.sleep(0.2)
        return {"text": "{}"}

    timeout_res = llm_call(
        user_prompt="x",
        system_prompt="y",
        response_format="json",
        provider_call=slow_provider,
        metadata={"agent_name": "smoke"},
    )
    assert timeout_res.fallback_used is True
    assert timeout_res.error == "timeout"

    _call_times.clear()
    _daily_cost.clear()
    os.environ["LLM_TIMEOUT_SECONDS"] = "1"
    os.environ["LLM_MAX_CALLS_PER_MINUTE"] = "2"

    def fast_provider(**kwargs):
        return {"text": "ok"}

    a = llm_call(user_prompt="1", system_prompt="s", provider_call=fast_provider)
    b = llm_call(user_prompt="2", system_prompt="s", provider_call=fast_provider)
    c = llm_call(user_prompt="3", system_prompt="s", provider_call=fast_provider)
    assert a.fallback_used is False
    assert b.fallback_used is False
    assert c.fallback_used is True

    prompt = load_prompt("test_bot")
    assert "Test Bot" in prompt

    print("LLM spine smoke test passed.")


if __name__ == "__main__":
    main()
