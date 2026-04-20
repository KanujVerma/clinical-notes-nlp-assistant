"""Per-session rate limiter for API endpoints.

A simple in-memory rate limiter using a deque of timestamps per session.
Thread-safe via a lock. Suitable for single-process deployments.
"""

from collections import deque
import time
import threading


class SessionRateLimiter:
    """Tracks call timestamps per session_id. Thread-safe via a lock."""

    def __init__(self):
        self._sessions: dict[str, deque] = {}
        self._lock = threading.Lock()

    def check(self, session_id: str, limit: int = 20, window_s: int = 3600) -> tuple[bool, int]:
        """
        Check if a call is within the rate limit for a session.

        Returns (allowed: bool, retry_after: int).
        - allowed=True means the call is within quota.
        - retry_after is the number of seconds until the oldest call expires (0 when allowed=True).

        Evicts timestamps older than window_s before checking.

        Args:
            session_id: Unique identifier for the session.
            limit: Maximum number of calls allowed in the window.
            window_s: Time window in seconds.

        Returns:
            Tuple of (allowed, retry_after) where:
            - allowed (bool): True if call is allowed, False if rate limited.
            - retry_after (int): Seconds to wait if not allowed (0 if allowed).
        """
        with self._lock:
            # Get or create the deque for this session
            if session_id not in self._sessions:
                self._sessions[session_id] = deque()

            deque_for_session = self._sessions[session_id]
            current_time = time.time()

            # Evict all timestamps older than window_s
            while deque_for_session and deque_for_session[0] <= current_time - window_s:
                deque_for_session.popleft()

            # Check if at or over limit
            if len(deque_for_session) >= limit:
                # Calculate retry_after: when the oldest call expires
                oldest_timestamp = deque_for_session[0]
                retry_after = int(oldest_timestamp + window_s - current_time)
                # Ensure at least 1 second if somehow calculated as negative
                retry_after = max(1, retry_after)
                return (False, retry_after)

            # Within limit: record this call and allow it
            deque_for_session.append(current_time)
            return (True, 0)


# Module-level singleton
_limiter = SessionRateLimiter()


def check_rate_limit(session_id: str, limit: int = 20, window_s: int = 3600) -> tuple[bool, int]:
    """Convenience function using the module singleton.

    Args:
        session_id: Unique identifier for the session.
        limit: Maximum number of calls allowed in the window (default: 20).
        window_s: Time window in seconds (default: 3600).

    Returns:
        Tuple of (allowed, retry_after) where:
        - allowed (bool): True if call is allowed, False if rate limited.
        - retry_after (int): Seconds to wait if not allowed (0 if allowed).
    """
    return _limiter.check(session_id, limit, window_s)
