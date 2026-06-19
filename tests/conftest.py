import json
import os
import tempfile
from pathlib import Path

import pytest

import app.db as db
import app.main as main
from app.config import settings
from app.services.openfda import fetch_adverse_events, fetch_label
from app.services.rxnorm import normalize_name

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def register_and_login(client, username: str = "tester", password: str = "password123"):
    """Register a user on the given TestClient; its cookie jar holds the session."""
    resp = client.post(
        "/register",
        data={"username": username, "password": password, "confirm": password},
    )
    assert resp.status_code == 200  # followed 303 redirect to "/"
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
    main.name_limiter.reset()
    main.symptom_limiter.reset()
    db.reset_users()
    yield
