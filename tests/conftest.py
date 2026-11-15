"""Shared fixtures: an app wired to an in-memory database and a controllable clock."""

import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.memory import InMemoryRepository
from app.main import create_app

# 10:00 IST on 15 Nov 2026.
START = datetime(2026, 11, 15, 4, 30, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def make_settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        session_secret="test-secret",
        db_backend="memory",
        gcp_project=None,
        default_timezone="Asia/Kolkata",
        session_max_age_seconds=3600,
        dose_grace_minutes=30,
        login_max_attempts=5,
        login_window_seconds=900,
        pbkdf2_iterations=1000,  # Fast hashing in tests only.
    )
    return Settings(**{**base, **overrides})


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(scope="session")
def _postgres_repo():
    """Shared Postgres repository when TEST_DATABASE_URL is set (CI runs the suite on both backends)."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        yield None
        return
    from app.db.postgres import PostgresRepository

    pg = PostgresRepository(url)
    yield pg
    pg.close()


@pytest.fixture
def repo(_postgres_repo):
    if _postgres_repo is None:
        return InMemoryRepository()
    with _postgres_repo._pool.connection() as conn:
        conn.execute("truncate documents")
    return _postgres_repo


@pytest.fixture
def app(repo, clock):
    return create_app(settings=make_settings(), repo=repo, clock=clock)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


ELDER = {
    "elder_name": "Kamala Iyer",
    "email": "kamala@example.com",
    "passcode": "kamala-123",
    "date_of_birth": "1948-03-02",
    "allergies": ["Penicillin"],
    "conditions": ["Type 2 diabetes"],
    "timezone": "Asia/Kolkata",
}

MED = {
    "name": "Metformin",
    "dosage": "500 mg",
    "instructions": "After food",
    "times": ["20:00", "08:00"],
    "start_date": "2026-11-10",
}


@pytest.fixture
def owner(app) -> tuple[TestClient, dict]:
    """A signed-in elder (profile owner) client and the created profile."""
    c = TestClient(app)
    res = c.post("/api/profiles", json=ELDER)
    assert res.status_code == 201, res.text
    return c, res.json()


def add_member(owner_client: TestClient, app, role: str, email: str) -> TestClient:
    """Owner adds a member; returns a separate client signed in as that member."""
    res = owner_client.post(
        "/api/members", json={"name": f"{role.title()} Person", "email": email, "role": role}
    )
    assert res.status_code == 201, res.text
    body = res.json()
    member_client = TestClient(app)
    login = member_client.post(
        "/api/session",
        json={"care_code": body["care_code"], "email": email, "passcode": body["passcode"]},
    )
    assert login.status_code == 200, login.text
    return member_client
