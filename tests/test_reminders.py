"""Tests for the reminder engine, scheduled endpoint and notification emails."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import reminders
from app.services.emailer import OutboxEmailer
from tests.conftest import ELDER, MED, FakeClock, add_member, make_settings

ELDER_DOC = {"id": "e1", "name": "Kamala Iyer", "timezone": "Asia/Kolkata"}
MEMBERS = [
    {"id": "o", "email": "kamala@example.com", "role": "elder", "active": True},
    {"id": "c", "email": "nurse@example.com", "role": "caretaker", "active": True},
    {"id": "f", "email": "son@example.com", "role": "family", "active": True},
    {"id": "x", "email": "removed@example.com", "role": "family", "active": False},
]
MED_DOC = {
    "id": "m1",
    "name": "Metformin",
    "dosage": "500 mg",
    "instructions": "After food",
    "times": ["08:00", "20:00"],
    "start_date": "2026-11-15",
    "end_date": None,
    "status": "active",
}


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    """IST wall-clock time on Nov `day`, as UTC."""
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC) - timedelta(hours=5, minutes=30)


def run_plan(now, logs=(), appointments=(), sent=()):
    return reminders.plan(ELDER_DOC, MEMBERS, [MED_DOC], list(logs), list(appointments), set(sent), now)


# ---------- plan: doses ----------


def test_upcoming_dose_reminder_goes_to_elder_and_caretaker():
    result = run_plan(utc(15, 7, 50))  # 07:50 IST, Metformin at 08:00.
    upcoming = [n for n in result.notifications if n.kind == "dose.upcoming"]
    assert len(upcoming) == 1
    assert upcoming[0].to == ["kamala@example.com", "nurse@example.com"]
    assert "8:00 AM" in upcoming[0].subject and "After food" in upcoming[0].body


def test_no_reminder_outside_window_or_when_already_sent():
    assert not [n for n in run_plan(utc(15, 7, 30)).notifications if n.kind == "dose.upcoming"]
    sent = {"upcoming:m1_2026-11-15_0800"}
    assert not [n for n in run_plan(utc(15, 7, 50), sent=sent).notifications if n.kind == "dose.upcoming"]


def test_missed_dose_recorded_and_circle_alerted():
    result = run_plan(utc(15, 8, 45))  # 45 minutes late, past the 30-minute grace.
    assert [log["id"] for log in result.missed_logs] == ["m1_2026-11-15_0800"]
    assert result.missed_logs[0]["status"] == "missed"
    alert = next(n for n in result.notifications if n.kind == "dose.missed")
    assert alert.to == ["nurse@example.com", "son@example.com", "kamala@example.com"]
    assert "removed@example.com" not in alert.to  # Removed members get nothing.
    assert "double dose" in alert.body


def test_taken_dose_is_not_missed():
    logs = [{"id": "m1_2026-11-15_0800", "status": "taken"}]
    result = run_plan(utc(15, 9, 0), logs=logs)
    assert not result.missed_logs and not result.notifications


def test_yesterdays_evening_dose_is_caught_after_midnight():
    result = run_plan(utc(16, 0, 30))
    assert "m1_2026-11-15_2000" in [log["id"] for log in result.missed_logs]


def test_doses_before_medicine_was_added_are_not_missed():
    backdated = {**MED_DOC, "start_date": "2026-11-01", "created_at": "2026-11-15T03:00:00Z"}  # 08:30 IST
    result = reminders.plan(ELDER_DOC, MEMBERS, [backdated], [], [], set(), utc(15, 9, 0))
    assert result.missed_logs == []  # 08:00 today and yesterday's doses predate the entry.


def test_paused_medicine_never_reminds():
    paused = {**MED_DOC, "status": "paused"}
    result = reminders.plan(ELDER_DOC, MEMBERS, [paused], [], [], set(), utc(15, 9, 0))
    assert not result.notifications and not result.missed_logs


# ---------- plan: appointments ----------


def appt(starts: datetime, appt_id="a1"):
    return {
        "id": appt_id,
        "doctor": "Dr. Mehta",
        "specialty": "Cardiology",
        "location": "Apollo Clinic",
        "notes": "Bring ECG",
        "starts_at": starts.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@pytest.mark.parametrize(("hours_before", "kind"), [(20, "appointment.24h"), (1.5, "appointment.2h")])
def test_appointment_reminder_windows(hours_before, kind):
    starts = utc(16, 11)
    result = run_plan(starts - timedelta(hours=hours_before), appointments=[appt(starts)], logs=_all_taken())
    notes = [n for n in result.notifications if n.kind.startswith("appointment")]
    assert [n.kind for n in notes] == [kind]
    assert "Apollo Clinic" in notes[0].body and len(notes[0].to) == 3


def test_appointment_reminders_are_not_repeated_and_reset_on_reschedule():
    starts = utc(16, 11)
    a = appt(starts)
    key = f"appointment.24h:a1:{a['starts_at']}"
    now = starts - timedelta(hours=20)
    assert not [n for n in run_plan(now, appointments=[a], sent={key}, logs=_all_taken()).notifications]
    moved = appt(starts + timedelta(hours=1))
    assert [
        n.kind for n in run_plan(now, appointments=[moved], sent={key}, logs=_all_taken()).notifications
    ] == ["appointment.24h"]


def test_far_appointments_wait():
    starts = utc(18, 11)
    assert not run_plan(utc(15, 9), appointments=[appt(starts)], logs=_all_taken()).notifications


def _all_taken():
    return [{"id": f"m1_2026-11-{d}_{t}", "status": "taken"} for d in (14, 15, 16) for t in ("0800", "2000")]


# ---------- endpoint + integration ----------


@pytest.fixture
def mail_app(repo):
    clock = FakeClock(utc(15, 7, 50))
    outbox = OutboxEmailer(enabled=True)
    app = create_app(
        settings=make_settings(cron_secret="cron-secret-123"), repo=repo, clock=clock, emailer=outbox
    )
    return app, clock, outbox


def test_run_endpoint_requires_secret(mail_app):
    app, _, _ = mail_app
    c = TestClient(app)
    assert c.post("/internal/run-reminders").status_code == 403
    assert c.post("/internal/run-reminders", headers={"X-Cron-Secret": "wrong"}).status_code == 403


def test_run_endpoint_disabled_without_secret(client):
    assert client.post("/internal/run-reminders", headers={"X-Cron-Secret": "x"}).status_code == 503


def test_end_to_end_reminders(mail_app):
    app, clock, outbox = mail_app
    owner = TestClient(app)
    owner.post("/api/profiles", json=ELDER)
    owner.post("/api/medications", json={**MED, "times": ["08:00"]})
    add_member(owner, app, "family", "son@example.com")
    outbox.outbox.clear()  # Ignore the invite email.
    headers = {"X-Cron-Secret": "cron-secret-123"}

    first = owner.post("/internal/run-reminders", headers=headers).json()
    assert first["emails_sent"] == 1 and "Reminder: Metformin" in outbox.outbox[-1].subject
    assert owner.post("/internal/run-reminders", headers=headers).json()["emails_sent"] == 0  # No duplicates.

    clock.now = utc(15, 8, 45)
    missed = owner.post("/internal/run-reminders", headers=headers).json()
    assert missed["missed_recorded"] == 1 and missed["emails_sent"] == 1
    assert "son@example.com" in outbox.outbox[-1].to
    today = owner.get("/api/doses/today").json()["doses"]
    assert today[0]["status"] == "missed"
    actions = [a["action"] for a in owner.get("/api/activity").json()]
    assert "notify.dose.missed" in actions

    # A missed dose can still be recorded as taken afterwards.
    med_id = today[0]["medication_id"]
    res = owner.post("/api/doses", json={"medication_id": med_id, "time": "08:00", "status": "taken"})
    assert res.status_code == 201


def test_invite_email_contains_sign_in_details(mail_app):
    app, _, outbox = mail_app
    owner = TestClient(app)
    owner.post("/api/profiles", json=ELDER)
    res = owner.post(
        "/api/members", json={"name": "Ravi", "email": "ravi@example.com", "role": "family"}
    ).json()
    assert res["emailed"] is True
    email = outbox.outbox[-1]
    assert email.to == ["ravi@example.com"]
    assert res["care_code"] in email.body and res["passcode"] in email.body


def test_test_email_endpoint(mail_app, client):
    app, _, outbox = mail_app
    owner = TestClient(app)
    owner.post("/api/profiles", json=ELDER)
    assert owner.get("/api/notifications/status").json() == {"email_enabled": True}
    assert owner.post("/api/notifications/test").json()["to"] == "kamala@example.com"
    assert outbox.outbox[-1].subject == "CareSync test email"
    # Without email configured, the endpoint explains instead of failing silently.
    client.post("/api/profiles", json=ELDER)
    assert client.post("/api/notifications/test").status_code == 503


def test_failed_delivery_is_not_marked_sent(repo):
    class FailingEmailer:
        enabled = True

        def send(self, email):
            return False

    clock = FakeClock(utc(15, 7, 50))
    app = create_app(
        settings=make_settings(cron_secret="s"), repo=repo, clock=clock, emailer=FailingEmailer()
    )
    c = TestClient(app)
    c.post("/api/profiles", json=ELDER)
    c.post("/api/medications", json={**MED, "times": ["08:00"]})
    first = c.post("/internal/run-reminders", headers={"X-Cron-Secret": "s"}).json()
    assert first["emails_failed"] == 1
    # Retried on the next run because it was never recorded as sent.
    assert c.post("/internal/run-reminders", headers={"X-Cron-Secret": "s"}).json()["emails_failed"] == 1
