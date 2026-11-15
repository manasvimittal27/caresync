from fastapi.testclient import TestClient

from tests.conftest import ELDER, add_member


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_create_profile_returns_care_code_and_signs_in(owner):
    c, body = owner
    assert len(body["elder"]["care_code"]) == 6
    assert body["member"]["role"] == "elder"
    assert "passcode_hash" not in body["member"]
    me = c.get("/api/me").json()
    assert me["elder"]["name"] == "Kamala Iyer"


def test_legacy_timezone_names_are_accepted(client):
    # Browsers in India often report the legacy "Asia/Calcutta" name.
    res = client.post("/api/profiles", json={**ELDER, "timezone": "Asia/Calcutta"})
    assert res.status_code == 201
    assert client.get("/api/doses/today").status_code == 200


def test_session_status_does_not_error_when_signed_out(client):
    assert client.get("/api/session").json() == {"signed_in": False}


def test_session_status_when_signed_in(owner):
    c, _ = owner
    body = c.get("/api/session").json()
    assert body["signed_in"] is True and body["member"]["role"] == "elder"


def test_session_cookie_is_httponly_and_strict(client):
    res = client.post("/api/profiles", json=ELDER)
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_profile_validation_rejects_bad_input(client):
    bad = {**ELDER, "email": "not-an-email", "passcode": "123"}
    assert client.post("/api/profiles", json=bad).status_code == 422
    assert client.post("/api/profiles", json={**ELDER, "timezone": "Mars/Base"}).status_code == 422
    assert client.post("/api/profiles", json={**ELDER, "is_admin": True}).status_code == 422


def test_sign_in_with_correct_and_wrong_passcode(app, owner):
    _, body = owner
    code = body["elder"]["care_code"]
    c = TestClient(app)
    wrong = c.post(
        "/api/session", json={"care_code": code, "email": ELDER["email"], "passcode": "wrong-pass"}
    )
    assert wrong.status_code == 401
    ok = c.post(
        "/api/session",
        json={"care_code": code.lower(), "email": ELDER["email"].upper(), "passcode": ELDER["passcode"]},
    )
    assert ok.status_code == 200
    assert c.get("/api/me").status_code == 200


def test_unknown_care_code_gives_same_error(client):
    res = client.post(
        "/api/session", json={"care_code": "ZZZZZZ", "email": "a@b.co", "passcode": "whatever1"}
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "Care code, email or passcode is incorrect"


def test_login_is_rate_limited(app, owner):
    _, body = owner
    c = TestClient(app)
    attempt = {"care_code": body["elder"]["care_code"], "email": ELDER["email"], "passcode": "bad-guess"}
    for _ in range(5):
        assert c.post("/api/session", json=attempt).status_code == 401
    # Even the right passcode is refused while blocked.
    blocked = c.post("/api/session", json={**attempt, "passcode": ELDER["passcode"]})
    assert blocked.status_code == 429


def test_requests_without_session_are_rejected(client):
    for path in ("/api/me", "/api/medications", "/api/doses/today", "/api/appointments", "/api/activity"):
        assert client.get(path).status_code == 401


def test_tampered_cookie_is_rejected(client):
    client.cookies.set("caresync_session", "forged.token.value")
    assert client.get("/api/me").status_code == 401


def test_logout_clears_session(owner):
    c, _ = owner
    assert c.post("/api/session/logout").status_code == 204
    assert c.get("/api/me").status_code == 401


def test_change_passcode(app, owner):
    c, body = owner
    bad = c.put("/api/me/passcode", json={"current_passcode": "wrong-one", "new_passcode": "new-pass-1"})
    assert bad.status_code == 400
    ok = c.put("/api/me/passcode", json={"current_passcode": ELDER["passcode"], "new_passcode": "new-pass-1"})
    assert ok.status_code == 204
    fresh = TestClient(app)
    res = fresh.post(
        "/api/session",
        json={"care_code": body["elder"]["care_code"], "email": ELDER["email"], "passcode": "new-pass-1"},
    )
    assert res.status_code == 200


def test_care_code_hidden_from_non_owners(app, owner):
    c, _ = owner
    family = add_member(c, app, "family", "son@example.com")
    assert "care_code" not in family.get("/api/me").json()["elder"]
    assert "care_code" in c.get("/api/me").json()["elder"]
