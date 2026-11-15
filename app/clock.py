"""Time helpers. The clock is injected so tests can freeze time."""

from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_iso_utc(dt: datetime) -> str:
    """Fixed-width UTC string so lexical order equals chronological order in Firestore."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_iso_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def local_now(now_utc: datetime, tz_name: str) -> datetime:
    return now_utc.astimezone(ZoneInfo(tz_name))
