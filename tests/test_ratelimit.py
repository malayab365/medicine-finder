from fastapi.testclient import TestClient

import app.main as main
from app.ratelimit import FixedWindowRateLimiter

client = TestClient(main.app)


def test_allows_up_to_limit_then_blocks():
    limiter = FixedWindowRateLimiter(limit=2, window=60)
    assert limiter.check("ip")[0] is True
    assert limiter.check("ip")[0] is True
    allowed, retry_after = limiter.check("ip")
    assert allowed is False
    assert retry_after > 0


def test_separate_keys_have_separate_windows():
    limiter = FixedWindowRateLimiter(limit=1, window=60)
    assert limiter.check("a")[0] is True
    assert limiter.check("b")[0] is True  # different client, own budget
    assert limiter.check("a")[0] is False


def test_window_resets_after_expiry():
    limiter = FixedWindowRateLimiter(limit=1, window=0)  # window already elapsed
    assert limiter.check("ip")[0] is True
    assert limiter.check("ip")[0] is True  # previous window expired immediately


def test_symptom_endpoint_returns_429_over_limit(monkeypatch):
    async def fake_triage(symptoms, **kwargs):
        from app.services.triage import TriageResult

        return TriageResult(candidates=[])

    monkeypatch.setattr(main, "triage", fake_triage)
    monkeypatch.setattr(main.symptom_limiter, "limit", 2)

    payloads = {"symptoms": "mild headache"}
    assert client.post("/search/symptom", json=payloads).status_code == 200
    assert client.post("/search/symptom", json=payloads).status_code == 200
    blocked = client.post("/search/symptom", json=payloads)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
