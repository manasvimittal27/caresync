from fastapi.testclient import TestClient

from tests.conftest import add_member


def test_owner_adds_member_who_can_sign_in(app, owner):
    c, _ = owner
    caretaker = add_member(c, app, "caretaker", "nurse@example.com")
    assert caretaker.get("/api/me").json()["member"]["role"] == "caretaker"
    roles = [m["role"] for m in c.get("/api/members").json()]
    assert roles == ["elder", "caretaker"]


def test_duplicate_member_email_conflicts(owner):
    c, _ = owner
    payload = {"name": "Ravi", "email": "ravi@example.com", "role": "family"}
    assert c.post("/api/members", json=payload).status_code == 201
    assert c.post("/api/members", json=payload).status_code == 409


def test_only_owner_manages_members(app, owner):
    c, _ = owner
    caretaker = add_member(c, app, "caretaker", "nurse@example.com")
    res = caretaker.post("/api/members", json={"name": "X", "email": "x@example.com", "role": "family"})
    assert res.status_code == 403


def test_removed_member_loses_access_immediately(app, owner):
    c, _ = owner
    family = add_member(c, app, "family", "daughter@example.com")
    member_id = family.get("/api/me").json()["member"]["id"]
    assert c.delete(f"/api/members/{member_id}").status_code == 204
    assert family.get("/api/me").status_code == 401
    assert len(c.get("/api/members").json()) == 1


def test_owner_cannot_remove_self(owner):
    c, body = owner
    assert c.delete(f"/api/members/{body['member']['id']}").status_code == 400


def test_member_passcode_never_returned_in_listing(app, owner):
    c, _ = owner
    add_member(c, app, "family", "son@example.com")
    for member in c.get("/api/members").json():
        assert "passcode_hash" not in member and "passcode" not in member


def test_profiles_are_isolated(app, owner):
    """A member of one profile can never see another profile's data."""
    c, _ = owner
    c.post(
        "/api/medications",
        json={"name": "Aspirin", "dosage": "75 mg", "times": ["09:00"], "start_date": "2026-11-01"},
    )
    other = TestClient(app)
    other.post(
        "/api/profiles", json={"elder_name": "Other", "email": "o@example.com", "passcode": "other-123"}
    )
    assert other.get("/api/medications").json() == []
