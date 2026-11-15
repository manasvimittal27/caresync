"""Doctor appointments, each with an "Add to Google Calendar" link."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.clock import Clock, from_iso_utc, to_iso_utc
from app.db import paths
from app.db.base import Repository
from app.deps import Actor, any_member, can_edit_care, get_clock, get_repo
from app.schemas import AppointmentIn
from app.services import audit
from app.services.calendar import google_calendar_url

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


def _serialise(body: AppointmentIn, tz_name: str) -> dict:
    starts_at = body.starts_at
    if starts_at.tzinfo is None:  # Naive times are in the elder's own timezone.
        starts_at = starts_at.replace(tzinfo=ZoneInfo(tz_name))
    return {
        "doctor": body.doctor,
        "specialty": body.specialty,
        "starts_at": to_iso_utc(starts_at),
        "duration_minutes": body.duration_minutes,
        "location": body.location,
        "notes": body.notes,
    }


def _with_links(appt: dict, elder_name: str) -> dict:
    start = from_iso_utc(appt["starts_at"])
    end = start + timedelta(minutes=appt["duration_minutes"])
    title = f"{elder_name}: appointment with {appt['doctor']}"
    return {
        **appt,
        "google_calendar_url": google_calendar_url(
            title, start, end, appt.get("notes", ""), appt.get("location", "")
        ),
    }


def _get_or_404(repo: Repository, elder_id: str, appt_id: str) -> dict:
    appt = repo.get(paths.appointments(elder_id), appt_id)
    if not appt:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
    return appt


@router.get("")
def list_appointments(
    include_past: bool = Query(default=False),
    actor: Actor = Depends(any_member),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> list[dict]:
    filters = [] if include_past else [("starts_at", ">=", to_iso_utc(clock()))]
    appts = repo.list(paths.appointments(actor.elder_id), filters, order_by="starts_at")
    return [_with_links(a, actor.elder["name"]) for a in appts]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_appointment(
    body: AppointmentIn,
    actor: Actor = Depends(can_edit_care),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> dict:
    now = clock()
    data = {
        **_serialise(body, actor.elder["timezone"]),
        "created_by": actor.member["name"],
        "created_at": to_iso_utc(now),
    }
    appt_id = repo.create(paths.appointments(actor.elder_id), data)
    audit.record(
        repo,
        actor.elder_id,
        actor.member,
        "appointment.created",
        f"Added appointment with {body.doctor}",
        now,
        appt_id,
    )
    return _with_links(repo.get(paths.appointments(actor.elder_id), appt_id), actor.elder["name"])


@router.put("/{appt_id}")
def update_appointment(
    appt_id: str,
    body: AppointmentIn,
    actor: Actor = Depends(can_edit_care),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> dict:
    _get_or_404(repo, actor.elder_id, appt_id)
    # A changed time must trigger fresh reminders, so clear the sent-reminder markers.
    repo.update(
        paths.appointments(actor.elder_id),
        appt_id,
        {**_serialise(body, actor.elder["timezone"]), "reminders_sent": []},
    )
    audit.record(
        repo,
        actor.elder_id,
        actor.member,
        "appointment.updated",
        f"Updated appointment with {body.doctor}",
        clock(),
        appt_id,
    )
    return _with_links(repo.get(paths.appointments(actor.elder_id), appt_id), actor.elder["name"])


@router.delete("/{appt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(
    appt_id: str,
    actor: Actor = Depends(can_edit_care),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> None:
    appt = _get_or_404(repo, actor.elder_id, appt_id)
    repo.delete(paths.appointments(actor.elder_id), appt_id)
    audit.record(
        repo,
        actor.elder_id,
        actor.member,
        "appointment.deleted",
        f"Removed appointment with {appt['doctor']}",
        clock(),
        appt_id,
    )
