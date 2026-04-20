"""Tests for the per-session rate limiter."""

import time
import pytest

from backend.utils.rate_limit import SessionRateLimiter, check_rate_limit


# ---------------------------------------------------------------------------
# Test: First call allowed
# ---------------------------------------------------------------------------

def test_first_call_allowed():
    """First call to a new session should be allowed."""
    limiter = SessionRateLimiter()
    allowed, retry_after = limiter.check("session-1")
    assert allowed is True
    assert retry_after == 0


# ---------------------------------------------------------------------------
# Test: Calls within limit are allowed
# ---------------------------------------------------------------------------

def test_calls_within_limit_allowed():
    """All calls up to the limit should be allowed."""
    limiter = SessionRateLimiter()
    session_id = "session-2"

    # Make 20 calls (default limit)
    for i in range(20):
        allowed, retry_after = limiter.check(session_id)
        assert allowed is True, f"Call {i+1} should be allowed"
        assert retry_after == 0, f"Call {i+1} should have retry_after=0"


# ---------------------------------------------------------------------------
# Test: Call at limit is denied
# ---------------------------------------------------------------------------

def test_call_at_limit_denied():
    """The 21st call (over the default limit of 20) should be denied."""
    limiter = SessionRateLimiter()
    session_id = "session-3"

    # Make 20 calls (fill the limit)
    for i in range(20):
        allowed, _ = limiter.check(session_id)
        assert allowed is True

    # 21st call should be denied
    allowed, retry_after = limiter.check(session_id)
    assert allowed is False
    assert retry_after > 0


# ---------------------------------------------------------------------------
# Test: Retry_after is positive when denied
# ---------------------------------------------------------------------------

def test_retry_after_is_positive():
    """When a call is denied, retry_after should be >= 1."""
    limiter = SessionRateLimiter()
    session_id = "session-4"

    # Fill the limit
    for i in range(20):
        limiter.check(session_id)

    # Deny the next call and check retry_after
    allowed, retry_after = limiter.check(session_id)
    assert allowed is False
    assert retry_after >= 1


# ---------------------------------------------------------------------------
# Test: Different sessions are independent
# ---------------------------------------------------------------------------

def test_different_sessions_are_independent():
    """Rate limits for different sessions should not affect each other."""
    limiter = SessionRateLimiter()

    # Fill session A to its limit
    for i in range(20):
        limiter.check("session-a")

    # Session A should now be rate limited
    allowed_a, _ = limiter.check("session-a")
    assert allowed_a is False

    # But session B should not be affected
    allowed_b, retry_after_b = limiter.check("session-b")
    assert allowed_b is True
    assert retry_after_b == 0


# ---------------------------------------------------------------------------
# Test: Old timestamps are evicted
# ---------------------------------------------------------------------------

def test_old_timestamps_evicted():
    """Timestamps older than window_s should be evicted, allowing new calls."""
    limiter = SessionRateLimiter()
    session_id = "session-5"

    # Manually inject old timestamps into the deque
    # We'll use a small window (1 second) to make the test faster
    old_time = time.time() - 2  # 2 seconds ago
    for i in range(20):
        limiter._sessions[session_id] = limiter._sessions.get(session_id, __import__('collections').deque())
        limiter._sessions[session_id].append(old_time)

    # With old timestamps in the deque, a new call should be allowed
    # because they should be evicted (since window_s=1, and timestamps are 2 seconds old)
    allowed, retry_after = limiter.check(session_id, limit=20, window_s=1)
    assert allowed is True, "Old timestamps should be evicted, allowing the call"
    assert retry_after == 0


# ---------------------------------------------------------------------------
# Test: Module-level convenience function
# ---------------------------------------------------------------------------

def test_module_level_check_rate_limit():
    """The module-level check_rate_limit() function should use the singleton."""
    # First call should be allowed
    allowed_1, retry_after_1 = check_rate_limit("session-module-1")
    assert allowed_1 is True
    assert retry_after_1 == 0

    # Same session, multiple calls should work
    for i in range(19):
        allowed, retry_after = check_rate_limit("session-module-1")
        assert allowed is True

    # 21st call should be denied
    allowed_21, retry_after_21 = check_rate_limit("session-module-1")
    assert allowed_21 is False
    assert retry_after_21 >= 1
