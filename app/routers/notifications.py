"""Email notifications: the scheduled reminder run, plus status and test-email helpers."""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.clock import Clock
from app.config import Settings
from app.db.base import Repository
from app.deps import Actor, any_member, get_clock, get_repo, get_settings_dep, owner_only
from app.services import reminders
from app.services.emailer import Email

router = APIRouter(tags=["notifications"])


@router.post("/internal/run-reminders", include_in_schema=False)
def run_reminders(
    request: Request,
    x_cron_secret: str | None = Header(default=None),
    repo: Repository = Depends(get_repo),
    settings: Settings = Depends(get_settings_dep),
    clock: Clock = Depends(get_clock),
) -> dict:
    """Called every 15 minutes by the scheduler. Protected by a shared secret header."""
    if not settings.cron_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Reminders are not configured")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.cron_secret):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return reminders.run(
        repo,
        request.app.state.emailer,
        clock(),
        settings.dose_grace_minutes,
        settings.reminder_lead_minutes,
    )


@router.get("/api/notifications/status")
def email_status(request: Request, actor: Actor = Depends(any_member)) -> dict:
    return {"email_enabled": request.app.state.emailer.enabled}


@router.post("/api/notifications/test")
def send_test_email(request: Request, actor: Actor = Depends(owner_only)) -> dict:
    emailer = request.app.state.emailer
    if not emailer.enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Email is not set up for this app yet.")
    sent = emailer.send(
        Email(
            [actor.member["email"]],
            "CareSync test email",
            f"Hello {actor.member['name'].split()[0]},\n\nEmail reminders are working. "
            "You and your care circle will be emailed about upcoming doses, missed doses and appointments."
            + reminders.FOOTER,
        )
    )
    if not sent:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The email could not be sent. Check the email settings."
        )
    return {"sent": True, "to": actor.member["email"]}
