"""Audit trail: who changed what, and when."""

import time
from datetime import datetime

from app.clock import to_iso_utc
from app.db import paths
from app.db.base import Repository


def record(
    repo: Repository,
    elder_id: str,
    actor: dict | None,
    action: str,
    summary: str,
    now: datetime,
    target_id: str | None = None,
) -> None:
    repo.create(
        paths.audit_log(elder_id),
        {
            "at": to_iso_utc(now),
            # Nanosecond sequence keeps same-second events in the right order.
            "seq": time.time_ns(),
            "actor_id": actor["id"] if actor else "system",
            "actor_name": actor["name"] if actor else "CareSync",
            "actor_role": actor["role"] if actor else "system",
            "action": action,
            "target_id": target_id,
            "summary": summary,
        },
    )
