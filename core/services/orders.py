"""Order state machine and public id generation (``Axxxx``)."""
from __future__ import annotations

import random
from core.db import queries as q

PENDING = "pending"
NEEDS_RESEND = "needs_resend"
UNDER_REVIEW = "under_review"
APPROVED = "approved"
REJECTED = "rejected"
CANCELLED = "cancelled"

STATUSES = frozenset(
    {PENDING, NEEDS_RESEND, UNDER_REVIEW, APPROVED, REJECTED, CANCELLED}
)

# from -> allowed next states
TRANSITIONS: dict[str, frozenset[str]] = {
    PENDING: frozenset({NEEDS_RESEND, UNDER_REVIEW, APPROVED, REJECTED, CANCELLED}),
    NEEDS_RESEND: frozenset({PENDING, UNDER_REVIEW, APPROVED, REJECTED, CANCELLED}),
    UNDER_REVIEW: frozenset({NEEDS_RESEND, APPROVED, REJECTED, CANCELLED}),
    APPROVED: frozenset(),
    REJECTED: frozenset(),
    CANCELLED: frozenset(),
}


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, frozenset())


async def generate_public_id(prefix: str = "A", digits: int = 4) -> str:
    """Generate a unique public order id such as ``A1042``."""
    for _ in range(50):
        candidate = prefix + str(random.randint(10 ** (digits - 1), 10 ** digits - 1))
        if await q.get_order_by_public_id(candidate) is None:
            return candidate
    raise RuntimeError("could not generate a unique order public id")


async def transition_order(order_id: int, new_status: str, **fields) -> bool:
    """Validate and apply a state transition. Returns False if not allowed."""
    order = await q.get_order(order_id)
    if order is None:
        return False
    current = order["status"]
    if not can_transition(current, new_status):
        return False
    await q.set_order_status(order_id, new_status, **fields)
    return True


__all__ = [
    "PENDING", "NEEDS_RESEND", "UNDER_REVIEW", "APPROVED", "REJECTED", "CANCELLED",
    "STATUSES", "TRANSITIONS", "can_transition", "generate_public_id", "transition_order",
]
