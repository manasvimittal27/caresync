"""Google Calendar "add event" links (no OAuth needed)."""

from datetime import UTC, datetime
from urllib.parse import urlencode

_GCAL_BASE = "https://calendar.google.com/calendar/render"


def google_calendar_url(
    title: str, start: datetime, end: datetime, details: str = "", location: str = ""
) -> str:
    fmt = "%Y%m%dT%H%M%SZ"
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start.astimezone(UTC).strftime(fmt)}/{end.astimezone(UTC).strftime(fmt)}",
        "details": details,
        "location": location,
    }
    return f"{_GCAL_BASE}?{urlencode(params)}"
