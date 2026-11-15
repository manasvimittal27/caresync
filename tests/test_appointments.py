from urllib.parse import parse_qs, urlparse

from tests.conftest import add_member

APPT = {
    "doctor": "Dr. Mehta",
    "specialty": "Cardiology",
    "starts_at": "2026-11-20T11:00:00",  # Naive = elder's local time (IST).
    "duration_minutes": 45,
    "location": "Apollo Clinic, Indiranagar",
    "notes": "Bring ECG report",
}


def test_create_appointment_stores_utc_and_calendar_link(owner):
    c, _ = owner
    res = c.post("/api/appointments", json=APPT)
    assert res.status_code == 201
    appt = res.json()
    assert appt["starts_at"] == "2026-11-20T05:30:00Z"
    query = parse_qs(urlparse(appt["google_calendar_url"]).query)
    assert query["dates"] == ["20261120T053000Z/20261120T061500Z"]
    assert query["location"] == [APPT["location"]]


def test_list_hides_past_unless_requested(owner, clock):
    c, _ = owner
    c.post("/api/appointments", json=APPT)
    c.post("/api/appointments", json={**APPT, "doctor": "Dr. Old", "starts_at": "2026-11-01T10:00:00"})
    assert [a["doctor"] for a in c.get("/api/appointments").json()] == ["Dr. Mehta"]
    assert len(c.get("/api/appointments?include_past=true").json()) == 2


def test_update_and_delete_appointment(owner):
    c, _ = owner
    appt_id = c.post("/api/appointments", json=APPT).json()["id"]
    updated = c.put(f"/api/appointments/{appt_id}", json={**APPT, "starts_at": "2026-11-21T09:00:00+05:30"})
    assert updated.json()["starts_at"] == "2026-11-21T03:30:00Z"
    assert c.delete(f"/api/appointments/{appt_id}").status_code == 204
    assert c.delete(f"/api/appointments/{appt_id}").status_code == 404


def test_family_can_view_but_not_edit(app, owner):
    c, _ = owner
    c.post("/api/appointments", json=APPT)
    family = add_member(c, app, "family", "son@example.com")
    assert len(family.get("/api/appointments").json()) == 1
    assert family.post("/api/appointments", json=APPT).status_code == 403


def test_appointment_validation(owner):
    c, _ = owner
    assert c.post("/api/appointments", json={**APPT, "duration_minutes": 0}).status_code == 422
    assert c.post("/api/appointments", json={**APPT, "doctor": ""}).status_code == 422
