import json
from pathlib import Path

import pytest

import app.main as main
from app.services.openfda import fetch_adverse_events, fetch_label
from app.services.rxnorm import normalize_name

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def _clear_service_state():
    """Keep cached results and rate-limit counters from leaking across tests."""
    normalize_name.cache_clear()
    fetch_label.cache_clear()
    fetch_adverse_events.cache_clear()
    main.name_limiter.reset()
    main.symptom_limiter.reset()
    yield
