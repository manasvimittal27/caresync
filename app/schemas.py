"""Request and response models. Every input is validated and length-limited."""

import re
from datetime import date, datetime
from datetime import date as _Date  # Alias: DoseLogIn has a field named "date".
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Role = Literal["elder", "caretaker", "family"]
MemberRole = Literal["caretaker", "family"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class StrictModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _normalise_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not _EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address")
    return value


# ---------- Profiles, sessions, members ----------


class ProfileCreate(StrictModel):
    elder_name: str = Field(min_length=1, max_length=80)
    email: str
    passcode: str = Field(min_length=6, max_length=64)
    date_of_birth: date | None = None
    allergies: list[ShortText] = Field(default_factory=list, max_length=20)
    conditions: list[ShortText] = Field(default_factory=list, max_length=20)
    timezone: str = "Asia/Kolkata"

    _email = field_validator("email")(_normalise_email)

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown timezone") from exc
        return value

    @field_validator("date_of_birth")
    @classmethod
    def _dob_in_past(cls, value: date | None) -> date | None:
        if value and value >= date.today():
            raise ValueError("Date of birth must be in the past")
        return value


class SessionCreate(StrictModel):
    care_code: str = Field(min_length=6, max_length=6)
    email: str
    passcode: str = Field(min_length=6, max_length=64)

    _email = field_validator("email")(_normalise_email)

    @field_validator("care_code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class PasscodeChange(StrictModel):
    current_passcode: str = Field(min_length=6, max_length=64)
    new_passcode: str = Field(min_length=6, max_length=64)


class MemberCreate(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    email: str
    role: MemberRole

    _email = field_validator("email")(_normalise_email)


class SettingsUpdate(StrictModel):
    require_approval: bool


# ---------- Medications and doses ----------


class MedicationIn(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    dosage: str = Field(min_length=1, max_length=60)
    instructions: str = Field(default="", max_length=300)
    times: list[str] = Field(min_length=1, max_length=8)
    start_date: date
    end_date: date | None = None

    @field_validator("times")
    @classmethod
    def _valid_times(cls, value: list[str]) -> list[str]:
        for t in value:
            if not _TIME_RE.match(t):
                raise ValueError(f"Invalid time '{t}', use HH:MM (24-hour)")
        if len(set(value)) != len(value):
            raise ValueError("Dose times must be unique")
        return sorted(value)

    @model_validator(mode="after")
    def _date_order(self) -> "MedicationIn":
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        return self


class MedicationUpdate(MedicationIn):
    paused: bool = False


class DoseLogIn(StrictModel):
    medication_id: str = Field(min_length=1, max_length=64)
    time: str
    status: Literal["taken", "skipped"]
    date: _Date | None = None

    @field_validator("time")
    @classmethod
    def _valid_time(cls, value: str) -> str:
        if not _TIME_RE.match(value):
            raise ValueError("Invalid time, use HH:MM (24-hour)")
        return value


# ---------- Appointments ----------


class AppointmentIn(StrictModel):
    doctor: str = Field(min_length=1, max_length=80)
    specialty: str = Field(default="", max_length=60)
    starts_at: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)
    location: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=500)
