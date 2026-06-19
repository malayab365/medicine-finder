from fastapi.testclient import TestClient

import app.main as main
from app.auth import hash_password, verify_password

client = TestClient(main.app)


def test_password_hash_roundtrip():
    stored = hash_password("password123")
    assert stored.startswith("scrypt$")
    assert verify_password("password123", stored)
    assert not verify_password("wrong", stored)


def test_register_logs_in_and_unlocks_symptom_search():
    resp = client.post("/auth/register", json={"username": "alice", "password": "password123"})
    assert resp.status_code == 201
    assert resp.json()["username"] == "alice"
    # Session cookie now lets the gated endpoint through (422 = past auth, empty body).
    gated = client.post("/search/symptom", json={"symptoms": ""})
    assert gated.status_code == 422


def test_me_reflects_session():
    anon = TestClient(main.app)
    assert anon.get("/auth/me").status_code == 401
    anon.post("/auth/register", json={"username": "moe", "password": "password123"})
    me = anon.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "moe"


def test_register_rejects_short_password():
    resp = client.post("/auth/register", json={"username": "bob", "password": "short"})
    assert resp.status_code == 400
    assert "at least" in resp.json()["detail"]


def test_register_rejects_duplicate_username():
    data = {"username": "dave", "password": "password123"}
    assert client.post("/auth/register", json=data).status_code == 201
    fresh = TestClient(main.app)
    resp = fresh.post("/auth/register", json=data)
    assert resp.status_code == 409
    assert "taken" in resp.json()["detail"].lower()


def test_login_with_valid_and_invalid_credentials():
    client.post("/auth/register", json={"username": "erin", "password": "password123"})
    fresh = TestClient(main.app)
    bad = fresh.post("/auth/login", json={"username": "erin", "password": "wrongpass"})
    assert bad.status_code == 401
    good = fresh.post("/auth/login", json={"username": "erin", "password": "password123"})
    assert good.status_code == 200
    assert good.json()["username"] == "erin"


def test_logout_revokes_access():
    client.post("/auth/register", json={"username": "frank", "password": "password123"})
    assert client.post("/search/symptom", json={"symptoms": ""}).status_code == 422
    assert client.post("/auth/logout").status_code == 204
    assert client.post("/search/symptom", json={"symptoms": "headache"}).status_code == 401
