"""Dose scheduling and adherence calculations (pure functions, no I/O)."""

from datetime import date, datetime, time, timedelta
from typing import Any

ACTIVE = "active"


def dose_id(medication_id: str, day: date, at: str) -> str:
    """Deterministic id so logging the same dose twice updates, not duplicates."""
    return f"{medication_id}_{day.isoformat()}_{at.replace(':', '')}"


def _parse_time(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def is_scheduled_on(med: dict[str, Any], day: date) -> bool:
    if med.get("status") != ACTIVE:
        return False
    start = date.fromisoformat(med["start_date"])
    end = date.fromisoformat(med["end_date"]) if med.get("end_date") else None
    return start <= day and (end is None or day <= end)


def doses_for_day(meds: list[dict[str, Any]], day: date) -> list[tuple[dict[str, Any], str]]:
    """All (medication, "HH:MM") pairs scheduled on ``day``, ordered by time."""
    pairs = [(m, t) for m in meds if is_scheduled_on(m, day) for t in m["times"]]
    return sorted(pairs, key=lambda pair: (pair[1], pair[0]["name"].lower()))


def dose_status(
    log: dict[str, Any] | None, scheduled_at: datetime, now_local: datetime, grace_minutes: int
) -> str:
    """taken / skipped / missed from a log, else upcoming / due / overdue by the clock."""
    if log:
        return log["status"]
    if now_local < scheduled_at:
        return "upcoming"
    if now_local < scheduled_at + timedelta(minutes=grace_minutes):
        return "due"
    return "overdue"


def day_schedule(
    meds: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    day: date,
    now_local: datetime,
    grace_minutes: int,
) -> list[dict[str, Any]]:
    logs_by_id = {log["id"]: log for log in logs}
    items = []
    for med, at in doses_for_day(meds, day):
        scheduled_at = datetime.combine(day, _parse_time(at), tzinfo=now_local.tzinfo)
        log = logs_by_id.get(dose_id(med["id"], day, at))
        items.append(
            {
                "dose_id": dose_id(med["id"], day, at),
                "medication_id": med["id"],
                "name": med["name"],
                "dosage": med["dosage"],
                "instructions": med.get("instructions", ""),
                "time": at,
                "status": dose_status(log, scheduled_at, now_local, grace_minutes),
                "logged_by": log.get("logged_by_name") if log else None,
            }
        )
    return items


def adherence(
    meds: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    now_local: datetime,
    days: int,
) -> dict[str, Any]:
    """Share of doses taken among doses already due in the last ``days`` days (incl. today)."""
    taken_ids = {log["id"] for log in logs if log.get("status") == "taken"}
    per_med: dict[str, dict[str, Any]] = {
        m["id"]: {"medication_id": m["id"], "name": m["name"], "scheduled": 0, "taken": 0}
        for m in meds
        if m.get("status") == ACTIVE
    }
    today = now_local.date()
    for offset in range(days):
        day = today - timedelta(days=offset)
        for med, at in doses_for_day(meds, day):
            scheduled_at = datetime.combine(day, _parse_time(at), tzinfo=now_local.tzinfo)
            if scheduled_at > now_local:
                continue  # Not due yet; don't penalise future doses.
            stats = per_med[med["id"]]
            stats["scheduled"] += 1
            if dose_id(med["id"], day, at) in taken_ids:
                stats["taken"] += 1

    def pct(taken: int, scheduled: int) -> float | None:
        return round(100 * taken / scheduled, 1) if scheduled else None

    rows = [{**s, "percent": pct(s["taken"], s["scheduled"])} for s in per_med.values()]
    total_scheduled = sum(r["scheduled"] for r in rows)
    total_taken = sum(r["taken"] for r in rows)
    return {
        "days": days,
        "scheduled": total_scheduled,
        "taken": total_taken,
        "percent": pct(total_taken, total_scheduled),
        "medications": sorted(rows, key=lambda r: r["name"].lower()),
    }
