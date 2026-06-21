from fastapi.testclient import TestClient

import app.main as main
from app.medicines import service as search

client = TestClient(main.app)


def test_suggest_returns_matches(monkeypatch):
    async def fake_suggest(query, clients, *, limit=10):
        assert query == "ibu"
        return ["ibuprofen", "ibuprofen / pseudoephedrine"]

    monkeypatch.setattr(search, "get_suggestions", fake_suggest)

    # Public endpoint — no authentication needed.
    response = client.get("/search/suggest", params={"q": "ibu"})

    assert response.status_code == 200
    assert response.json() == {"suggestions": ["ibuprofen", "ibuprofen / pseudoephedrine"]}


def test_suggest_blank_query_returns_empty():
    response = client.get("/search/suggest", params={"q": ""})
    assert response.status_code == 200
    assert response.json() == {"suggestions": []}


def test_suggest_missing_query_returns_empty():
    response = client.get("/search/suggest")
    assert response.status_code == 200
    assert response.json() == {"suggestions": []}
