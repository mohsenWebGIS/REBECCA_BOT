"""Provision a Rebecca subscription for an approved order."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import settings
from core.db import queries as q
from core.rebecca_api import GB, RebeccaAPIError, RebeccaClient
from core.services import orders as order_sm

logger = logging.getLogger(__name__)


async def _plan_data(order: dict[str, Any]) -> tuple[str, float, int]:
    raw = order.get("plan_snapshot")
    snapshot: Any = raw
    if isinstance(raw, str):
        try:
            snapshot = json.loads(raw)
        except (ValueError, TypeError):
            snapshot = None
    if isinstance(snapshot, dict):
        name = str(snapshot.get("name") or snapshot.get("plan_name") or "Plan")
        gb = float(snapshot.get("gb") or snapshot.get("plan_gb") or 0)
        days = int(snapshot.get("days") or snapshot.get("plan_days") or 30)
        return name, gb, days
    plan_id = order.get("plan_id")
    if plan_id is not None:
        plan = await q.get_plan(int(plan_id))
        if plan is not None:
            return str(plan["name"]), float(plan["gb"]), int(plan["days"])
    return "Plan", 0.0, 30


def _absolute_subscription_url(data: dict[str, Any]) -> Optional[str]:
    url = data.get("subscription_url") or data.get("key_subscription_url")
    if not url:
        return None
    if isinstance(url, str) and url.startswith("/"):
        return settings.rebecca_base + url
    return url


def _iso_from_epoch(value: Any) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None


async def _build_username(telegram_id: int, public_id: str) -> str:
    base = f"u{telegram_id}_{public_id}".lower()
    candidate = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base)
    # ensure no collision (public ids are unique, but be defensive)
    existing = await q.get_subscription_by_username(candidate)
    if existing is None:
        return candidate
    suffix = 1
    while await q.get_subscription_by_username(f"{candidate}_{suffix}") is not None:
        suffix += 1
    return f"{candidate}_{suffix}"


async def provision_sub_for_order(
    order: dict[str, Any], client: Optional[RebeccaClient] = None
) -> dict[str, Any]:
    """Create the Rebecca user, persist a subscription row, link the order.

    Raises ``RebeccaAPIError`` on panel failures (caller must not mark paid).
    """
    order_id = int(order["id"])
    telegram_id = int(order["telegram_id"])
    public_id = str(order["public_id"])
    plan_name, plan_gb, plan_days = await _plan_data(order)
    username = await _build_username(telegram_id, public_id)

    owns_client = client is None
    client = client or RebeccaClient()
    try:
        data = await client.create_user(
            username=username,
            plan_gb=plan_gb,
            plan_days=plan_days,
            notes=f"order {public_id}",
        )
        try:
            data = await client.update_user(username, telegram_id=str(telegram_id))
        except RebeccaAPIError:
            logger.exception("failed to set panel telegram_id for %s", username)
    finally:
        if owns_client:
            await client.close()

    subscription_url = _absolute_subscription_url(data)
    used_gb = float(data.get("used_traffic") or 0) / GB
    total_gb = float(data.get("data_limit") or 0) / GB or plan_gb
    expires_at = _iso_from_epoch(data.get("expire"))
    status = str(data.get("status") or "active")

    sub_id = await q.create_subscription(
        telegram_id=telegram_id,
        rebecca_username=username,
        plan_name=plan_name,
        plan_gb=plan_gb,
        plan_days=plan_days,
        subscription_url=subscription_url,
        status=status,
        traffic_total_gb=total_gb,
        expires_at=expires_at,
        source_order_id=order_id,
    )
    await q.update_subscription(sub_id, traffic_used_gb=used_gb)
    await q.update_order(order_id, provisioned_sub_id=sub_id, status=order_sm.APPROVED)

    sub = await q.get_subscription(sub_id)
    assert sub is not None
    logger.info("provisioned order %s -> sub %s (%s)", public_id, sub_id, username)
    return sub


async def renew_sub_for_order(
    order: dict[str, Any], client: Optional[RebeccaClient] = None
) -> dict[str, Any]:
    """Extend an existing panel subscription and add the plan's traffic."""
    order_id = int(order["id"])
    telegram_id = int(order["telegram_id"])
    sub_id = order.get("subscription_id")
    if not sub_id:
        raise RebeccaAPIError(409, "renewal order has no subscription")
    sub = await q.get_subscription(int(sub_id))
    if sub is None or int(sub["telegram_id"]) != telegram_id:
        raise RebeccaAPIError(409, "subscription no longer belongs to the user")
    _plan_name, plan_gb, plan_days = await _plan_data(order)

    owns_client = client is None
    client = client or RebeccaClient()
    try:
        data = await client.get_user(sub["rebecca_username"])
        if not data:
            raise RebeccaAPIError(404, "user not found on panel")
        current_expire = int(data.get("expire") or 0)
        new_expire = max(current_expire, int(time.time())) + int(plan_days * 86400)
        current_limit = int(data.get("data_limit") or 0)
        new_limit = current_limit + int(plan_gb * GB) if current_limit else 0
        await client.update_user(
            sub["rebecca_username"],
            expire=new_expire,
            data_limit=new_limit,
            status="active",
        )
    finally:
        if owns_client:
            await client.close()

    refreshed = await q.get_subscription(int(sub_id))
    if refreshed is None:
        raise RebeccaAPIError(404, "local subscription missing after renewal")

    used_gb = float(data.get("used_traffic") or 0) / GB
    total_gb = new_limit / GB if new_limit else plan_gb
    await q.update_subscription(
        int(sub_id),
        traffic_used_gb=used_gb,
        traffic_total_gb=total_gb,
        expires_at=_iso_from_epoch(new_expire),
        status="active",
        subscription_url=refreshed.get("subscription_url"),
    )
    await q.update_order(
        order_id, provisioned_sub_id=int(sub_id), status=order_sm.APPROVED
    )
    refreshed = await q.get_subscription(int(sub_id))
    assert refreshed is not None
    logger.info(
        "renewed order %s -> sub %s (%s)", order["public_id"], sub_id,
        sub["rebecca_username"],
    )
    return refreshed


__all__ = ["provision_sub_for_order", "renew_sub_for_order"]
