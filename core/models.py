"""Pydantic v2 models mirroring the SQLite rows.

Timestamps are kept as TEXT (ISO-8601), matching the schema.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class User(ORMModel):
    telegram_id: int
    username: Optional[str] = None
    display_name: Optional[str] = None
    joined_at: Optional[str] = None
    banned: int = 0
    mute_broadcasts: int = 0
    preferred_lang: str = "en"
    lang_selected: int = 0
    last_seen_at: Optional[str] = None


class Plan(ORMModel):
    id: int
    name: str
    gb: float
    days: int
    price_toman: float
    active: int = 1
    sort_order: int = 0


class Subscription(ORMModel):
    id: int
    telegram_id: int
    rebecca_username: str
    plan_name: Optional[str] = None
    plan_gb: Optional[float] = None
    plan_days: Optional[int] = None
    subscription_url: Optional[str] = None
    status: str = "active"
    traffic_used_gb: float = 0.0
    traffic_total_gb: float = 0.0
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    source_order_id: Optional[int] = None


class Order(ORMModel):
    id: int
    public_id: str
    telegram_id: int
    plan_id: Optional[int] = None
    plan_snapshot: Optional[str] = None
    kind: str = "new"
    subscription_id: Optional[int] = None
    list_price: Optional[float] = None
    discount_code: Optional[str] = None
    discount_toman: float = 0.0
    volume_discount_toman: float = 0.0
    final_price: Optional[float] = None
    receipt_path: Optional[str] = None
    receipt_history: str = "[]"
    status: str = "pending"
    reject_reason: Optional[str] = None
    reviewer_id: Optional[int] = None
    reviewed_at: Optional[str] = None
    provisioned_sub_id: Optional[int] = None
    created_at: Optional[str] = None


class OrderNote(ORMModel):
    id: int
    order_id: int
    admin_id: int
    note: str
    created_at: Optional[str] = None


class Ticket(ORMModel):
    id: int
    public_id: str
    telegram_id: int
    category: str
    description: Optional[str] = None
    screenshot_path: Optional[str] = None
    status: str = "open"
    assigned_to: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TicketMessage(ORMModel):
    id: int
    ticket_id: int
    sender_role: str
    sender_id: Optional[int] = None
    body: Optional[str] = None
    file_path: Optional[str] = None
    created_at: Optional[str] = None


class Discount(ORMModel):
    code: str
    type: str
    value: float
    applies_to: str = "all"
    max_uses: Optional[int] = None
    per_user_max: int = 1
    expires_at: Optional[str] = None
    active: int = 1
    created_at: Optional[str] = None


class DiscountRedemption(ORMModel):
    id: int
    code: str
    telegram_id: int
    order_id: Optional[int] = None
    created_at: Optional[str] = None


class Notification(ORMModel):
    id: int
    telegram_id: int
    type: str
    dedupe_key: Optional[str] = None
    title: str
    body: Optional[str] = None
    sub_id: Optional[int] = None
    order_id: Optional[int] = None
    ticket_id: Optional[int] = None
    is_read: int = 0
    delivered: int = 0
    created_at: Optional[str] = None


class AdminAudit(ORMModel):
    id: int
    admin_id: int
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    payload_before: Optional[str] = None
    payload_after: Optional[str] = None
    created_at: Optional[str] = None


class AIConversation(ORMModel):
    id: int
    telegram_id: int
    role: str
    content: str
    created_at: Optional[str] = None


class ManagerPref(ORMModel):
    telegram_id: int
    lang: str = "en"


__all__ = [
    "User", "Plan", "Subscription", "Order", "OrderNote", "Ticket",
    "TicketMessage", "Discount", "DiscountRedemption", "Notification",
    "AdminAudit", "AIConversation", "ManagerPref",
]
