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
    resp = client.post(
        "/register",
        data={"username": "alice", "password": "password123", "confirm": "password123"},
    )
    assert resp.status_code == 200  # followed redirect to "/"
    # Session cookie now lets the gated endpoint through (422 = past auth, empty body).
    gated = client.post("/search/symptom", json={"symptoms": ""})
    assert gated.status_code == 422


def test_register_rejects_short_password():
    resp = client.post(
        "/register",
        data={"username": "bob", "password": "short", "confirm": "short"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "at least" in resp.text


def test_register_rejects_mismatched_confirm():
    resp = client.post(
        "/register",
        data={"username": "carol", "password": "password123", "confirm": "different1"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "match" in resp.text.lower()


def test_register_rejects_duplicate_username():
    data = {"username": "dave", "password": "password123", "confirm": "password123"}
    assert client.post("/register", data=data).status_code == 200
    fresh = TestClient(main.app)
    resp = fresh.post("/register", data=data, follow_redirects=False)
    assert resp.status_code == 400
    assert "taken" in resp.text.lower()


def test_login_with_valid_and_invalid_credentials():
    client.post(
        "/register",
        data={"username": "erin", "password": "password123", "confirm": "password123"},
    )
    fresh = TestClient(main.app)
    bad = fresh.post(
        "/login",
        data={"username": "erin", "password": "wrongpass"},
        follow_redirects=False,
    )
    assert bad.status_code == 400

    good = fresh.post(
        "/login",
        data={"username": "erin", "password": "password123"},
        follow_redirects=False,
    )
    assert good.status_code == 303


def test_logout_revokes_access():
    client.post(
        "/register",
        data={"username": "frank", "password": "password123", "confirm": "password123"},
    )
    assert client.post("/search/symptom", json={"symptoms": ""}).status_code == 422
    client.post("/logout", follow_redirects=False)
    assert client.post("/search/symptom", json={"symptoms": "headache"}).status_code == 401
