"""Email delivery. Gmail SMTP in production; an in-memory outbox in development and tests."""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Email:
    to: list[str]
    subject: str
    body: str


class Emailer(Protocol):
    enabled: bool

    def send(self, email: Email) -> bool: ...


class SmtpEmailer:
    """Sends plain-text email over SMTP with TLS (Gmail: smtp.gmail.com:465 + App Password)."""

    enabled = True

    def __init__(self, host: str, port: int, user: str, password: str, sender_name: str = "CareSync") -> None:
        self._host, self._port = host, port
        self._user, self._password = user, password
        self._from = formataddr((sender_name, user))

    def send(self, email: Email) -> bool:
        recipients = sorted({r for r in email.to if r})
        if not recipients:
            return False
        msg = EmailMessage()
        msg["From"] = self._from
        msg["To"] = self._from  # Recipients go in Bcc so care-circle emails stay private.
        msg["Bcc"] = ", ".join(recipients)
        msg["Subject"] = email.subject
        msg.set_content(email.body)
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self._host, self._port, context=context, timeout=20) as server:
                server.login(self._user, self._password)
                server.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("Email delivery failed: %s", type(exc).__name__)
            return False
        return True


class OutboxEmailer:
    """Development/test emailer: keeps messages in memory and logs a one-line summary."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.outbox: list[Email] = []

    def send(self, email: Email) -> bool:
        self.outbox.append(email)
        logger.info("Email (not sent, dev mode) to %d recipient(s): %s", len(email.to), email.subject)
        return True


def build_emailer(host: str, port: int, user: str | None, password: str | None) -> Emailer:
    if user and password:
        return SmtpEmailer(host, port, user, password)
    return OutboxEmailer()
