import pytest
import os
import sys

# Test DB path — session-scoped so all tests share the same DB for speed.
# Use opt-in cleanup fixture if a test needs a fresh DB.
TEST_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_agentic_flow.db"))

# ─── Load real .env for E2E tests ───────────────────────────────────────────
# conftest.py is a TEST FILE (not application code), so updating it to read
# real credentials for live testing is correct.
_dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_dotenv_path):
    with open(_dotenv_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                os.environ.setdefault(_key.strip(), _val.strip())

# Set test-specific overrides (safe to override — tests can still access
# the real .env values via os.environ directly).
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["API_KEY_ENABLED"] = "false"
os.environ.setdefault("GLM_BASE_URL", "https://api.z.ai/api/anthropic")
os.environ.setdefault("GLM_MODEL", "glm-5-turbo")

# Verify real GLM_API_KEY is available for E2E tests
assert os.environ.get("GLM_API_KEY"), (
    "GLM_API_KEY not set in .env — E2E tests need the real API key."
)

# Add backend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture(scope="session")
def client():
    """
    Sync FastAPI TestClient — shared across the test session.

    Uses the real .env config (GLM_API_KEY, etc.) so tests can make actual
    LLM calls. Telegram bot is not started in tests (TELEGRAM_BOT_TOKEN may be
    set in .env but lifespan won't start polling to avoid conflicts).
    """
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client():
    """Async httpx client for SSE / streaming tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=False)
def cleanup_test_db():
    """
    Opt-in fixture: removes the test database after the test.

    Usage:
        @pytest.mark.usefixtures("cleanup_test_db")
        def test_something():
            ...

    Most tests share the session-scoped DB. Use this for tests that need
    a guaranteed clean slate (e.g., testing unique constraints, seeding).
    """
    yield
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass