"""Today's dose checklist, dose logging and adherence."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.clock import Clock, local_now, to_iso_utc
from app.config import Settings
from app.db import paths
from app.db.base import Repository
from app.deps import Actor, any_member, can_edit_care, get_clock, get_repo, get_settings_dep
from app.schemas import DoseLogIn
from app.services import audit, schedule

router = APIRouter(prefix="/api", tags=["doses"])


@router.get("/doses/today")
def today(
    actor: Actor = Depends(any_member),
    repo: Repository = Depends(get_repo),
    settings: Settings = Depends(get_settings_dep),
    clock: Clock = Depends(get_clock),
) -> dict:
    now = local_now(clock(), actor.elder["timezone"])
    day = now.date()
    meds = repo.list(paths.medications(actor.elder_id))
    logs = repo.list(paths.dose_logs(actor.elder_id), [("date", "==", day.isoformat())])
    items = schedule.day_schedule(meds, logs, day, now, settings.dose_grace_minutes)
    return {"date": day.isoformat(), "doses": items}


@router.post("/doses", status_code=status.HTTP_201_CREATED)
def log_dose(
    body: DoseLogIn,
    actor: Actor = Depends(can_edit_care),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> dict:
    now_utc = clock()
    today_local = local_now(now_utc, actor.elder["timezone"]).date()
    day = body.date or today_local
    if day > today_local or day < today_local - timedelta(days=2):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Doses can be logged for today or the previous 2 days"
        )

    med = repo.get(paths.medications(actor.elder_id), body.medication_id)
    if not med:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medication not found")
    if body.time not in med["times"] or not schedule.is_scheduled_on(med, day):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No dose is scheduled at that time")

    log_id = schedule.dose_id(med["id"], day, body.time)
    repo.set(
        paths.dose_logs(actor.elder_id),
        log_id,
        {
            "medication_id": med["id"],
            "medication_name": med["name"],
            "date": day.isoformat(),
            "time": body.time,
            "status": body.status,
            "logged_by_id": actor.member["id"],
            "logged_by_name": actor.member["name"],
            "logged_at": to_iso_utc(now_utc),
        },
    )
    audit.record(
        repo,
        actor.elder_id,
        actor.member,
        f"dose.{body.status}",
        f"Marked {med['name']} at {body.time} on {day.isoformat()} as {body.status}",
        now_utc,
        log_id,
    )
    return repo.get(paths.dose_logs(actor.elder_id), log_id)


@router.get("/adherence")
def get_adherence(
    days: int = Query(default=7, ge=1, le=90),
    actor: Actor = Depends(any_member),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> dict:
    now = local_now(clock(), actor.elder["timezone"])
    start = (now.date() - timedelta(days=days - 1)).isoformat()
    meds = repo.list(paths.medications(actor.elder_id))
    logs = repo.list(paths.dose_logs(actor.elder_id), [("date", ">=", start)])
    return schedule.adherence(meds, logs, now, days)
