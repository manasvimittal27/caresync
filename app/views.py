"""Shape stored documents into public API responses (never leaks hashes or codes)."""

from typing import Any


def public_member(member: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": member["id"],
        "name": member["name"],
        "email": member["email"],
        "role": member["role"],
        "active": member.get("active", True),
        "created_at": member.get("created_at"),
    }


def public_elder(elder: dict[str, Any], include_care_code: bool = False) -> dict[str, Any]:
    data = {
        "id": elder["id"],
        "name": elder["name"],
        "date_of_birth": elder.get("date_of_birth"),
        "allergies": elder.get("allergies", []),
        "conditions": elder.get("conditions", []),
        "timezone": elder["timezone"],
        "settings": elder.get("settings", {}),
    }
    if include_care_code:
        data["care_code"] = elder["care_code"]
    return data
