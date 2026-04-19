"""Simple in-memory rate limiting helpers for API endpoints."""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import time

from fastapi import HTTPException, Request, status

from app.core.config import settings


class InMemoryRateLimiter:
    """Thread-safe fixed-window limiter keyed by endpoint + client id."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, bucket: deque[float], window_seconds: int, now: float) -> None:
        cutoff = now - window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

    def allow(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        """Return whether request is allowed and retry-after seconds if blocked."""
        now = time()
        with self._lock:
            bucket = self._events[key]
            self._prune(bucket, window_seconds, now)
            if len(bucket) >= max_requests:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                return False, retry_after
            bucket.append(now)
            return True, 0


_limiter = InMemoryRateLimiter()


def reset_rate_limiter() -> None:
    """Clear limiter state. Intended for tests only."""
    with _limiter._lock:  # pylint: disable=protected-access
        _limiter._events.clear()  # pylint: disable=protected-access


def _client_id(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _enforce(request: Request, endpoint_key: str, max_requests: int) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    client_id = _client_id(request)
    allowed, retry_after = _limiter.allow(
        key=f"{endpoint_key}:{client_id}",
        max_requests=max_requests,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )


def enforce_validate_rate_limit(request: Request) -> None:
    """Apply per-client throttling to the validate endpoint."""
    _enforce(
        request=request,
        endpoint_key="qasm_validate",
        max_requests=settings.RATE_LIMIT_VALIDATE_REQUESTS,
    )


def enforce_analyze_rate_limit(request: Request) -> None:
    """Apply per-client throttling to the analyze endpoint."""
    _enforce(
        request=request,
        endpoint_key="qasm_analyze",
        max_requests=settings.RATE_LIMIT_ANALYZE_REQUESTS,
    )
