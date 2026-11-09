"""Ticket state machine and public id generation (``Txxx``)."""
from __future__ import annotations

import random

from core.db import queries as q

OPEN = "open"
IN_PROGRESS = "in_progress"
RESOLVED = "resolved"
CLOSED = "closed"

STATUSES = frozenset({OPEN, IN_PROGRESS, RESOLVED, CLOSED})

TRANSITIONS: dict[str, frozenset[str]] = {
    OPEN: frozenset({IN_PROGRESS, RESOLVED, CLOSED}),
    IN_PROGRESS: frozenset({RESOLVED, CLOSED, OPEN}),
    RESOLVED: frozenset({CLOSED, OPEN}),
    CLOSED: frozenset({OPEN}),
}


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, frozenset())


async def generate_public_id(prefix: str = "T", digits: int = 3) -> str:
    """Generate a unique public ticket id such as ``T501``."""
    for _ in range(100):
        candidate = prefix + str(random.randint(10 ** (digits - 1), 10 ** digits - 1))
        if await q.get_ticket_by_public_id(candidate) is None:
            return candidate
    raise RuntimeError("could not generate a unique ticket public id")


async def transition_ticket(ticket_id: int, new_status: str, assigned_to=None) -> bool:
    ticket = await q.get_ticket(ticket_id)
    if ticket is None:
        return False
    if not can_transition(ticket["status"], new_status):
        return False
    await q.set_ticket_status(ticket_id, new_status, assigned_to=assigned_to)
    return True


__all__ = [
    "OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED", "STATUSES", "TRANSITIONS",
    "can_transition", "generate_public_id", "transition_ticket",
]
