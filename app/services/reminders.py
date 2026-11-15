"""Reminder engine: decides which emails are due and records missed doses.

``plan`` is pure (no I/O) and fully unit-tested. ``run`` loads each care profile,
sends what ``plan`` decides, and records every notification so nothing is sent twice.
It is triggered every 15 minutes by a scheduler calling POST /internal/run-reminders.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from app.clock import from_iso_utc, local_now, to_iso_utc
from app.db import paths
from app.db.base import Repository
from app.services import audit, schedule
from app.services.emailer import Email, Emailer

FOOTER = (
    "\n\n—\nCareSync keeps the whole care circle informed. "
    "It supports care decisions but does not replace advice from a doctor or pharmacist."
)


@dataclass(frozen=True)
class Notification:
    id: str
    kind: str  # dose.upcoming | dose.missed | appointment.24h | appointment.2h
    to: list[str]
    subject: str
    body: str
    audit_summary: str


@dataclass
class Plan:
    notifications: list[Notification] = field(default_factory=list)
    missed_logs: list[dict[str, Any]] = field(default_factory=list)


def _fmt(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def _emails(members: list[dict[str, Any]], *roles: str) -> list[str]:
    return sorted({m["email"] for m in members if m.get("active") and m["role"] in roles})


def plan(
    elder: dict[str, Any],
    members: list[dict[str, Any]],
    meds: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    appointments: list[dict[str, Any]],
    already_sent: set[str],
    now_utc: datetime,
    grace_minutes: int = 30,
    lead_minutes: int = 15,
) -> Plan:
    result = Plan()
    now = local_now(now_utc, elder["timezone"])
    first = elder["name"].split()[0]
    logged = {log["id"] for log in logs}
    elder_email = _emails(members, "elder")
    circle = _emails(members, "caretaker", "family")
    grace, lead = timedelta(minutes=grace_minutes), timedelta(minutes=lead_minutes)

    for day in (now.date() - timedelta(days=1), now.date()):
        for med, at in schedule.doses_for_day(meds, day):
            h, m = (int(x) for x in at.split(":"))
            due = datetime(day.year, day.month, day.day, h, m, tzinfo=now.tzinfo)
            if med.get("created_at") and due < from_iso_utc(med["created_at"]):
                continue  # Doses due before the medicine was added to CareSync can't be "missed".
            dose = schedule.dose_id(med["id"], day, at)
            what = f"{med['name']} {med['dosage']}"
            how = f" ({med['instructions']})" if med.get("instructions") else ""

            if now < due <= now + lead and f"upcoming:{dose}" not in already_sent:
                result.notifications.append(
                    Notification(
                        f"upcoming:{dose}",
                        "dose.upcoming",
                        elder_email + _emails(members, "caretaker"),
                        f"Reminder: {what} at {_fmt(at)}",
                        f"Hello {first},\n\nIt's almost time for {what} at {_fmt(at)}{how}.\n"
                        "Open CareSync and tap “I took it” once you've taken it." + FOOTER,
                        f"Emailed a reminder for {med['name']} at {_fmt(at)}",
                    )
                )

            if dose not in logged and due + grace <= now and now - due <= timedelta(hours=24):
                result.missed_logs.append(
                    {
                        "id": dose,
                        "medication_id": med["id"],
                        "medication_name": med["name"],
                        "date": day.isoformat(),
                        "time": at,
                        "status": "missed",
                        "logged_by_id": "system",
                        "logged_by_name": "CareSync",
                        "logged_at": to_iso_utc(now_utc),
                    }
                )
                if f"missed:{dose}" not in already_sent:
                    when = "today" if day == now.date() else "yesterday"
                    result.notifications.append(
                        Notification(
                            f"missed:{dose}",
                            "dose.missed",
                            circle + elder_email,
                            f"Missed dose: {first}'s {med['name']} at {_fmt(at)}",
                            f"{first}'s {what} scheduled for {_fmt(at)} {when} "
                            "has not been marked as taken.\n\n"
                            f"If {first} has taken it, it can still be recorded in CareSync. "
                            f"Otherwise, a quick call to {first} may help. "
                            "Do not give a double dose without checking with a doctor or pharmacist."
                            + FOOTER,
                            f"Emailed a missed-dose alert for {med['name']} at {_fmt(at)} ({when})",
                        )
                    )

    for appt in appointments:
        starts = from_iso_utc(appt["starts_at"])
        hours = (starts - now_utc).total_seconds() / 3600
        if hours <= 0:
            continue
        key = f"{appt['id']}:{appt['starts_at']}"  # A rescheduled appointment gets fresh reminders.
        window = "2h" if hours <= 2 else "24h" if hours <= 24 else None
        if window is None or f"appointment.{window}:{key}" in already_sent:
            continue
        if window == "24h" and f"appointment.2h:{key}" in already_sent:
            continue
        local = starts.astimezone(now.tzinfo)
        when = f"{local.strftime('%A %d %B')} at {_fmt(local.strftime('%H:%M'))}"
        place = f"\nWhere: {appt['location']}" if appt.get("location") else ""
        notes = f"\nNotes: {appt['notes']}" if appt.get("notes") else ""
        day_label = (
            "Today"
            if local.date() == now.date()
            else "Tomorrow"
            if local.date() == now.date() + timedelta(days=1)
            else local.strftime("%A")
        )
        result.notifications.append(
            Notification(
                f"appointment.{window}:{key}",
                f"appointment.{window}",
                elder_email + circle,
                f"{day_label}: {first}'s appointment with {appt['doctor']}",
                f"Reminder: {first} has an appointment with {appt['doctor']}"
                f"{' (' + appt['specialty'] + ')' if appt.get('specialty') else ''}.\n\n"
                f"When: {when}{place}{notes}\n\n"
                "Bring the list of current medicines and any questions for the doctor." + FOOTER,
                f"Emailed a reminder for the appointment with {appt['doctor']} ({window} before)",
            )
        )
    return result


def run(repo: Repository, emailer: Emailer, now_utc: datetime, grace_minutes: int, lead_minutes: int) -> dict:
    """Process every care profile once. Returns counts for monitoring."""
    totals = {"profiles": 0, "emails_sent": 0, "emails_failed": 0, "missed_recorded": 0}
    for elder in repo.list(paths.ELDERS):
        totals["profiles"] += 1
        eid = elder["id"]
        today = local_now(now_utc, elder["timezone"]).date()
        since: date = today - timedelta(days=1)
        horizon = to_iso_utc(now_utc + timedelta(hours=25))
        appointments = [
            a
            for a in repo.list(paths.appointments(eid), [("starts_at", ">=", to_iso_utc(now_utc))])
            if a["starts_at"] <= horizon
        ]
        result = plan(
            elder,
            repo.list(paths.members(eid), [("active", "==", True)]),
            repo.list(paths.medications(eid)),
            repo.list(paths.dose_logs(eid), [("date", ">=", since.isoformat())]),
            appointments,
            already_sent={
                n["id"] for n in repo.list(paths.notifications(eid), [("date", ">=", since.isoformat())])
            },
            now_utc=now_utc,
            grace_minutes=grace_minutes,
            lead_minutes=lead_minutes,
        )
        for log in result.missed_logs:
            repo.set(paths.dose_logs(eid), log["id"], {k: v for k, v in log.items() if k != "id"})
            totals["missed_recorded"] += 1
        for note in result.notifications:
            if not note.to:
                continue
            ok = emailer.send(Email(note.to, note.subject, note.body))
            totals["emails_sent" if ok else "emails_failed"] += 1
            if ok:
                repo.set(
                    paths.notifications(eid),
                    note.id,
                    {
                        "kind": note.kind,
                        "date": today.isoformat(),
                        "sent_at": to_iso_utc(now_utc),
                        "recipients": len(note.to),
                    },
                )
                audit.record(
                    repo,
                    eid,
                    None,
                    f"notify.{note.kind}",
                    f"{note.audit_summary} to {len(note.to)} {'person' if len(note.to) == 1 else 'people'}",
                    now_utc,
                    note.id,
                )
    return totals


def invite_email(
    member_name: str, elder_name: str, care_code: str, email: str, passcode: str, app_url: str
) -> Email:
    return Email(
        [email],
        f"{elder_name} added you to their CareSync care circle",
        f"Hello {member_name},\n\n{elder_name} has invited you to their CareSync care circle, "
        "so you can stay informed about their medicines and appointments.\n\n"
        f"Sign in at: {app_url}\nCare Code: {care_code}\nEmail: {email}\nPasscode: {passcode}\n\n"
        "Please change your passcode after signing in. If you weren't expecting this, you can ignore it."
        + FOOTER,
    )
