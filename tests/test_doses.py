from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services import schedule
from tests.conftest import MED, add_member

IST = ZoneInfo("Asia/Kolkata")


def test_today_schedule_statuses(owner, clock):
    c, _ = owner
    c.post("/api/medications", json=MED)
    # Clock is 10:00 IST: the 08:00 dose is past the 30-min grace, 20:00 is upcoming.
    doses = c.get("/api/doses/today").json()["doses"]
    assert [(d["time"], d["status"]) for d in doses] == [("08:00", "overdue"), ("20:00", "upcoming")]

    clock.now = datetime(2026, 11, 15, 14, 40, tzinfo=UTC)  # 20:10 IST, inside grace window.
    statuses = [d["status"] for d in c.get("/api/doses/today").json()["doses"]]
    assert statuses == ["overdue", "due"]


def test_log_dose_is_idempotent(owner):
    c, _ = owner
    med_id = c.post("/api/medications", json=MED).json()["id"]
    payload = {"medication_id": med_id, "time": "08:00", "status": "skipped"}
    assert c.post("/api/doses", json=payload).status_code == 201
    assert c.post("/api/doses", json={**payload, "status": "taken"}).status_code == 201
    doses = c.get("/api/doses/today").json()["doses"]
    assert doses[0]["status"] == "taken"
    assert doses[0]["logged_by"] == "Kamala Iyer"


def test_log_dose_rejects_unscheduled_or_future(owner):
    c, _ = owner
    med_id = c.post("/api/medications", json=MED).json()["id"]
    assert (
        c.post("/api/doses", json={"medication_id": med_id, "time": "09:00", "status": "taken"}).status_code
        == 400
    )
    future = {"medication_id": med_id, "time": "08:00", "status": "taken", "date": "2026-11-16"}
    assert c.post("/api/doses", json=future).status_code == 400
    assert (
        c.post("/api/doses", json={"medication_id": "nope", "time": "08:00", "status": "taken"}).status_code
        == 404
    )


def test_family_cannot_log_doses(app, owner):
    c, _ = owner
    med_id = c.post("/api/medications", json=MED).json()["id"]
    family = add_member(c, app, "family", "son@example.com")
    res = family.post("/api/doses", json={"medication_id": med_id, "time": "08:00", "status": "taken"})
    assert res.status_code == 403


def test_adherence_endpoint(owner):
    c, _ = owner
    med_id = c.post("/api/medications", json=MED).json()["id"]
    # Yesterday: both doses due; take the morning one only. Today: only 08:00 is due.
    c.post(
        "/api/doses", json={"medication_id": med_id, "time": "08:00", "status": "taken", "date": "2026-11-14"}
    )
    c.post("/api/doses", json={"medication_id": med_id, "time": "08:00", "status": "taken"})
    result = c.get("/api/adherence?days=2").json()
    assert result["scheduled"] == 3
    assert result["taken"] == 2
    assert result["percent"] == 66.7


def test_adherence_ignores_future_and_inactive(owner):
    meds = [
        {
            "id": "a",
            "name": "A",
            "status": "active",
            "times": ["08:00", "21:00"],
            "start_date": "2026-11-15",
            "end_date": None,
        },
        {
            "id": "b",
            "name": "B",
            "status": "paused",
            "times": ["08:00"],
            "start_date": "2026-11-01",
            "end_date": None,
        },
    ]
    now = datetime(2026, 11, 15, 10, 0, tzinfo=IST)
    result = schedule.adherence(meds, [], now, days=7)
    assert result["scheduled"] == 1  # Only A at 08:00 today; B is paused; 21:00 is still ahead.
    assert result["percent"] == 0.0


def test_end_date_limits_schedule():
    med = {
        "id": "a",
        "name": "A",
        "status": "active",
        "times": ["08:00"],
        "start_date": "2026-11-01",
        "end_date": "2026-11-05",
    }
    day = datetime(2026, 11, 6, tzinfo=IST).date()
    assert schedule.doses_for_day([med], day) == []
    assert len(schedule.doses_for_day([med], day - timedelta(days=1))) == 1
