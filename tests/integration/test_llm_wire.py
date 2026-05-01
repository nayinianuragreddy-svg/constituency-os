"""Live integration test proving the OpenAI wire works end to end from inside the repo.

This test is the foundation of every later live test in V2.0. If this passes, we know:
- .env loads correctly
- OPENAI_API_KEY is valid
- The configured Communication Agent model accepts requests
- The OpenAI SDK version is compatible with the configured model
- A round trip works in under 10 seconds

Run with:
  pytest tests/integration/test_llm_wire.py -m live -v
"""

import pytest


@pytest.mark.live
def test_openai_round_trip(openai_client, communication_model):
    """Send a tiny prompt, expect a real reply containing 'pong'."""
    response = openai_client.chat.completions.create(
        model=communication_model,
        messages=[
            {"role": "user", "content": "Reply with exactly the single word: pong"}
        ],
        max_completion_tokens=10,
    )

    reply = response.choices[0].message.content
    assert reply is not None, "OpenAI returned no content"
    assert "pong" in reply.lower(), f"expected 'pong' in reply, got {reply!r}"


@pytest.mark.live
def test_openai_handles_telugu(openai_client, communication_model):
    """Verify the model can both read and write Telugu script.

    This is a smoke test for the multilingual contract from Doc C v2.1 §4.
    If this fails, the entire Communication Agent design is at risk.
    """
    response = openai_client.chat.completions.create(
        model=communication_model,
        messages=[
            {"role": "user", "content": "నమస్తే అని తెలుగులో ఒక్క పదంలో జవాబు ఇవ్వండి"}
        ],
        max_completion_tokens=20,
    )

    reply = response.choices[0].message.content
    assert reply is not None, "OpenAI returned no content"
    # Telugu Unicode range U+0C00 to U+0C7F
    has_telugu = any('ఀ' <= ch <= '౿' for ch in reply)
    assert has_telugu, f"expected Telugu characters in reply, got {reply!r}"
