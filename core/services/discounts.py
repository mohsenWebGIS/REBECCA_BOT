"""Promo-code validation used by the user bot's purchase flow."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from core.db import queries as q
from core.pricing import price_after_volume

Result = tuple[bool, str, float]


def _parse_applies_to(raw: Any) -> Optional[set[int]]:
    """Return the set of plan ids, or None meaning "all plans"."""
    if raw is None or raw == "" or raw == "all":
        return None
    if isinstance(raw, (list, tuple, set)):
        return {int(x) for x in raw}
    text = str(raw).strip()
    if text.lower() == "all":
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return {int(x) for x in parsed}
        if isinstance(parsed, (int, str)):
            return {int(parsed)}
    except (ValueError, TypeError):
        pass
    return {int(part) for part in text.replace(" ", "").split(",") if part}


def _is_expired(expires_at: Optional[str]) -> bool:
    if not expires_at:
        return False
    try:
        parsed = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(str(expires_at), "%Y-%m-%d")
        except ValueError:
            return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed < datetime.now(timezone.utc)


def amount_for_plan(discount: dict[str, Any], plan: dict[str, Any]) -> Optional[float]:
    """Discount amount in Toman for a plan, or None if the code does not apply.

    Percent discounts apply to the price after the automatic volume discount.
    """
    applies_to = _parse_applies_to(discount.get("applies_to"))
    if applies_to is not None and int(plan["id"]) not in applies_to:
        return None
    price = float(price_after_volume(float(plan["gb"])))
    if discount.get("type") == "percent":
        amount = price * float(discount.get("value") or 0) / 100.0
    else:
        amount = float(discount.get("value") or 0)
    return round(max(0.0, min(amount, price)), 2)


async def validate_code(telegram_id: int, plan_id: int, code: str) -> Result:
    """Validate ``code`` for ``telegram_id`` on ``plan_id``.

    Returns ``(ok, reason, amount_off)`` where ``amount_off`` is in Toman.
    """
    plan = await q.get_plan(plan_id)
    if plan is None:
        return False, "Unknown plan.", 0.0

    discount = await q.get_discount(code.strip())
    if discount is None:
        return False, "Invalid promo code.", 0.0
    if not discount["active"]:
        return False, "This promo code is no longer active.", 0.0
    if _is_expired(discount["expires_at"]):
        return False, "This promo code has expired.", 0.0

    applies_to = _parse_applies_to(discount["applies_to"])
    if applies_to is not None and int(plan_id) not in applies_to:
        return False, "This promo code does not apply to the selected plan.", 0.0

    max_uses = discount["max_uses"]
    if max_uses is not None:
        used = await q.count_redemptions(discount["code"])
        if used >= int(max_uses):
            return False, "This promo code has reached its usage limit.", 0.0

    per_user_max = int(discount["per_user_max"] or 1)
    user_used = await q.count_user_redemptions(discount["code"], telegram_id)
    if user_used >= per_user_max:
        return False, "You have already used this promo code.", 0.0

    price = float(price_after_volume(float(plan["gb"])))
    if discount["type"] == "percent":
        amount = price * float(discount["value"]) / 100.0
    else:
        amount = float(discount["value"])
    amount = max(0.0, min(amount, price))
    return True, "ok", round(amount, 2)


__all__ = ["validate_code", "Result"]
