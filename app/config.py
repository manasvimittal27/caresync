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
        db_backend=os.getenv("DB_BACKEND", "firestore" if app_env == "prod" else "memory"),
        gcp_project=os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT"),
        default_timezone=os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata"),
        session_max_age_seconds=_int("SESSION_MAX_AGE_SECONDS", 12 * 60 * 60),
        dose_grace_minutes=_int("DOSE_GRACE_MINUTES", 30),
        login_max_attempts=_int("LOGIN_MAX_ATTEMPTS", 5),
        login_window_seconds=_int("LOGIN_WINDOW_SECONDS", 15 * 60),
        pbkdf2_iterations=_int("PBKDF2_ITERATIONS", 210_000),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
