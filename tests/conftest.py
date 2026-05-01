import os
import pytest
from dotenv import load_dotenv

# Load .env before any test runs. override=True ensures .env wins over stale shell vars.
load_dotenv(override=True)


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless -m live is explicitly passed."""
    if config.getoption("-m") and "live" in config.getoption("-m"):
        return  # user explicitly asked for live tests, don't skip
    skip_live = pytest.mark.skip(reason="live tests require -m live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(scope="session")
def openai_client():
    """Real OpenAI client. Used by live tests only."""
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.startswith("sk-"):
        pytest.skip("OPENAI_API_KEY not configured")
    return OpenAI(api_key=api_key)


@pytest.fixture(scope="session")
def communication_model():
    """The model name configured for the Communication Agent."""
    return os.getenv("LLM_MODEL_COMMUNICATION", "gpt-4o-mini")
