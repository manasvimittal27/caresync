"""Passcode hashing, code generation, session tokens and login rate limiting."""

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Unambiguous alphabet: no 0/O, 1/I/L, so codes are easy to read aloud and type.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_HASH_SCHEME = "pbkdf2_sha256"


def hash_passcode(passcode: str, iterations: int) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", passcode.encode(), salt, iterations)
    return f"{_HASH_SCHEME}${iterations}${salt.hex()}${digest.hex()}"


def verify_passcode(passcode: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != _HASH_SCHEME:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", passcode.encode(), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(candidate.hex(), digest_hex)


def generate_care_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def generate_passcode(length: int = 8) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


class SessionManager:
    """Signs and verifies the session cookie payload ({elder_id, member_id})."""

    def __init__(self, secret: str, max_age_seconds: int) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt="caresync-session")
        self.max_age_seconds = max_age_seconds

    def issue(self, elder_id: str, member_id: str) -> str:
        return self._serializer.dumps({"e": elder_id, "m": member_id})

    def read(self, token: str) -> tuple[str, str] | None:
        try:
            data = self._serializer.loads(token, max_age=self.max_age_seconds)
        except (BadSignature, SignatureExpired):
            return None
        if not isinstance(data, dict) or "e" not in data or "m" not in data:
            return None
        return data["e"], data["m"]


class RateLimiter:
    """Sliding-window counter of failed attempts per key.

    In-memory, so limits are per Cloud Run instance; acceptable for brute-force
    protection with a small max-instances setting.
    """

    def __init__(
        self, max_attempts: int, window_seconds: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str) -> deque[float]:
        cutoff = self._clock() - self.window_seconds
        bucket = self._failures[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        return bucket

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key)) >= self.max_attempts

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._prune(key).append(self._clock())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
