"""Small in-memory sliding-window limiter for user actions."""
from __future__ import annotations

import time
from collections import deque
from typing import Deque

_BUCKETS: dict[tuple[int, str], Deque[float]] = {}
MAX_BUCKETS = 20000


def allow(
    telegram_id: int,
    key: str,
    limit: int,
    window_seconds: float,
    *,
    now: float | None = None,
) -> bool:
    """Return True and record a hit when the action is within its limit."""
    if limit <= 0:
        return True
    current = time.monotonic() if now is None else now
    bucket = _BUCKETS.setdefault((int(telegram_id), key), deque())
    while bucket and current - bucket[0] >= window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(current)
    if len(_BUCKETS) > MAX_BUCKETS:
        _prune(current)
    return True


def _prune(now: float) -> None:
    for bucket_key, bucket in list(_BUCKETS.items()):
        if not bucket or now - bucket[-1] > 3600:
            _BUCKETS.pop(bucket_key, None)


def reset_all() -> None:
    _BUCKETS.clear()


__all__ = ["allow", "reset_all"]
