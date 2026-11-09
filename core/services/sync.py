"""Import existing panel users that have a Telegram id set.

Subscriptions created through the bot are linked at provisioning time. This
handles the other case: users created directly in the Rebecca panel with
``telegram_id`` filled in. They are imported into the shared subscriptions table
so the matching Telegram account can see them.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import settings
from core.db import queries as q
from core.rebecca_api import GB, RebeccaClient

logger = logging.getLogger(__name__)

SYNC_COOLDOWN_SECONDS = 60.0
SNAPSHOT_TTL_SECONDS = 30.0

_last_sync: dict[int, float] = {}
_sync_locks: dict[int, asyncio.Lock] = {}
_snapshot_at = 0.0
_snapshot: list[dict[str, Any]] = []
_snapshot_lock = asyncio.Lock()


def _iso(epoch: Any) -> Optional[str]:
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None


def _absolute(url: Any) -> Optional[str]:
    if not url:
        return None
    url = str(url)
    return settings.rebecca_base + url if url.startswith("/") else url


async def link_panel_user(telegram_id: int, data: dict[str, Any]) -> int:
    username = data.get("username")
    if not username:
        return 0
    total_gb = float(data.get("data_limit") or 0) / GB
    used_gb = float(data.get("used_traffic") or 0) / GB
    await q.upsert_panel_subscription(
        telegram_id=telegram_id,
        rebecca_username=str(username),
        plan_name=data.get("service_name") or "Panel",
        plan_gb=total_gb or None,
        plan_days=None,
        subscription_url=_absolute(
            data.get("subscription_url") or data.get("key_subscription_url")
        ),
        status=str(data.get("status") or "active"),
        traffic_used_gb=used_gb,
        traffic_total_gb=total_gb,
        expires_at=_iso(data.get("expire")),
    )
    return 1


async def _panel_snapshot(client: RebeccaClient) -> list[dict[str, Any]]:
    global _snapshot_at, _snapshot
    now = time.monotonic()
    if _snapshot_at and now - _snapshot_at < SNAPSHOT_TTL_SECONDS:
        return list(_snapshot)
    async with _snapshot_lock:
        now = time.monotonic()
        if _snapshot_at and now - _snapshot_at < SNAPSHOT_TTL_SECONDS:
            return list(_snapshot)
        listing = await client.list_users(0, 1000)

        async def fetch(entry: dict[str, Any]) -> Optional[dict[str, Any]]:
            username = entry.get("username")
            if not username:
                return None
            try:
                return await client.get_user(str(username))
            except Exception:
                logger.warning("panel user fetch failed during sync for %s", username)
                return None

        results = await asyncio.gather(*[fetch(entry) for entry in listing])
        _snapshot = [item for item in results if item]
        _snapshot_at = time.monotonic()
        return list(_snapshot)


async def sync_for_telegram_id(telegram_id: int, client: RebeccaClient) -> int:
    """Ensure panel users tagged with this Telegram id exist locally."""
    if time.monotonic() - _last_sync.get(int(telegram_id), 0.0) < SYNC_COOLDOWN_SECONDS:
        return 0
    lock = _sync_locks.setdefault(int(telegram_id), asyncio.Lock())
    async with lock:
        if (
            time.monotonic() - _last_sync.get(int(telegram_id), 0.0)
            < SYNC_COOLDOWN_SECONDS
        ):
            return 0
        _last_sync[int(telegram_id)] = time.monotonic()
        try:
            snapshot = await _panel_snapshot(client)
        except Exception:
            logger.exception("panel listing failed during sync")
            return 0

        linked = 0
        for data in snapshot:
            if str(data.get("telegram_id") or "") != str(telegram_id):
                continue
            try:
                linked += await link_panel_user(int(telegram_id), data)
            except Exception:
                logger.exception(
                    "failed to link panel sub for telegram_id %s", telegram_id
                )
        if linked:
            logger.info(
                "sync linked %s panel sub(s) to telegram_id %s", linked, telegram_id
            )
        return linked


def reset_sync_cache() -> None:
    global _snapshot_at, _snapshot
    _last_sync.clear()
    _snapshot_at = 0.0
    _snapshot = []


__all__ = ["sync_for_telegram_id", "link_panel_user", "reset_sync_cache"]
