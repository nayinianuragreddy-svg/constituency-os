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


@pytest.fixture(scope="session")
def seeded_test_db_engine():
    """Boot a fresh test database, run all migrations, yield a SQLAlchemy engine.

    The DB is dropped at session teardown.
    """
    import subprocess
    import sqlalchemy as sa

    db_user = os.getenv("USER", "postgres")
    db_name = "constituency_os_pytest"
    base_url = f"postgresql+psycopg://{db_user}@localhost:5432"
    db_url = f"{base_url}/{db_name}"

    subprocess.run(["dropdb", "--if-exists", db_name], check=True)
    subprocess.run(["createdb", db_name], check=True)

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    subprocess.run(
        ["alembic", "-c", "alembic.ini", "upgrade", "head"],
        env=env,
        check=True,
    )

    engine = sa.create_engine(db_url)
    yield engine
    engine.dispose()
    subprocess.run(["dropdb", "--if-exists", db_name], check=False)
