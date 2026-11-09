"""In-memory per-user FSM and AI rate limiting for the user bot."""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Optional

# telegram_id -> {"flow": str, ...state data}
_STATES: dict[int, dict[str, Any]] = {}
# telegram_id -> timestamps of recent AI messages (in-memory half of the limit)
_AI_HITS: dict[int, deque[float]] = {}

FLOW_RECEIPT = "awaiting_receipt"
FLOW_TICKET_DESC = "awaiting_ticket_desc"
FLOW_TICKET_REPLY = "awaiting_ticket_reply"
FLOW_PROMO = "awaiting_promo"
FLOW_AI = "ai_chat"
FLOW_SUB_RENAME = "awaiting_sub_name"
FLOW_TRANSFER = "awaiting_transfer_recipient"
FLOW_INVITE = "awaiting_invite_code"


def set_state(telegram_id: int, flow: str, **data: Any) -> None:
    state = _STATES.setdefault(telegram_id, {})
    state["flow"] = flow
    state.update(data)


def get_state(telegram_id: int) -> dict[str, Any]:
    return _STATES.get(telegram_id, {})


def get_flow(telegram_id: int) -> Optional[str]:
    return _STATES.get(telegram_id, {}).get("flow")


def update_state(telegram_id: int, **data: Any) -> None:
    _STATES.setdefault(telegram_id, {}).update(data)


def clear_state(telegram_id: int) -> None:
    _STATES.pop(telegram_id, None)


def ai_rate_limited(telegram_id: int, limit: int = 20, window: float = 3600.0) -> bool:
    now = time.time()
    hits = _AI_HITS.setdefault(telegram_id, deque())
    while hits and now - hits[0] > window:
        hits.popleft()
    if len(hits) >= limit:
        return True
    hits.append(now)
    return False


def reset_ai_rate(telegram_id: int) -> None:
    _AI_HITS.pop(telegram_id, None)
