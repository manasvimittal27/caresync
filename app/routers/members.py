"""Care circle management. Only the elder (profile owner) can add or remove people."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from app.clock import Clock, to_iso_utc
from app.config import Settings
from app.db import paths
from app.db.base import Repository
from app.deps import Actor, any_member, get_clock, get_repo, get_settings_dep, owner_only
from app.schemas import MemberCreate, SettingsUpdate
from app.security import generate_passcode, hash_passcode
from app.services import audit
from app.services.reminders import invite_email
from app.views import public_elder, public_member

router = APIRouter(prefix="/api", tags=["care circle"])


@router.get("/profile")
def get_profile(actor: Actor = Depends(any_member)) -> dict:
    return public_elder(actor.elder, include_care_code=actor.role == "elder")


@router.put("/profile/settings")
def update_settings(
    body: SettingsUpdate,
    actor: Actor = Depends(owner_only),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> dict:
    repo.update(paths.ELDERS, actor.elder_id, {"settings": body.model_dump()})
    state = "on" if body.require_approval else "off"
    audit.record(
        repo,
        actor.elder_id,
        actor.member,
        "settings.updated",
        f"Turned approval of caretaker changes {state}",
        clock(),
    )
    return public_elder(repo.get(paths.ELDERS, actor.elder_id), include_care_code=True)


@router.get("/members")
def list_members(actor: Actor = Depends(any_member), repo: Repository = Depends(get_repo)) -> list[dict]:
    members = repo.list(paths.members(actor.elder_id), [("active", "==", True)])
    order = {"elder": 0, "caretaker": 1, "family": 2}
    members.sort(key=lambda m: (order[m["role"]], m["name"].lower()))
    return [public_member(m) for m in members]


@router.post("/members", status_code=status.HTTP_201_CREATED)
def add_member(
    body: MemberCreate,
    request: Request,
    background: BackgroundTasks,
    actor: Actor = Depends(owner_only),
    repo: Repository = Depends(get_repo),
    settings: Settings = Depends(get_settings_dep),
    clock: Clock = Depends(get_clock),
) -> dict:
    path = paths.members(actor.elder_id)
    existing = repo.list(path, [("email", "==", body.email)], limit=1)
    if existing and existing[0].get("active"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This email is already in the care circle")

    passcode = generate_passcode()
    data = {
        "name": body.name,
        "email": body.email,
        "role": body.role,
        "passcode_hash": hash_passcode(passcode, settings.pbkdf2_iterations),
        "active": True,
        "created_at": to_iso_utc(clock()),
    }
    if existing:  # Re-invite a previously removed member.
        member_id = existing[0]["id"]
        repo.set(path, member_id, data)
    else:
        member_id = repo.create(path, data)

    audit.record(
        repo,
        actor.elder_id,
        actor.member,
        "member.added",
        f"Added {body.name} as {body.role}",
        clock(),
        member_id,
    )
    # The passcode is shown once to the owner and emailed to the new member; only its hash is stored.
    emailer = request.app.state.emailer
    background.add_task(
        emailer.send,
        invite_email(
            body.name, actor.elder["name"], actor.elder["care_code"], body.email, passcode, settings.app_url
        ),
    )
    return {
        "member": public_member(repo.get(path, member_id)),
        "passcode": passcode,
        "care_code": actor.elder["care_code"],
        "emailed": emailer.enabled,
    }


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    member_id: str,
    actor: Actor = Depends(owner_only),
    repo: Repository = Depends(get_repo),
    clock: Clock = Depends(get_clock),
) -> None:
    if member_id == actor.member["id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot remove yourself")
    path = paths.members(actor.elder_id)
    member = repo.get(path, member_id)
    if not member or not member.get("active"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    # Soft delete keeps the audit trail meaningful; access stops immediately.
    repo.update(path, member_id, {"active": False})
    audit.record(
        repo,
        actor.elder_id,
        actor.member,
        "member.removed",
        f"Removed {member['name']} from the care circle",
        clock(),
        member_id,
    )
