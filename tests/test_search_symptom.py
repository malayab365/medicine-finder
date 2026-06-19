from fastapi.testclient import TestClient

import app.main as main
from app.schemas import Label
from app.services.rxnorm import RxNormMatch
from app.services.triage import TriageResult

client = TestClient(main.app)


def test_emergency_keyword_short_circuits_before_llm(monkeypatch):
    async def boom(*args, **kwargs):
        raise AssertionError("triage must not be called for emergency input")

    monkeypatch.setattr(main, "triage", boom)

    response = client.post("/search/symptom", json={"symptoms": "I have severe chest pain"})

    assert response.status_code == 200
    data = response.json()
    assert data["emergency"] is True
    assert "emergency" in data["message"].lower()
    assert data["candidates"] == []
    # Disclaimer banner present on every symptom response.
    assert "Consult a healthcare provider" in data["disclaimer"]


def test_symptom_search_returns_candidates_with_labels(monkeypatch):
    async def fake_triage(symptoms, **kwargs):
        return TriageResult(candidates=["acetaminophen"])

    async def fake_normalize(name, **kwargs):
        return RxNormMatch(rxcui="161", name="Acetaminophen")

    async def fake_fetch(*, rxcui=None, name=None, **kwargs):
        return Label(indications="Pain and fever relief.", dosage="1 tablet.")

    monkeypatch.setattr(main, "triage", fake_triage)
    monkeypatch.setattr(main, "normalize_name", fake_normalize)
    monkeypatch.setattr(main, "fetch_label", fake_fetch)

    response = client.post("/search/symptom", json={"symptoms": "mild headache and fever"})

    assert response.status_code == 200
    data = response.json()
    assert data["emergency"] is False
    assert len(data["candidates"]) == 1
    candidate = data["candidates"][0]
    assert candidate["matched_name"] == "Acetaminophen"
    assert candidate["rxcui"] == "161"
    assert candidate["label"]["indications"] == "Pain and fever relief."
    assert "Consult a healthcare provider" in data["disclaimer"]


def test_symptom_search_respects_llm_emergency_flag(monkeypatch):
    async def fake_triage(symptoms, **kwargs):
        return TriageResult(emergency=True)

    monkeypatch.setattr(main, "triage", fake_triage)

    response = client.post("/search/symptom", json={"symptoms": "vague but worrying symptom"})

    assert response.status_code == 200
    data = response.json()
    assert data["emergency"] is True
    assert data["candidates"] == []


def test_symptom_search_rejects_empty(monkeypatch):
    response = client.post("/search/symptom", json={"symptoms": ""})
    assert response.status_code == 422
