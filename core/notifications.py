"""Notification fan-out through the shared database.

A notification row is created once (deduped by ``UNIQUE(telegram_id, type,
dedupe_key)``). Whichever bot can reach the recipient sends it and sets
``delivered=1``.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.db import queries as q

logger = logging.getLogger(__name__)


def _render(title: str, body: Optional[str]) -> str:
    return f"{title}\n\n{body}" if body else title


async def notify(
    telegram_id: int,
    type: str,
    title: str,
    body: Optional[str] = None,
    *,
    bot: Any = None,
    sub_id: Optional[int] = None,
    order_id: Optional[int] = None,
    ticket_id: Optional[int] = None,
    dedupe_key: Optional[str] = None,
    reply_markup: Any = None,
    force: bool = False,
) -> bool:
    """Create a notification and optionally deliver it. True only on fresh insert."""
    notification_id = await q.insert_notification(
        telegram_id=telegram_id,
        type=type,
        title=title,
        body=body,
        dedupe_key=dedupe_key,
        sub_id=sub_id,
        order_id=order_id,
        ticket_id=ticket_id,
    )
    if notification_id is None:
        return False

    if bot is not None:
        should_send = True
        if type == "broadcast" and not force:
            user = await q.get_user(telegram_id)
            if user and user.get("mute_broadcasts"):
                should_send = False
        if should_send:
            try:
                await bot.send_message(
                    chat_id=telegram_id,
                    text=_render(title, body),
                    reply_markup=reply_markup,
                )
                await q.mark_notification_delivered(notification_id)
            except Exception:  # delivery is best-effort; row stays pending
                logger.exception("notification delivery failed for %s", telegram_id)

    return True


__all__ = ["notify"]
