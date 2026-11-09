"""Toman pricing rules.

Price is per GB with an automatic volume discount above a threshold. Promo
codes are applied on top of the post-volume price.
"""
from __future__ import annotations

from core.config import settings


def price_per_gb() -> int:
    return int(settings.price_per_gb_toman)


def volume_discount_percent(gb: float) -> int:
    return int(settings.bulk_discount_percent) if float(gb) > settings.bulk_threshold_gb else 0


def base_price(gb: float) -> int:
    return int(round(float(gb) * price_per_gb()))


def volume_discount(gb: float) -> int:
    return int(round(base_price(gb) * volume_discount_percent(gb) / 100.0))


def price_after_volume(gb: float) -> int:
    return base_price(gb) - volume_discount(gb)


def plan_prices(plan: dict) -> tuple[int, int, int]:
    """Return (base, volume_discount, price_after_volume) in Toman."""
    gb = float(plan["gb"])
    base = base_price(gb)
    volume = volume_discount(gb)
    return base, volume, base - volume


__all__ = [
    "price_per_gb", "volume_discount_percent", "base_price", "volume_discount",
    "price_after_volume", "plan_prices",
]
