"""Application settings loaded from environment variables.

All secrets come from the environment (populated from Secret Manager on Cloud Run),
never from source code.
"""

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    app_env: str
    session_secret: str
    db_backend: str
    gcp_project: str | None
    default_timezone: str
    session_max_age_seconds: int
    dose_grace_minutes: int
    login_max_attempts: int
    login_window_seconds: int
    pbkdf2_iterations: int
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: str | None = None
    cron_secret: str | None = None
    app_url: str = "http://localhost:8000"
    reminder_lead_minutes: int = 15
    database_url: str | None = None

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"

    @property
    def cookie_secure(self) -> bool:
        return self.is_production


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def load_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "local")
    session_secret = os.getenv("SESSION_SECRET", "")
    if not session_secret:
        if app_env == "prod":
            raise RuntimeError("SESSION_SECRET must be set in production")
        # Ephemeral key for local development and tests only.
        session_secret = secrets.token_urlsafe(32)

    return Settings(
        app_env=app_env,
        session_secret=session_secret,
        db_backend=os.getenv("DB_BACKEND") or ("postgres" if os.getenv("DATABASE_URL") else "memory"),
        gcp_project=os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT"),
        default_timezone=os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata"),
        session_max_age_seconds=_int("SESSION_MAX_AGE_SECONDS", 12 * 60 * 60),
        dose_grace_minutes=_int("DOSE_GRACE_MINUTES", 30),
        login_max_attempts=_int("LOGIN_MAX_ATTEMPTS", 5),
        login_window_seconds=_int("LOGIN_WINDOW_SECONDS", 15 * 60),
        pbkdf2_iterations=_int("PBKDF2_ITERATIONS", 210_000),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=_int("SMTP_PORT", 465),
        smtp_user=os.getenv("SMTP_USER") or None,
        smtp_password=(os.getenv("SMTP_PASSWORD") or "").replace(" ", "")
        or None,  # Gmail shows it in groups.
        cron_secret=os.getenv("CRON_SECRET") or None,
        app_url=os.getenv("APP_URL", "http://localhost:8000").rstrip("/"),
        reminder_lead_minutes=_int("REMINDER_LEAD_MINUTES", 15),
        database_url=os.getenv("DATABASE_URL") or None,
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
