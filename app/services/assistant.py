"""Smart Care Assistant: a context-aware decision engine.

Looks at who is asking (role), the time of day, today's doses, adherence trends,
missed-dose patterns, allergies, medicine end dates, upcoming appointments and
pending approvals, then returns prioritised, explained next steps.

Pure functions with no I/O, so every rule is deterministic and unit-tested.
Each insight carries a ``reason`` so users can see *why* it was suggested.
"""

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.clock import from_iso_utc
from app.services import schedule

PRIORITY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
MAX_INSIGHTS = 8

# Medicines that commonly cross-react with a listed allergy (keyword match, lower case).
ALLERGY_FAMILIES: dict[str, set[str]] = {
    "penicillin": {"penicillin", "amoxicillin", "ampicillin", "augmentin", "piperacillin", "cloxacillin"},
    "sulfa": {"sulfamethoxazole", "bactrim", "septran", "sulfasalazine", "sulfadiazine"},
    "aspirin": {"aspirin", "ibuprofen", "naproxen", "diclofenac", "ecosprin"},
    "nsaid": {"ibuprofen", "naproxen", "diclofenac", "aspirin", "ketorolac"},
    "codeine": {"codeine", "morphine", "tramadol"},
    "cephalosporin": {"cefalexin", "cephalexin", "cefuroxime", "ceftriaxone", "cefixime"},
}


@dataclass(frozen=True)
class Insight:
    id: str
    priority: str  # urgent | high | medium | low
    category: str  # dose | adherence | safety | appointment | care-circle | encouragement | setup
    title: str
    message: str
    reason: str
    action_label: str | None = None
    action_href: str | None = None


@dataclass(frozen=True)
class CareContext:
    role: str  # elder | caretaker | family
    viewer_name: str
    elder_name: str
    allergies: list[str]
    now_local: datetime
    meds: list[dict[str, Any]]
    logs: list[dict[str, Any]]  # dose logs for at least the last 14 days
    appointments: list[dict[str, Any]]  # upcoming appointments (UTC ISO starts_at)
    member_count: int
    grace_minutes: int = 30

    @property
    def is_elder(self) -> bool:
        return self.role == "elder"

    @property
    def can_edit(self) -> bool:
        return self.role in ("elder", "caretaker")

    @property
    def first_name(self) -> str:
        return self.elder_name.split()[0] if self.elder_name else "them"

    def subject(self, possessive: bool = False) -> str:
        """'you'/'your' for the elder, the elder's first name for everyone else."""
        if self.is_elder:
            return "your" if possessive else "you"
        return f"{self.first_name}'s" if possessive else self.first_name


# ---------------------------------------------------------------- helpers


def _fmt_time(hhmm: str) -> str:
    hours, minutes = (int(x) for x in hhmm.split(":"))
    return f"{hours % 12 or 12}:{minutes:02d} {'AM' if hours < 12 else 'PM'}"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" and {items[-1]}"


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def _today_schedule(ctx: CareContext) -> list[dict[str, Any]]:
    today = ctx.now_local.date()
    todays_logs = [log for log in ctx.logs if log.get("date") == today.isoformat()]
    return schedule.day_schedule(ctx.meds, todays_logs, today, ctx.now_local, ctx.grace_minutes)


def _routine_tip(hhmm: str) -> str:
    hour = int(hhmm.split(":")[0])
    if hour < 11:
        return "Keeping the strip next to the toothbrush or breakfast table often helps."
    if hour < 17:
        return "Pairing it with lunch or setting a phone alarm often helps."
    return "Linking it to dinner, or asking the doctor whether it can be taken earlier, often helps."


# ---------------------------------------------------------------- rules


def _dose_rules(ctx: CareContext, today: list[dict[str, Any]]) -> list[Insight]:
    insights: list[Insight] = []
    overdue = [d for d in today if d["status"] == "overdue"]
    due = [d for d in today if d["status"] == "due"]

    if overdue:
        names = [f"{d['name']} ({_fmt_time(d['time'])})" for d in overdue]
        reason = f"Not marked as taken more than {ctx.grace_minutes} minutes after the scheduled time."
        if ctx.is_elder:
            insights.append(
                Insight(
                    "dose:overdue",
                    "urgent",
                    "dose",
                    "Did you take these medicines?",
                    f"{_join(names)} {'is' if len(names) == 1 else 'are'} not marked yet. "
                    "If you took it, tap “I took it” so your family isn't worried.",
                    reason,
                    "Mark doses",
                    "#/today",
                )
            )
        elif ctx.role == "caretaker":
            insights.append(
                Insight(
                    "dose:overdue",
                    "urgent",
                    "dose",
                    f"{ctx.first_name} may have missed a dose",
                    f"{_join(names)} {'is' if len(names) == 1 else 'are'} not marked as taken. "
                    f"Please check with {ctx.first_name} and record it.",
                    reason,
                    "Record dose",
                    "#/today",
                )
            )
        else:
            insights.append(
                Insight(
                    "dose:overdue",
                    "high",
                    "dose",
                    f"{ctx.first_name} may have missed a dose",
                    f"{_join(names)} {'is' if len(names) == 1 else 'are'} not marked as taken. "
                    f"A quick call to {ctx.first_name} might help.",
                    reason,
                )
            )

    if due:
        items = [
            f"{d['name']} {d['dosage']}" + (f" ({d['instructions']})" if d.get("instructions") else "")
            for d in due
        ]
        title = "Time for your medicine" if ctx.is_elder else f"{ctx.first_name}'s medicine is due now"
        insights.append(
            Insight(
                "dose:due",
                "high",
                "dose",
                title,
                f"{_join(items)}.",
                "Scheduled within the last few minutes.",
                "Mark as taken" if ctx.can_edit else None,
                "#/today" if ctx.can_edit else None,
            )
        )

    if today and all(d["status"] in ("taken", "skipped") for d in today):
        insights.append(
            Insight(
                "dose:all-done",
                "low",
                "encouragement",
                "All of today's medicines are done",
                "Well done!" if ctx.is_elder else f"{ctx.first_name} is all set for today.",
                f"All {len(today)} scheduled doses today are recorded.",
            )
        )
    return insights


def missed_patterns(ctx: CareContext, days: int = 7) -> list[dict[str, Any]]:
    """Dose slots (medicine + time) that were not taken repeatedly in the recent past."""
    taken_ids = {log["id"] for log in ctx.logs if log.get("status") == "taken"}
    skipped_ids = {log["id"] for log in ctx.logs if log.get("status") == "skipped"}
    grace = timedelta(minutes=ctx.grace_minutes)
    slots: dict[tuple[str, str], dict[str, Any]] = {}
    today = ctx.now_local.date()
    for offset in range(days):
        day = today - timedelta(days=offset)
        for med, at in schedule.doses_for_day(ctx.meds, day):
            hours, minutes = (int(x) for x in at.split(":"))
            due_at = datetime(day.year, day.month, day.day, hours, minutes, tzinfo=ctx.now_local.tzinfo)
            if due_at + grace > ctx.now_local:
                continue  # Still within its window.
            dose = schedule.dose_id(med["id"], day, at)
            if dose in skipped_ids:
                continue  # A deliberate skip is a decision, not a lapse.
            slot = slots.setdefault((med["id"], at), {"med": med, "time": at, "due": 0, "missed": 0})
            slot["due"] += 1
            if dose not in taken_ids:
                slot["missed"] += 1
    return [s for s in slots.values() if s["due"] >= 3 and s["missed"] >= 2]


def _pattern_rules(ctx: CareContext) -> list[Insight]:
    insights = []
    for slot in missed_patterns(ctx):
        med, at = slot["med"], slot["time"]
        whose = ctx.subject(possessive=True)
        insights.append(
            Insight(
                f"pattern:{med['id']}:{at}",
                "high",
                "adherence",
                f"The {_fmt_time(at)} {med['name']} is often missed",
                f"{whose.capitalize()} {_fmt_time(at)} dose was missed {slot['missed']} times recently. "
                + _routine_tip(at),
                f"Missed {slot['missed']} of the last {slot['due']} scheduled {_fmt_time(at)} doses.",
                "Adjust schedule" if ctx.can_edit else None,
                "#/medicines" if ctx.can_edit else None,
            )
        )
    return insights


def _adherence_rules(ctx: CareContext) -> list[Insight]:
    this_week = schedule.adherence(ctx.meds, ctx.logs, ctx.now_local, 7)
    last_week = schedule.adherence(ctx.meds, ctx.logs, ctx.now_local - timedelta(days=7), 7)
    pct, prev = this_week["percent"], last_week["percent"]
    if pct is None or this_week["scheduled"] < 3:
        return []

    insights = []
    reason = f"{this_week['taken']} of {this_week['scheduled']} doses taken in the last 7 days"
    if prev is not None and last_week["scheduled"] >= 3:
        reason += f" (previous week: {round(prev)}%)"
    reason += "."

    if prev is not None and last_week["scheduled"] >= 3 and prev - pct >= 15:
        insights.append(
            Insight(
                "adherence:drop",
                "high",
                "adherence",
                "Medicine routine has slipped this week",
                f"{ctx.subject(possessive=True).capitalize()} doses taken fell "
                f"from {round(prev)}% to {round(pct)}%. "
                + (
                    "Is anything making it harder, like side effects or a busy routine?"
                    if ctx.is_elder
                    else f"It may be worth checking in with {ctx.first_name}."
                ),
                reason,
            )
        )
    elif pct < 80:
        insights.append(
            Insight(
                "adherence:low",
                "high",
                "adherence",
                f"Only {round(pct)}% of doses taken this week",
                "Missing doses can make treatment less effective. "
                + (
                    "Turning on reminders or asking family to help could make it easier."
                    if ctx.is_elder
                    else f"Consider setting up a daily check-in with {ctx.first_name}."
                ),
                reason,
            )
        )
    elif pct >= 90 and this_week["scheduled"] >= 5:
        insights.append(
            Insight(
                "adherence:great",
                "low",
                "encouragement",
                f"Great consistency: {round(pct)}% this week",
                "Keep it up!" if ctx.is_elder else f"{ctx.first_name} is staying on track.",
                reason,
            )
        )
    return insights


def allergy_conflicts(meds: list[dict[str, Any]], allergies: list[str]) -> list[tuple[dict[str, Any], str]]:
    conflicts = []
    for allergy in allergies:
        key = allergy.strip().lower()
        if not key:
            continue
        keywords = ALLERGY_FAMILIES.get(key, set()) | {key}
        for med in meds:
            if med.get("status") == "paused":
                continue
            name = med["name"].lower()
            if any(word in name for word in keywords):
                conflicts.append((med, allergy))
    return conflicts


def _safety_rules(ctx: CareContext) -> list[Insight]:
    insights = []
    for med, allergy in allergy_conflicts(ctx.meds, ctx.allergies):
        insights.append(
            Insight(
                f"safety:allergy:{med['id']}",
                "urgent",
                "safety",
                f"Check {med['name']} with a doctor",
                f"{ctx.subject(possessive=True).capitalize()} profile lists a {allergy} allergy, and "
                f"{med['name']} may be related. "
                "Please confirm with the doctor or pharmacist before the next dose.",
                f"Allergy on profile: {allergy}. {med['name']} matches a medicine family linked to it.",
                "Review medicine" if ctx.can_edit else None,
                "#/medicines" if ctx.can_edit else None,
            )
        )

    seen: dict[str, dict[str, Any]] = {}
    for med in ctx.meds:
        if med.get("status") != "active":
            continue
        key = _normalise(med["name"])
        if key in seen:
            insights.append(
                Insight(
                    f"safety:duplicate:{key}",
                    "high",
                    "safety",
                    f"{med['name']} is listed twice",
                    "Taking the same medicine twice can lead to an overdose. "
                    "Please check whether one entry is old.",
                    f"Two active entries: {seen[key]['dosage']} and {med['dosage']}.",
                    "Review medicines" if ctx.can_edit else None,
                    "#/medicines" if ctx.can_edit else None,
                )
            )
        seen.setdefault(key, med)
    return insights


def _course_rules(ctx: CareContext) -> list[Insight]:
    insights = []
    today = ctx.now_local.date()
    for med in ctx.meds:
        if med.get("status") != "active" or not med.get("end_date"):
            continue
        days_left = (date.fromisoformat(med["end_date"]) - today).days
        if 0 <= days_left <= 3:
            when = "today" if days_left == 0 else f"in {days_left} day{'s' if days_left > 1 else ''}"
            insights.append(
                Insight(
                    f"course:ending:{med['id']}",
                    "medium",
                    "dose",
                    f"{med['name']} course ends {when}",
                    "Check with the doctor whether to continue it, and arrange a refill if needed.",
                    f"End date set to {med['end_date']}.",
                )
            )
    return insights


def _appointment_rules(ctx: CareContext) -> list[Insight]:
    insights = []
    for appt in ctx.appointments:
        starts = from_iso_utc(appt["starts_at"]).astimezone(ctx.now_local.tzinfo)
        hours = (starts - ctx.now_local).total_seconds() / 3600
        if hours < 0 or hours > 48:
            continue
        when_day = (
            "today"
            if starts.date() == ctx.now_local.date()
            else (
                "tomorrow"
                if starts.date() == ctx.now_local.date() + timedelta(days=1)
                else starts.strftime("%A")
            )
        )
        when = f"{when_day} at {_fmt_time(starts.strftime('%H:%M'))}"
        priority = "urgent" if hours <= 3 else "high" if hours <= 24 else "medium"
        active = [m["name"] for m in ctx.meds if m.get("status") == "active"]
        prep = "Take the list of current medicines"
        prep += f" ({_join(active)})" if active and len(active) <= 4 else ""
        prep += " and note any side effects or questions to ask."
        lead = "Time to get ready: " if priority == "urgent" else ""
        insights.append(
            Insight(
                f"appointment:{appt['id']}",
                priority,
                "appointment",
                f"{appt['doctor']} {when}",
                lead + prep,
                f"Appointment starts in about {max(1, round(hours))} hour{'s' if round(hours) != 1 else ''}"
                + (f" at {appt['location']}." if appt.get("location") else "."),
                "View appointment",
                "#/appointments",
            )
        )
    return insights


def _care_circle_rules(ctx: CareContext) -> list[Insight]:
    insights = []
    pending = [m for m in ctx.meds if m.get("status") == "pending"]
    if pending and ctx.is_elder:
        insights.append(
            Insight(
                "approval:pending",
                "high",
                "care-circle",
                f"{len(pending)} medicine change{'s' if len(pending) > 1 else ''} need your approval",
                f"{_join([m['name'] for m in pending])} {'was' if len(pending) == 1 else 'were'} added or "
                "changed by a caretaker. Nothing changes until you approve.",
                "You asked to approve caretaker changes.",
                "Review now",
                "#/medicines",
            )
        )
    elif pending and ctx.role == "caretaker":
        insights.append(
            Insight(
                "approval:waiting",
                "low",
                "care-circle",
                f"Waiting for {ctx.first_name}'s approval",
                f"{_join([m['name'] for m in pending])} will start once {ctx.first_name} approves.",
                f"{ctx.first_name} reviews caretaker changes before they take effect.",
            )
        )
    if ctx.is_elder and ctx.member_count <= 1:
        insights.append(
            Insight(
                "circle:invite",
                "medium",
                "care-circle",
                "Invite someone you trust",
                "Add a family member or caretaker so someone is alerted if a dose is missed.",
                "Only you are in your care circle.",
                "Invite someone",
                "#/circle",
            )
        )
    if not ctx.meds and ctx.can_edit:
        insights.append(
            Insight(
                "setup:first-medicine",
                "medium",
                "setup",
                "Add the first medicine",
                "Once medicines are added, CareSync can remind, track and spot patterns.",
                "No medicines are on this profile yet.",
                "Add a medicine",
                "#/medicines",
            )
        )
    return insights


# ---------------------------------------------------------------- public API


def build_insights(ctx: CareContext) -> list[Insight]:
    today = _today_schedule(ctx)
    insights = (
        _safety_rules(ctx)
        + _dose_rules(ctx, today)
        + _appointment_rules(ctx)
        + _pattern_rules(ctx)
        + _adherence_rules(ctx)
        + _course_rules(ctx)
        + _care_circle_rules(ctx)
    )
    unique = {i.id: i for i in insights}.values()  # Rules never emit the same id twice; guard anyway.
    return sorted(unique, key=lambda i: PRIORITY_ORDER[i.priority])[:MAX_INSIGHTS]


def headline(ctx: CareContext, insights: list[Insight]) -> str:
    urgent = sum(1 for i in insights if i.priority == "urgent")
    if urgent:
        return f"{urgent} thing{'s need' if urgent > 1 else ' needs'} attention now"
    upcoming = [d for d in _today_schedule(ctx) if d["status"] == "upcoming"]
    if upcoming:
        nxt = upcoming[0]
        return f"Next: {nxt['name']} {nxt['dosage']} at {_fmt_time(nxt['time'])}"
    return "Everything is on track"


def summarise(ctx: CareContext) -> dict[str, Any]:
    insights = build_insights(ctx)
    return {"headline": headline(ctx, insights), "insights": [asdict(i) for i in insights]}


def context_brief(ctx: CareContext) -> str:
    """Minimal, non-identifying context for the AI model (no emails, codes or passcodes)."""
    active = [m for m in ctx.meds if m.get("status") == "active"]
    week = schedule.adherence(ctx.meds, ctx.logs, ctx.now_local, 7)
    lines = [
        f"Person receiving care: {ctx.first_name}. Asker's role: {ctx.role}.",
        f"Local time: {ctx.now_local.strftime('%A %H:%M')}.",
        f"Allergies: {', '.join(ctx.allergies) or 'none recorded'}.",
        "Current medicines: "
        + (
            "; ".join(
                f"{m['name']} {m['dosage']} at {', '.join(m['times'])}"
                + (f" ({m['instructions']})" if m.get("instructions") else "")
                for m in active
            )
            or "none"
        )
        + ".",
        f"Doses taken in the last 7 days: {week['percent'] if week['percent'] is not None else 'n/a'}%.",
    ]
    for appt in ctx.appointments[:3]:
        lines.append(
            f"Upcoming appointment: {appt['doctor']} {appt.get('specialty', '')} at {appt['starts_at']} UTC."
        )
    return "\n".join(lines)
