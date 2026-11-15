"""Firestore collection paths, kept in one place."""

ELDERS = "elders"


def members(elder_id: str) -> str:
    return f"{ELDERS}/{elder_id}/members"


def medications(elder_id: str) -> str:
    return f"{ELDERS}/{elder_id}/medications"


def dose_logs(elder_id: str) -> str:
    return f"{ELDERS}/{elder_id}/dose_logs"


def appointments(elder_id: str) -> str:
    return f"{ELDERS}/{elder_id}/appointments"


def audit_log(elder_id: str) -> str:
    return f"{ELDERS}/{elder_id}/audit_log"


def notifications(elder_id: str) -> str:
    return f"{ELDERS}/{elder_id}/notifications"
