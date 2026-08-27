"""A small in-process, fixed-window-per-key rate limiter. Deliberately not
backed by Redis/DB: this project runs as a single Uvicorn process, so
in-memory state is sufficient and avoids adding an infra dependency purely
for a defensive limit. If this backend is ever scaled to multiple worker
processes, swap this for a shared store (Redis INCR + TTL is the standard
approach) since each worker would otherwise track its own counters."""
import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
