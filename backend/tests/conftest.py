import json
import os
import tempfile
from pathlib import Path

import pytest

from app.auth import repository as db
from app.core.config import settings
from app.medicines import router as medicines_router
from app.medicines.providers.openfda import fetch_adverse_events, fetch_label
from app.medicines.providers.rxnorm import normalize_name

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def register_and_login(client, username: str = "tester", password: str = "password123"):
    """Register a user on the given TestClient; its cookie jar holds the session."""
    resp = client.post("/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 201
    return client


@pytest.fixture(autouse=True, scope="session")
def _test_db():
    """Point the app at a throwaway SQLite file for the whole test session."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    settings.database_path = path
    db.init_db()
    yield
    os.unlink(path)


@pytest.fixture(autouse=True)
def _clear_service_state():
    """Keep cached results, rate-limit counters, and users from leaking across tests."""
    normalize_name.cache_clear()
    fetch_label.cache_clear()
    fetch_adverse_events.cache_clear()
    medicines_router.name_limiter.reset()
    medicines_router.symptom_limiter.reset()
    db.reset_users()
    yield
