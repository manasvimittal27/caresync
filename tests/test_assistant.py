"""Tests for the Smart Care Assistant decision engine and its endpoints."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import assistant, schedule
from app.services.ai import AIUnavailableError
from tests.conftest import ELDER, MED, add_member, make_settings

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 15, 10, 0, tzinfo=IST)  # Sunday 10:00 IST


def med(med_id="m1", name="Metformin", times=("08:00",), start="2026-11-01", end=None, status="active"):
    return {
        "id": med_id,
        "name": name,
        "dosage": "500 mg",
        "instructions": "After food",
        "times": list(times),
        "start_date": start,
        "end_date": end,
        "status": status,
    }


def taken(m, day: date, at: str, status="taken"):
    return {"id": schedule.dose_id(m["id"], day, at), "date": day.isoformat(), "time": at, "status": status}


def ctx(**overrides) -> assistant.CareContext:
    base = dict(
        role="elder",
        viewer_name="Kamala Iyer",
        elder_name="Kamala Iyer",
        allergies=[],
        now_local=NOW,
        meds=[],
        logs=[],
        appointments=[],
        member_count=2,
    )
    return assistant.CareContext(**{**base, **overrides})


def ids(c: assistant.CareContext) -> list[str]:
    return [i.id for i in assistant.build_insights(c)]


def by_id(c: assistant.CareContext, insight_id: str) -> assistant.Insight:
    return next(i for i in assistant.build_insights(c) if i.id == insight_id)


# ---------- dose rules ----------


def test_overdue_dose_is_urgent_and_worded_for_the_elder():
    m = med()
    insight = by_id(ctx(meds=[m]), "dose:overdue")
    assert insight.priority == "urgent"
    assert "Did you take" in insight.title
    assert insight.action_href == "#/today"


def test_overdue_dose_wording_changes_by_role():
    m = med()
    caretaker = by_id(ctx(meds=[m], role="caretaker", viewer_name="Nurse"), "dose:overdue")
    family = by_id(ctx(meds=[m], role="family", viewer_name="Ravi"), "dose:overdue")
    assert "Kamala may have missed" in caretaker.title and caretaker.priority == "urgent"
    assert family.priority == "high" and family.action_href is None  # Family can't record doses.
    assert "call" in family.message


def test_due_dose_inside_grace_window():
    m = med(times=("09:45",))
    insight = by_id(ctx(meds=[m]), "dose:due")
    assert insight.title == "Time for your medicine"
    assert "Metformin 500 mg (After food)" in insight.message


def test_all_doses_done_is_celebrated():
    m = med()
    c = ctx(meds=[m], logs=[taken(m, NOW.date(), "08:00")])
    assert "dose:all-done" in ids(c)
    assert "dose:overdue" not in ids(c)


# ---------- adherence rules ----------


def test_missed_pattern_detected_for_a_time_slot():
    m = med(times=("08:00", "21:00"))
    logs = []
    for offset in range(1, 7):
        day = NOW.date() - timedelta(days=offset)
        logs.append(taken(m, day, "08:00"))
        if offset % 3 == 0:  # Evening dose taken only twice in six days.
            logs.append(taken(m, day, "21:00"))
    c = ctx(meds=[m], logs=logs + [taken(m, NOW.date(), "08:00")])
    insight = by_id(c, "pattern:m1:21:00")
    assert insight.priority == "high"
    assert "9:00 PM Metformin is often missed" in insight.title
    assert "Missed 4 of the last 6" in insight.reason
    assert not any(i.startswith("pattern:m1:08:00") for i in ids(c))


def test_skipped_doses_are_not_counted_as_lapses():
    m = med()
    logs = [taken(m, NOW.date() - timedelta(days=d), "08:00", status="skipped") for d in range(0, 6)]
    assert assistant.missed_patterns(ctx(meds=[m], logs=logs)) == []


def test_adherence_drop_week_over_week():
    m = med()
    logs = [taken(m, NOW.date() - timedelta(days=d), "08:00") for d in range(7, 14)]  # Perfect last week.
    logs += [taken(m, NOW.date() - timedelta(days=d), "08:00") for d in (0, 1, 2)]  # 3/7 this week.
    insight = by_id(ctx(meds=[m], logs=logs), "adherence:drop")
    assert "100% to 43%" in insight.message
    assert "previous week: 100%" in insight.reason


def test_great_adherence_gets_encouragement():
    m = med()
    logs = [taken(m, NOW.date() - timedelta(days=d), "08:00") for d in range(0, 7)]
    insight = by_id(ctx(meds=[m], logs=logs), "adherence:great")
    assert insight.priority == "low" and "100%" in insight.title


def test_new_medicine_does_not_trigger_adherence_alerts():
    m = med(start=NOW.date().isoformat())
    assert not any(i.startswith("adherence:") for i in ids(ctx(meds=[m])))


# ---------- safety rules ----------


@pytest.mark.parametrize(
    ("allergy", "medicine"),
    [
        ("Penicillin", "Amoxicillin"),
        ("penicillin", "Augmentin 625"),
        ("Sulfa", "Bactrim DS"),
        ("Aspirin", "Ibuprofen"),
    ],
)
def test_allergy_family_conflicts_are_urgent(allergy, medicine):
    m = med(name=medicine)
    insight = by_id(ctx(meds=[m], allergies=[allergy]), "safety:allergy:m1")
    assert insight.priority == "urgent"
    assert allergy in insight.message


def test_no_false_allergy_alarm():
    assert not any(i.startswith("safety:") for i in ids(ctx(meds=[med()], allergies=["Penicillin"])))


def test_duplicate_active_medicine_flagged():
    meds = [med("a", "Metformin"), med("b", "metformin ")]
    assert "safety:duplicate:metformin" in ids(ctx(meds=meds))


def test_course_ending_soon():
    m = med(end=(NOW.date() + timedelta(days=2)).isoformat())
    insight = by_id(ctx(meds=[m]), "course:ending:m1")
    assert insight.title == "Metformin course ends in 2 days"


# ---------- appointments ----------


def appt(hours_ahead: float):
    starts = (NOW + timedelta(hours=hours_ahead)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"id": "a1", "doctor": "Dr. Mehta", "starts_at": starts, "location": "Apollo Clinic"}


@pytest.mark.parametrize(("hours", "priority"), [(2, "urgent"), (20, "high"), (40, "medium")])
def test_appointment_priority_depends_on_how_soon(hours, priority):
    insight = by_id(ctx(meds=[med()], appointments=[appt(hours)]), "appointment:a1")
    assert insight.priority == priority
    assert "Metformin" in insight.message  # Preparation tip lists current medicines.


def test_far_appointments_are_not_mentioned():
    assert "appointment:a1" not in ids(ctx(appointments=[appt(72)]))


# ---------- care circle and setup ----------


def test_pending_approvals_for_elder_and_caretaker():
    pending = med(status="pending")
    assert by_id(ctx(meds=[pending]), "approval:pending").priority == "high"
    assert "approval:waiting" in ids(ctx(meds=[pending], role="caretaker"))
    assert not any(i.startswith("approval") for i in ids(ctx(meds=[pending], role="family")))


def test_setup_nudges():
    c = ctx(member_count=1)
    assert {"setup:first-medicine", "circle:invite"} <= set(ids(c))
    assert "setup:first-medicine" not in ids(ctx(role="family"))


def test_insights_sorted_by_priority_and_capped():
    meds = [med(f"m{i}", f"Med{i}", end=(NOW.date() + timedelta(days=1)).isoformat()) for i in range(10)]
    insights = assistant.build_insights(ctx(meds=meds, allergies=[]))
    order = [assistant.PRIORITY_ORDER[i.priority] for i in insights]
    assert order == sorted(order)
    assert len(insights) <= assistant.MAX_INSIGHTS


def test_headline():
    m = med(times=("20:00",))
    assert assistant.summarise(ctx(meds=[m]))["headline"] == "Next: Metformin 500 mg at 8:00 PM"
    assert assistant.summarise(ctx(meds=[med()]))["headline"] == "1 thing needs attention now"


def test_context_brief_contains_no_contact_details():
    brief = assistant.context_brief(ctx(meds=[med()], allergies=["Penicillin"]))
    assert "Kamala" in brief and "Penicillin" in brief and "Metformin 500 mg at 08:00" in brief
    assert "@" not in brief and "Iyer" not in brief  # First name only, no emails.


# ---------- endpoints ----------


def test_assistant_endpoint(owner):
    c, _ = owner
    c.post("/api/medications", json=MED)
    body = c.get("/api/assistant").json()
    assert body["ai_enabled"] is False
    assert body["insights"][0]["priority"] == "urgent"  # 08:00 dose is overdue at 10:00.
    assert {"id", "title", "message", "reason"} <= set(body["insights"][0])


def test_assistant_requires_sign_in(client):
    assert client.get("/api/assistant").status_code == 401


def test_ask_disabled_without_api_key(owner):
    c, _ = owner
    assert c.post("/api/assistant/ask", json={"question": "Can I take it with tea?"}).status_code == 503


class FakeModel:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def answer(self, question: str, context: str) -> str:
        self.calls.append((question, context))
        if self.fail:
            raise AIUnavailableError("The assistant is unavailable right now.")
        return "Take it after food, and check with your doctor."


def ai_client(repo, clock, model):
    app = create_app(settings=make_settings(), repo=repo, clock=clock, ai=model)
    c = TestClient(app)
    c.post("/api/profiles", json=ELDER)
    return app, c


def test_ask_uses_model_with_safe_context(repo, clock):
    model = FakeModel()
    _, c = ai_client(repo, clock, model)
    c.post("/api/medications", json=MED)
    res = c.post("/api/assistant/ask", json={"question": "When should I take Metformin?"})
    assert res.status_code == 200
    assert "doctor" in res.json()["answer"] and "not medical advice" in res.json()["disclaimer"]
    question, context = model.calls[0]
    assert "Metformin" in context and "kamala@example.com" not in context
    assert c.get("/api/assistant").json()["ai_enabled"] is True


def test_ask_validation_rate_limit_and_failure(repo, clock):
    _, c = ai_client(repo, clock, FakeModel())
    assert c.post("/api/assistant/ask", json={"question": "x"}).status_code == 422
    for _ in range(10):
        assert c.post("/api/assistant/ask", json={"question": "Is this ok?"}).status_code == 200
    assert c.post("/api/assistant/ask", json={"question": "Is this ok?"}).status_code == 429

    _, failing = ai_client(repo, clock, FakeModel(fail=True))
    assert failing.post("/api/assistant/ask", json={"question": "Is this ok?"}).status_code == 502


def test_family_sees_family_wording(app, owner):
    c, _ = owner
    c.post("/api/medications", json=MED)
    family = add_member(c, app, "family", "son@example.com")
    first = family.get("/api/assistant").json()["insights"][0]
    assert first["title"] == "Kamala may have missed a dose"
