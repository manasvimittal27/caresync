"""Medication schedules. Caretaker changes can require the elder's approval."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.clock import Clock, to_iso_utc
from app.db import paths
from app.db.base import Repository
from app.deps import Actor, any_member, can_edit_care, get_clock, get_repo, owner_only
from app.schemas import MedicationIn, MedicationUpdate
from app.services import audit

router = APIRouter(prefix="/api/medications", tags=["medications"])


def _needs_approval(actor: Actor) -> bool:
    return actor.role != "elder" and actor.elder.get("settings", {}).get("require_approval", False)


def _serialise(body: MedicationIn) -> dict:
    return {
        "name": body.name,
        "dosage": body.dosage,
        "instructions": body.instructions,
        "times": body.times,
        "start_date": body.start_date.isoformat(),
        "end_date": body.end_date.isoformat() if body.end_date else None,
    }


def _get_or_404(repo: Repository, elder_id: str, med_id: str) -> dict:
    med = repo.get(paths.medications(elder_id), med_id)
    if not med:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medication not found")
    return med


@router.get("")
def list_medications(actor: Actor = Depends(any_member), repo: Repository = Depends(get_repo)) -> list[dict]:
    meds = repo.list(paths.medications(actor.elder_id))
    return sorted(meds, key=lambda m: m["name"].lower())


@router.post("", status_code=status.HTTP_201_CREATED)
def create_medication(
    body: MedicationIn,
    actor: Actor = Depends(can_edit_care),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> dict:
    now = clock()
    pending = _needs_approval(actor)
    data = {
        **_serialise(body),
        "status": "pending" if pending else "active",
        "created_by": actor.member["name"],
        "created_at": to_iso_utc(now),
        "updated_at": to_iso_utc(now),
    }
    med_id = repo.create(paths.medications(actor.elder_id), data)
    note = " (awaiting approval)" if pending else ""
    audit.record(
        repo,
        actor.elder_id,
        actor.member,
        "medication.created",
        f"Added {body.name} {body.dosage}{note}",
        now,
        med_id,
    )
    return repo.get(paths.medications(actor.elder_id), med_id)


@router.put("/{med_id}")
def update_medication(
    med_id: str,
    body: MedicationUpdate,
    actor: Actor = Depends(can_edit_care),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> dict:
    _get_or_404(repo, actor.elder_id, med_id)
    now = clock()
    if _needs_approval(actor):
        new_status = "pending"
    else:
        new_status = "paused" if body.paused else "active"
    repo.update(
        paths.medications(actor.elder_id),
        med_id,
        {**_serialise(body), "status": new_status, "updated_at": to_iso_utc(now)},
    )
    audit.record(
        repo,
        actor.elder_id,
        actor.member,
        "medication.updated",
        f"Updated {body.name} ({new_status})",
        now,
        med_id,
    )
    return repo.get(paths.medications(actor.elder_id), med_id)


@router.post("/{med_id}/approve")
def approve_medication(
    med_id: str,
    actor: Actor = Depends(owner_only),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> dict:
    med = _get_or_404(repo, actor.elder_id, med_id)
    if med["status"] != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "This medication is not awaiting approval")
    now = clock()
    repo.update(
        paths.medications(actor.elder_id),
        med_id,
        {"status": "active", "updated_at": to_iso_utc(now)},
    )
    audit.record(
        repo,
        actor.elder_id,
        actor.member,
        "medication.approved",
        f"Approved {med['name']}",
        now,
        med_id,
    )
    return repo.get(paths.medications(actor.elder_id), med_id)


@router.delete("/{med_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medication(
    med_id: str,
    actor: Actor = Depends(can_edit_care),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> None:
    med = _get_or_404(repo, actor.elder_id, med_id)
    repo.delete(paths.medications(actor.elder_id), med_id)
    audit.record(
        repo,
        actor.elder_id,
        actor.member,
        "medication.deleted",
        f"Removed {med['name']}",
        clock(),
        med_id,
    )
