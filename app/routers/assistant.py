"""Smart Care Assistant endpoints: rule-based insights plus optional AI answers."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import Field

from app.clock import Clock, local_now, to_iso_utc
from app.config import Settings
from app.db import paths
from app.db.base import Repository
from app.deps import Actor, any_member, get_clock, get_repo, get_settings_dep
from app.schemas import StrictModel
from app.services import assistant
from app.services.ai import DISCLAIMER, AIUnavailableError

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class Question(StrictModel):
    question: str = Field(min_length=3, max_length=500)


def build_context(actor: Actor, repo: Repository, settings: Settings, clock: Clock) -> assistant.CareContext:
    now_utc = clock()
    now = local_now(now_utc, actor.elder["timezone"])
    since = (now.date() - timedelta(days=14)).isoformat()
    return assistant.CareContext(
        role=actor.role,
        viewer_name=actor.member["name"],
        elder_name=actor.elder["name"],
        allergies=actor.elder.get("allergies", []),
        now_local=now,
        meds=repo.list(paths.medications(actor.elder_id)),
        logs=repo.list(paths.dose_logs(actor.elder_id), [("date", ">=", since)]),
        appointments=repo.list(
            paths.appointments(actor.elder_id),
            [("starts_at", ">=", to_iso_utc(now_utc))],
            order_by="starts_at",
            limit=10,
        ),
        member_count=len(repo.list(paths.members(actor.elder_id), [("active", "==", True)])),
        grace_minutes=settings.dose_grace_minutes,
    )


@router.get("")
def get_insights(
    request: Request,
    actor: Actor = Depends(any_member),
    repo: Repository = Depends(get_repo),
    settings: Settings = Depends(get_settings_dep),
    clock: Clock = Depends(get_clock),
) -> dict:
    ctx = build_context(actor, repo, settings, clock)
    return {**assistant.summarise(ctx), "ai_enabled": request.app.state.ai is not None}


@router.post("/ask")
def ask(
    body: Question,
    request: Request,
    actor: Actor = Depends(any_member),
    repo: Repository = Depends(get_repo),
    settings: Settings = Depends(get_settings_dep),
    clock: Clock = Depends(get_clock),
) -> dict:
    model = request.app.state.ai
    if model is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI answers are not turned on for this app.")
    limiter = request.app.state.ai_limiter
    key = f"ai:{actor.member['id']}"
    if limiter.is_blocked(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Please wait a few minutes before asking again."
        )
    limiter.record_failure(key)  # Counts every question toward the per-member limit.

    ctx = build_context(actor, repo, settings, clock)
    try:
        answer = model.answer(body.question, assistant.context_brief(ctx))
    except AIUnavailableError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return {"answer": answer, "disclaimer": DISCLAIMER}
