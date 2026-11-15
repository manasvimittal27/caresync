from app.security import RateLimiter, SessionManager, generate_care_code, hash_passcode, verify_passcode


def test_security_headers_present(client):
    res = client.get("/healthz")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in res.headers["Content-Security-Policy"]


def test_api_responses_not_cached(owner):
    c, _ = owner
    assert c.get("/api/me").headers["Cache-Control"] == "no-store"


def test_passcode_hash_roundtrip_and_salting():
    first = hash_passcode("secret-1", 1000)
    second = hash_passcode("secret-1", 1000)
    assert first != second  # Unique salt per hash.
    assert verify_passcode("secret-1", first)
    assert not verify_passcode("secret-2", first)
    assert not verify_passcode("secret-1", "garbage")


def test_session_tokens_cannot_be_forged():
    sessions = SessionManager("key-a", 60)
    token = sessions.issue("elder1", "member1")
    assert sessions.read(token) == ("elder1", "member1")
    assert SessionManager("key-b", 60).read(token) is None


def test_rate_limiter_window_expires():
    now = [0.0]
    limiter = RateLimiter(max_attempts=2, window_seconds=10, clock=lambda: now[0])
    limiter.record_failure("k")
    limiter.record_failure("k")
    assert limiter.is_blocked("k")
    now[0] = 11.0
    assert not limiter.is_blocked("k")


def test_care_codes_use_unambiguous_characters():
    for _ in range(50):
        code = generate_care_code()
        assert len(code) == 6 and not set(code) & set("0O1IL")
