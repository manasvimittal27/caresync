"""Activity log: a transparent record of every change, visible to the whole circle."""

from fastapi import APIRouter, Depends, Query

from app.db import paths
from app.db.base import Repository
from app.deps import Actor, any_member, get_repo

router = APIRouter(prefix="/api", tags=["activity"])


@router.get("/activity")
def activity(
    limit: int = Query(default=50, ge=1, le=200),
    actor: Actor = Depends(any_member),
    repo: Repository = Depends(get_repo),
) -> list[dict]:
    return repo.list(paths.audit_log(actor.elder_id), order_by="seq", descending=True, limit=limit)
