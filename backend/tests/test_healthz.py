from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_returns_ok():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_robots_blocks_indexing():
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.text.strip() == "User-agent: *\nDisallow: /"
    assert response.headers["content-type"].startswith("text/plain")
