from fastapi.testclient import TestClient

import app.main as main
from app.schemas import AdverseEvent, Label
from app.services.rxnorm import RxNormMatch

client = TestClient(main.app)


def test_search_name_returns_label(monkeypatch):
    async def fake_normalize(query, **kwargs):
        return RxNormMatch(rxcui="5640", name="Ibuprofen")

    async def fake_fetch(*, rxcui=None, name=None, **kwargs):
        assert rxcui == "5640"
        return Label(indications="Pain relief.", dosage="1 tablet.", warnings="NSAID warning.")

    async def fake_events(*, rxcui=None, name=None, **kwargs):
        return [AdverseEvent(term="Nausea", count=5321)]

    monkeypatch.setattr(main, "normalize_name", fake_normalize)
    monkeypatch.setattr(main, "fetch_label", fake_fetch)
    monkeypatch.setattr(main, "fetch_adverse_events", fake_events)

    response = client.post("/search/name", json={"query": "ibuprofen"})

    assert response.status_code == 200
    data = response.json()
    assert data["matched_name"] == "Ibuprofen"
    assert data["rxcui"] == "5640"
    assert data["label"]["indications"] == "Pain relief."
    assert data["adverse_events"] == [{"term": "Nausea", "count": 5321}]
    assert "Consult a healthcare provider" in data["disclaimer"]


def test_search_name_no_match(monkeypatch):
    async def fake_normalize(query, **kwargs):
        return None

    async def fake_fetch(*, rxcui=None, name=None, **kwargs):
        return None

    async def fake_events(*, rxcui=None, name=None, **kwargs):
        return []

    monkeypatch.setattr(main, "normalize_name", fake_normalize)
    monkeypatch.setattr(main, "fetch_label", fake_fetch)
    monkeypatch.setattr(main, "fetch_adverse_events", fake_events)

    response = client.post("/search/name", json={"query": "zzzzz"})

    assert response.status_code == 200
    data = response.json()
    assert data["matched_name"] is None
    assert data["label"] is None


def test_search_name_rejects_empty_query():
    response = client.post("/search/name", json={"query": ""})
    assert response.status_code == 422
