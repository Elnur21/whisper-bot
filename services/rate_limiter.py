import time
from collections import defaultdict, deque


class RateLimiter:
    """Sliding-window in-memory rate limiter — one instance shared per process."""

    def __init__(self, max_calls: int, window_seconds: int) -> None:
        self.max_calls = max_calls
        self.window = window_seconds
        self._history: dict[int, deque] = defaultdict(deque)

    def is_allowed(self, user_id: int) -> bool:
        now = time.monotonic()
        dq = self._history[user_id]
        while dq and now - dq[0] > self.window:
            dq.popleft()
        if len(dq) >= self.max_calls:
            return False
        dq.append(now)
        return True

    def retry_after(self, user_id: int) -> float:
        dq = self._history[user_id]
        if not dq:
            return 0.0
        return max(0.0, self.window - (time.monotonic() - dq[0]))
