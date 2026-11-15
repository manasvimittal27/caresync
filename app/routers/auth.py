"""Profile creation and passcode-based sign-in."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.clock import Clock, to_iso_utc
from app.config import Settings
from app.db import paths
from app.db.base import Repository
from app.deps import (
    SESSION_COOKIE,
    Actor,
    current_actor,
    get_clock,
    get_login_limiter,
    get_repo,
    get_sessions,
    get_settings_dep,
)
from app.schemas import PasscodeChange, ProfileCreate, SessionCreate
from app.security import (
    RateLimiter,
    SessionManager,
    generate_care_code,
    hash_passcode,
    verify_passcode,
)
from app.services import audit
from app.views import public_elder, public_member

router = APIRouter(prefix="/api", tags=["auth"])

_INVALID_LOGIN = "Care code, email or passcode is incorrect"
# Used to equalise timing when the member does not exist (prevents account probing).
_DUMMY_HASH = hash_passcode("dummy-passcode", 1000)


def _set_session_cookie(
    response: Response, sessions: SessionManager, settings: Settings, elder_id: str, member_id: str
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sessions.issue(elder_id, member_id),
        max_age=sessions.max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def _unique_care_code(repo: Repository) -> str:
    for _ in range(10):
        code = generate_care_code()
        if not repo.list(paths.ELDERS, [("care_code", "==", code)], limit=1):
            return code
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Please try again")


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
def create_profile(
    body: ProfileCreate,
    response: Response,
    repo: Repository = Depends(get_repo),
    settings: Settings = Depends(get_settings_dep),
    sessions: SessionManager = Depends(get_sessions),
    clock: Clock = Depends(get_clock),
) -> dict:
    now = clock()
    care_code = _unique_care_code(repo)
    elder_id = repo.create(
        paths.ELDERS,
        {
            "name": body.elder_name,
            "date_of_birth": body.date_of_birth.isoformat() if body.date_of_birth else None,
            "allergies": body.allergies,
            "conditions": body.conditions,
            "timezone": body.timezone,
            "care_code": care_code,
            "settings": {"require_approval": False},
            "created_at": to_iso_utc(now),
        },
    )
    member_id = repo.create(
        paths.members(elder_id),
        {
            "name": body.elder_name,
            "email": body.email,
            "role": "elder",
            "passcode_hash": hash_passcode(body.passcode, settings.pbkdf2_iterations),
            "active": True,
            "created_at": to_iso_utc(now),
        },
    )
    member = repo.get(paths.members(elder_id), member_id)
    audit.record(repo, elder_id, member, "profile.created", "Created the CareSync profile", now)
    _set_session_cookie(response, sessions, settings, elder_id, member_id)
    return {
        "elder": public_elder(repo.get(paths.ELDERS, elder_id), include_care_code=True),
        "member": public_member(member),
    }


@router.post("/session")
def sign_in(
    body: SessionCreate,
    request: Request,
    response: Response,
    repo: Repository = Depends(get_repo),
    settings: Settings = Depends(get_settings_dep),
    sessions: SessionManager = Depends(get_sessions),
    limiter: RateLimiter = Depends(get_login_limiter),
    clock: Clock = Depends(get_clock),
) -> dict:
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{body.care_code}"
    if limiter.is_blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Please wait 15 minutes.")

    elders = repo.list(paths.ELDERS, [("care_code", "==", body.care_code)], limit=1)
    member = None
    if elders:
        matches = repo.list(paths.members(elders[0]["id"]), [("email", "==", body.email)], limit=1)
        member = matches[0] if matches else None

    stored_hash = member["passcode_hash"] if member else _DUMMY_HASH
    valid = verify_passcode(body.passcode, stored_hash)
    if not (member and valid and member.get("active", False)):
        limiter.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _INVALID_LOGIN)

    limiter.reset(key)
    elder = elders[0]
    _set_session_cookie(response, sessions, settings, elder["id"], member["id"])
    audit.record(repo, elder["id"], member, "session.signed_in", "Signed in", clock())
    return {
        "elder": public_elder(elder, include_care_code=member["role"] == "elder"),
        "member": public_member(member),
    }


@router.post("/session/logout", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/session")
def session_status(
    request: Request,
    repo: Repository = Depends(get_repo),
    sessions: SessionManager = Depends(get_sessions),
) -> dict:
    """Lets the front end check sign-in state without triggering a 401."""
    try:
        actor = current_actor(request, repo, sessions)
    except HTTPException:
        return {"signed_in": False}
    return {"signed_in": True, **me(actor)}


@router.get("/me")
def me(actor: Actor = Depends(current_actor)) -> dict:
    return {
        "elder": public_elder(actor.elder, include_care_code=actor.role == "elder"),
        "member": public_member(actor.member),
    }


@router.put("/me/passcode", status_code=status.HTTP_204_NO_CONTENT)
def change_passcode(
    body: PasscodeChange,
    actor: Actor = Depends(current_actor),
    repo: Repository = Depends(get_repo),
    settings: Settings = Depends(get_settings_dep),
    clock: Clock = Depends(get_clock),
) -> None:
    if not verify_passcode(body.current_passcode, actor.member["passcode_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current passcode is incorrect")
    repo.update(
        paths.members(actor.elder_id),
        actor.member["id"],
        {"passcode_hash": hash_passcode(body.new_passcode, settings.pbkdf2_iterations)},
    )
    audit.record(repo, actor.elder_id, actor.member, "member.passcode_changed", "Changed passcode", clock())
