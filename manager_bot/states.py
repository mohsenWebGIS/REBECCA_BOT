"""Per-admin pending-input state for the manager bot."""
from __future__ import annotations

from typing import Any, Optional

_STATES: dict[int, dict[str, Any]] = {}


def set_state(telegram_id: int, action: str, **data: Any) -> None:
    state = {"action": action}
    state.update(data)
    _STATES[telegram_id] = state


def get_state(telegram_id: int) -> dict[str, Any]:
    return _STATES.get(telegram_id, {})


def get_action(telegram_id: int) -> Optional[str]:
    return _STATES.get(telegram_id, {}).get("action")


def clear_state(telegram_id: int) -> None:
    _STATES.pop(telegram_id, None)
