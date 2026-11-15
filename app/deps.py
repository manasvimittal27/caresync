"""FastAPI dependencies: shared app state, authentication and role checks."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.clock import Clock
from app.config import Settings
from app.db import paths
from app.db.base import Repository
from app.security import RateLimiter, SessionManager

SESSION_COOKIE = "caresync_session"


def get_repo(request: Request) -> Repository:
    return request.app.state.repo


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_sessions(request: Request) -> SessionManager:
    return request.app.state.sessions


def get_login_limiter(request: Request) -> RateLimiter:
    return request.app.state.login_limiter


@dataclass(frozen=True)
class Actor:
    """The signed-in member and the elder profile they belong to."""

    elder: dict[str, Any]
    member: dict[str, Any]

    @property
    def elder_id(self) -> str:
        return self.elder["id"]

    @property
    def role(self) -> str:
        return self.member["role"]


def current_actor(
    request: Request,
    repo: Repository = Depends(get_repo),
    sessions: SessionManager = Depends(get_sessions),
) -> Actor:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in")
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise unauthorized
    ids = sessions.read(token)
    if ids is None:
        raise unauthorized
    elder_id, member_id = ids
    elder = repo.get(paths.ELDERS, elder_id)
    member = repo.get(paths.members(elder_id), member_id)
    # Membership is re-checked on every request, so revoking access is immediate.
    if not elder or not member or not member.get("active", False):
        raise unauthorized
    return Actor(elder=elder, member=member)


def require_roles(*roles: str) -> Callable[..., Actor]:
    def checker(actor: Actor = Depends(current_actor)) -> Actor:
        if actor.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do this")
        return actor

    return checker


# Reusable role guards.
any_member = current_actor
can_edit_care = require_roles("elder", "caretaker")
owner_only = require_roles("elder")
