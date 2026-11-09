"""Discover Rebecca panel users that have no Telegram ID linked."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from core.rebecca_api import RebeccaClient

logger = logging.getLogger(__name__)

CACHE_TTL = 60.0
MAX_USERS = 5000
PAGE_SIZE = 1000
CHECK_CONCURRENCY = 10

_cache_at = 0.0
_cache_items: list[dict[str, Any]] = []


def invalidate_unlinked_cache() -> None:
    global _cache_at, _cache_items
    _cache_at = 0.0
    _cache_items = []


async def scan_unlinked_panel_users(
    client: RebeccaClient, *, force: bool = False
) -> list[dict[str, Any]]:
    """Return panel users whose ``telegram_id`` is empty (cached briefly)."""
    global _cache_at, _cache_items
    if not force and _cache_at and time.monotonic() - _cache_at < CACHE_TTL:
        return [dict(item) for item in _cache_items]

    entries: list[dict[str, Any]] = []
    offset = 0
    while offset < MAX_USERS:
        page = await client.list_users(offset, PAGE_SIZE)
        if not page:
            break
        entries.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)

    semaphore = asyncio.Semaphore(CHECK_CONCURRENCY)

    async def check(entry: dict[str, Any]) -> dict[str, Any] | None:
        username = str(entry.get("username") or "")
        if not username:
            return None
        try:
            async with semaphore:
                data = await client.get_user(username)
        except Exception:
            logger.warning("panel user check failed for %s", username, exc_info=True)
            return None
        if data is None:
            return None
        if str(data.get("telegram_id") or "").strip():
            return None
        return {
            "username": username,
            "id": entry.get("id"),
            "service_name": data.get("service_name") or entry.get("service_name") or "",
            "status": data.get("status") or entry.get("status") or "unknown",
            "data_limit": data.get("data_limit"),
            "used_traffic": data.get("used_traffic"),
            "expire": data.get("expire"),
        }

    results = await asyncio.gather(*[check(entry) for entry in entries])
    items = sorted(
        (item for item in results if item is not None),
        key=lambda item: item["username"].lower(),
    )
    _cache_at = time.monotonic()
    _cache_items = items
    return [dict(item) for item in items]


__all__ = ["scan_unlinked_panel_users", "invalidate_unlinked_cache"]
