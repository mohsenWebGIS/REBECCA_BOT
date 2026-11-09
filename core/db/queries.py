"""Typed async query helpers, one group per table.

Every statement is parameterised. Dynamic UPDATE helpers only accept column
names from an explicit allow-list, so user input can never become SQL.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

import aiosqlite

from core.db import get_db

Record = dict[str, Any]


def _row(row: Optional[aiosqlite.Row]) -> Optional[Record]:
    return dict(row) if row is not None else None


def _rows(rows: Iterable[aiosqlite.Row]) -> list[Record]:
    return [dict(r) for r in rows]


def _set_clause(columns: Iterable[str], allowed: frozenset[str]) -> str:
    cols = [c for c in columns if c in allowed]
    if not cols:
        raise ValueError("no updatable columns supplied")
    return ", ".join([c + " = ?" for c in cols])


async def _update(
    table: str,
    key_column: str,
    key_value: Any,
    fields: Record,
    allowed: frozenset[str],
) -> None:
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    clause = _set_clause(fields.keys(), allowed)
    params = list(fields.values()) + [key_value]
    db = await get_db()
    await db.execute(
        "UPDATE " + table + " SET " + clause + " WHERE " + key_column + " = ?",
        params,
    )
    await db.commit()


# --------------------------------------------------------------------------
# users
# --------------------------------------------------------------------------
USER_COLUMNS = frozenset(
    {
        "username",
        "display_name",
        "invite_code",
        "banned",
        "mute_broadcasts",
        "preferred_lang",
        "lang_selected",
        "last_seen_at",
    }
)


async def upsert_user(
    telegram_id: int,
    username: Optional[str] = None,
    display_name: Optional[str] = None,
    preferred_lang: str = "en",
) -> Record:
    db = await get_db()
    await db.execute(
        "INSERT INTO users (telegram_id, username, display_name, preferred_lang, last_seen_at) "
        "VALUES (?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(telegram_id) DO UPDATE SET "
        "username = COALESCE(excluded.username, users.username), "
        "display_name = COALESCE(excluded.display_name, users.display_name), "
        "last_seen_at = datetime('now')",
        (telegram_id, username, display_name, preferred_lang),
    )
    await db.commit()
    user = await get_user(telegram_id)
    assert user is not None
    return user


async def get_user(telegram_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cur:
        return _row(await cur.fetchone())


async def update_user(telegram_id: int, **fields: Any) -> None:
    await _update("users", "telegram_id", telegram_id, fields, USER_COLUMNS)


async def get_user_by_invite_code(code: str) -> Optional[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM users WHERE invite_code = ?", (code,)
    ) as cur:
        return _row(await cur.fetchone())


async def set_user_banned(telegram_id: int, banned: bool) -> None:
    await update_user(telegram_id, banned=int(banned))


async def set_user_muted(telegram_id: int, muted: bool) -> None:
    await update_user(telegram_id, mute_broadcasts=int(muted))


async def touch_user(telegram_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE users SET last_seen_at = datetime('now') WHERE telegram_id = ?",
        (telegram_id,),
    )
    await db.commit()


async def list_users(offset: int = 0, limit: int = 10) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM users ORDER BY joined_at DESC, telegram_id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ) as cur:
        return _rows(await cur.fetchall())


async def search_users(query: str, limit: int = 50) -> list[Record]:
    db = await get_db()
    like = "%" + query + "%"
    async with db.execute(
        "SELECT * FROM users WHERE CAST(telegram_id AS TEXT) LIKE ? OR username LIKE ? "
        "ORDER BY joined_at DESC LIMIT ?",
        (like, like, limit),
    ) as cur:
        return _rows(await cur.fetchall())


async def count_users() -> int:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) AS n FROM users") as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def list_users_without_subscriptions(
    offset: int = 0, limit: int = 10
) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT u.* FROM users u "
        "WHERE NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.telegram_id = u.telegram_id) "
        "ORDER BY u.joined_at DESC, u.telegram_id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ) as cur:
        return _rows(await cur.fetchall())


async def count_users_without_subscriptions() -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS n FROM users u "
        "WHERE NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.telegram_id = u.telegram_id)"
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def user_has_purchase_history(telegram_id: int) -> bool:
    db = await get_db()
    async with db.execute(
        "SELECT ("
        "EXISTS (SELECT 1 FROM orders WHERE telegram_id = ? AND status = 'approved') "
        "OR EXISTS (SELECT 1 FROM subscriptions WHERE telegram_id = ?)"
        ") AS has_history",
        (telegram_id, telegram_id),
    ) as cur:
        row = await cur.fetchone()
    return bool(row["has_history"]) if row else False


async def get_meta(key: str) -> Optional[str]:
    db = await get_db()
    async with db.execute("SELECT value FROM schema_meta WHERE key = ?", (key,)) as cur:
        row = await cur.fetchone()
    return row["value"] if row else None


async def set_meta(key: str, value: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO schema_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await db.commit()


# --------------------------------------------------------------------------
# card access
# --------------------------------------------------------------------------
async def get_card_access(telegram_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM card_access WHERE telegram_id = ?", (telegram_id,)
    ) as cur:
        return _row(await cur.fetchone())


async def upsert_card_request(telegram_id: int) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO card_access (telegram_id, status, requested_at) "
        "VALUES (?, 'pending', datetime('now')) "
        "ON CONFLICT(telegram_id) DO UPDATE SET "
        "status = 'pending', requested_at = datetime('now'), "
        "reviewed_by = NULL, reviewed_at = NULL",
        (telegram_id,),
    )
    await db.commit()


async def set_card_access(
    telegram_id: int, status: str, reviewed_by: Optional[int] = None
) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO card_access (telegram_id, status, requested_at, reviewed_by, reviewed_at) "
        "VALUES (?, ?, datetime('now'), ?, datetime('now')) "
        "ON CONFLICT(telegram_id) DO UPDATE SET "
        "status = excluded.status, reviewed_by = excluded.reviewed_by, "
        "reviewed_at = datetime('now')",
        (telegram_id, status, reviewed_by),
    )
    await db.commit()


async def delete_card_access(telegram_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM card_access WHERE telegram_id = ?", (telegram_id,))
    await db.commit()


async def list_card_requests(status: str = "pending") -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT c.*, u.username FROM card_access c "
        "LEFT JOIN users u ON u.telegram_id = c.telegram_id "
        "WHERE c.status = ? ORDER BY c.requested_at ASC",
        (status,),
    ) as cur:
        return _rows(await cur.fetchall())


async def count_card_requests(status: str = "pending") -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS n FROM card_access WHERE status = ?", (status,)
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def user_ids_active(days: int = 7) -> list[int]:
    db = await get_db()
    modifier = f"-{int(days)} days"
    async with db.execute(
        "SELECT telegram_id FROM users WHERE last_seen_at >= datetime('now', ?)",
        (modifier,),
    ) as cur:
        return [int(r["telegram_id"]) for r in await cur.fetchall()]


async def user_ids_expiring(days: int = 7) -> list[int]:
    db = await get_db()
    modifier = f"+{int(days)} days"
    async with db.execute(
        "SELECT DISTINCT telegram_id FROM subscriptions "
        "WHERE status = 'active' AND expires_at IS NOT NULL "
        "AND expires_at <= datetime('now', ?) AND expires_at > datetime('now')",
        (modifier,),
    ) as cur:
        return [int(r["telegram_id"]) for r in await cur.fetchall()]


async def user_ids_high_traffic(pct: float = 90.0) -> list[int]:
    db = await get_db()
    async with db.execute(
        "SELECT DISTINCT telegram_id FROM subscriptions "
        "WHERE traffic_total_gb > 0 AND (traffic_used_gb / traffic_total_gb) >= ?",
        (pct / 100.0,),
    ) as cur:
        return [int(r["telegram_id"]) for r in await cur.fetchall()]


async def revenue_since(modifier: str) -> float:
    db = await get_db()
    async with db.execute(
        "SELECT COALESCE(SUM(final_price), 0) AS total FROM orders "
        "WHERE status = 'approved' AND COALESCE(reviewed_at, created_at) >= datetime('now', ?)",
        (modifier,),
    ) as cur:
        row = await cur.fetchone()
    return float(row["total"]) if row else 0.0


async def orders_status_counts_since(modifier: str) -> dict[str, int]:
    db = await get_db()
    async with db.execute(
        "SELECT status, COUNT(*) AS n FROM orders WHERE created_at >= datetime('now', ?) "
        "GROUP BY status",
        (modifier,),
    ) as cur:
        return {r["status"]: int(r["n"]) for r in await cur.fetchall()}


async def avg_review_seconds(modifier: str) -> Optional[float]:
    db = await get_db()
    async with db.execute(
        "SELECT AVG((julianday(reviewed_at) - julianday(created_at)) * 86400.0) AS avg "
        "FROM orders WHERE reviewed_at IS NOT NULL AND created_at >= datetime('now', ?)",
        (modifier,),
    ) as cur:
        row = await cur.fetchone()
    return float(row["avg"]) if row and row["avg"] is not None else None


async def top_promos(limit: int = 5, modifier: str = "-30 days") -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT code, COUNT(*) AS uses FROM discount_redemptions "
        "WHERE created_at >= datetime('now', ?) GROUP BY code ORDER BY uses DESC LIMIT ?",
        (modifier, limit),
    ) as cur:
        return _rows(await cur.fetchall())


async def count_users_since(modifier: str) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS n FROM users WHERE joined_at >= datetime('now', ?)", (modifier,)
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def count_active_users_since(modifier: str) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS n FROM users WHERE last_seen_at >= datetime('now', ?)", (modifier,)
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def user_total_paid(telegram_id: int) -> float:
    db = await get_db()
    async with db.execute(
        "SELECT COALESCE(SUM(final_price), 0) AS total FROM orders "
        "WHERE telegram_id = ? AND status = 'approved'",
        (telegram_id,),
    ) as cur:
        row = await cur.fetchone()
    return float(row["total"]) if row else 0.0


async def user_rejection_count(telegram_id: int) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE telegram_id = ? AND status = 'rejected'",
        (telegram_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def list_all_subscriptions(limit: int = 5000) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM subscriptions ORDER BY id DESC LIMIT ?", (limit,)
    ) as cur:
        return _rows(await cur.fetchall())


async def list_all_orders(limit: int = 5000) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
    ) as cur:
        return _rows(await cur.fetchall())


async def list_user_ids(exclude: Iterable[int] = ()) -> list[int]:
    excluded = list(exclude)
    db = await get_db()
    if excluded:
        placeholders = ", ".join(["?"] * len(excluded))
        sql = "SELECT telegram_id FROM users WHERE telegram_id NOT IN (" + placeholders + ")"
        async with db.execute(sql, excluded) as cur:
            return [int(r["telegram_id"]) for r in await cur.fetchall()]
    async with db.execute("SELECT telegram_id FROM users") as cur:
        return [int(r["telegram_id"]) for r in await cur.fetchall()]


# --------------------------------------------------------------------------
# plans
# --------------------------------------------------------------------------
PLAN_COLUMNS = frozenset({"name", "gb", "days", "price_toman", "active", "sort_order"})


async def create_plan(
    name: str, gb: float, days: int, price_toman: float,
    active: bool = True, sort_order: int = 0,
) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO plans (name, gb, days, price_toman, active, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
        (name, gb, days, price_toman, int(active), sort_order),
    )
    await db.commit()
    return int(cur.lastrowid)


async def get_plan(plan_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)) as cur:
        return _row(await cur.fetchone())


async def list_active_plans() -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM plans WHERE active = 1 ORDER BY sort_order, id"
    ) as cur:
        return _rows(await cur.fetchall())


async def list_plans() -> list[Record]:
    db = await get_db()
    async with db.execute("SELECT * FROM plans ORDER BY sort_order, id") as cur:
        return _rows(await cur.fetchall())


async def update_plan(plan_id: int, **fields: Any) -> None:
    await _update("plans", "id", plan_id, fields, PLAN_COLUMNS)


async def count_plans() -> int:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) AS n FROM plans") as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


# --------------------------------------------------------------------------
# subscriptions
# --------------------------------------------------------------------------
SUB_COLUMNS = frozenset(
    {
        "telegram_id",
        "rebecca_username",
        "display_name",
        "plan_name",
        "plan_gb",
        "plan_days",
        "subscription_url",
        "status",
        "traffic_used_gb",
        "traffic_total_gb",
        "expires_at",
        "source_order_id",
    }
)


async def create_subscription(
    telegram_id: int,
    rebecca_username: str,
    plan_name: Optional[str] = None,
    plan_gb: Optional[float] = None,
    plan_days: Optional[int] = None,
    subscription_url: Optional[str] = None,
    status: str = "active",
    traffic_total_gb: float = 0.0,
    expires_at: Optional[str] = None,
    source_order_id: Optional[int] = None,
) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO subscriptions "
        "(telegram_id, rebecca_username, plan_name, plan_gb, plan_days, subscription_url, "
        " status, traffic_total_gb, expires_at, source_order_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            telegram_id, rebecca_username, plan_name, plan_gb, plan_days,
            subscription_url, status, traffic_total_gb, expires_at, source_order_id,
        ),
    )
    await db.commit()
    return int(cur.lastrowid)


async def get_subscription(sub_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,)) as cur:
        return _row(await cur.fetchone())


async def upsert_panel_subscription(
    telegram_id: int,
    rebecca_username: str,
    plan_name: Optional[str] = None,
    plan_gb: Optional[float] = None,
    plan_days: Optional[int] = None,
    subscription_url: Optional[str] = None,
    status: str = "active",
    traffic_used_gb: float = 0.0,
    traffic_total_gb: float = 0.0,
    expires_at: Optional[str] = None,
) -> int:
    """Insert/link a panel user to a Telegram id (UNIQUE on rebecca_username)."""
    db = await get_db()
    await db.execute(
        "INSERT INTO subscriptions "
        "(telegram_id, rebecca_username, plan_name, plan_gb, plan_days, subscription_url, "
        " status, traffic_used_gb, traffic_total_gb, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(rebecca_username) DO UPDATE SET "
        "telegram_id = excluded.telegram_id, "
        "subscription_url = COALESCE(excluded.subscription_url, subscriptions.subscription_url), "
        "status = excluded.status, "
        "traffic_used_gb = excluded.traffic_used_gb, "
        "traffic_total_gb = excluded.traffic_total_gb, "
        "expires_at = excluded.expires_at, "
        "plan_name = COALESCE(subscriptions.plan_name, excluded.plan_name), "
        "plan_gb = COALESCE(subscriptions.plan_gb, excluded.plan_gb), "
        "plan_days = COALESCE(subscriptions.plan_days, excluded.plan_days)",
        (
            telegram_id, rebecca_username, plan_name, plan_gb, plan_days, subscription_url,
            status, traffic_used_gb, traffic_total_gb, expires_at,
        ),
    )
    await db.commit()
    async with db.execute(
        "SELECT id FROM subscriptions WHERE rebecca_username = ?", (rebecca_username,)
    ) as cur:
        row = await cur.fetchone()
    return int(row["id"])


async def get_subscription_by_username(rebecca_username: str) -> Optional[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM subscriptions WHERE rebecca_username = ?", (rebecca_username,)
    ) as cur:
        return _row(await cur.fetchone())


async def list_subscriptions_for_user(telegram_id: int) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM subscriptions WHERE telegram_id = ? ORDER BY created_at DESC",
        (telegram_id,),
    ) as cur:
        return _rows(await cur.fetchall())


async def list_active_subscriptions() -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM subscriptions WHERE status = 'active' ORDER BY id"
    ) as cur:
        return _rows(await cur.fetchall())


async def update_subscription(sub_id: int, **fields: Any) -> None:
    await _update("subscriptions", "id", sub_id, fields, SUB_COLUMNS)


async def delete_subscription(sub_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
    await db.commit()


# --------------------------------------------------------------------------
# subscription transfers
# --------------------------------------------------------------------------
async def create_transfer(sub_id: int, from_id: int, to_id: int) -> int:
    db = await get_db()
    try:
        cur = await db.execute(
            "INSERT INTO subscription_transfers (sub_id, from_id, to_id, status) "
            "VALUES (?, ?, ?, 'pending')",
            (sub_id, from_id, to_id),
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        return 0
    return int(cur.lastrowid)


async def get_transfer(transfer_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM subscription_transfers WHERE id = ?", (transfer_id,)
    ) as cur:
        return _row(await cur.fetchone())


async def get_pending_transfer_for_sub(sub_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM subscription_transfers WHERE sub_id = ? AND status = 'pending'",
        (sub_id,),
    ) as cur:
        return _row(await cur.fetchone())


async def set_transfer_status(transfer_id: int, status: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE subscription_transfers SET status = ?, resolved_at = datetime('now') "
        "WHERE id = ?",
        (status, transfer_id),
    )
    await db.commit()


# --------------------------------------------------------------------------
# referrals
# --------------------------------------------------------------------------
async def create_referral(
    order_id: int,
    inviter_id: int,
    invitee_id: int,
    invite_code: str,
    plan_gb: float,
    bonus_gb: float,
) -> Optional[int]:
    db = await get_db()
    try:
        cur = await db.execute(
            "INSERT INTO referrals "
            "(order_id, inviter_id, invitee_id, invite_code, plan_gb, bonus_gb, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            (order_id, inviter_id, invitee_id, invite_code, plan_gb, bonus_gb),
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        return None
    return int(cur.lastrowid)


async def get_referral_by_order(order_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM referrals WHERE order_id = ?", (order_id,)
    ) as cur:
        return _row(await cur.fetchone())


async def get_active_referral_for_invitee(invitee_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM referrals WHERE invitee_id = ? "
        "AND status IN ('pending', 'credited')",
        (invitee_id,),
    ) as cur:
        return _row(await cur.fetchone())


async def set_referral_status(
    referral_id: int,
    status: str,
    inviter_sub_id: Optional[int] = None,
) -> None:
    db = await get_db()
    if status == "credited":
        await db.execute(
            "UPDATE referrals SET status = ?, inviter_sub_id = ?, "
            "credited_at = datetime('now') WHERE id = ?",
            (status, inviter_sub_id, referral_id),
        )
    else:
        await db.execute(
            "UPDATE referrals SET status = ? WHERE id = ?", (status, referral_id)
        )
    await db.commit()


async def cancel_referral_for_order(order_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE referrals SET status = 'cancelled' "
        "WHERE order_id = ? AND status = 'pending'",
        (order_id,),
    )
    await db.commit()


async def list_pending_referrals_for_approved_orders(
    limit: int = 100,
) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT r.* FROM referrals r JOIN orders o ON o.id = r.order_id "
        "WHERE r.status = 'pending' AND o.status = 'approved' "
        "ORDER BY r.id ASC LIMIT ?",
        (limit,),
    ) as cur:
        return _rows(await cur.fetchall())


async def referral_stats(inviter_id: int) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT status, COUNT(*) AS n, COALESCE(SUM(bonus_gb), 0) AS total "
        "FROM referrals WHERE inviter_id = ? GROUP BY status",
        (inviter_id,),
    ) as cur:
        return _rows(await cur.fetchall())


# --------------------------------------------------------------------------
# orders
# --------------------------------------------------------------------------
ORDER_COLUMNS = frozenset(
    {
        "telegram_id",
        "plan_id",
        "plan_snapshot",
        "kind",
        "subscription_id",
        "list_price",
        "discount_code",
        "discount_toman",
        "volume_discount_toman",
        "final_price",
        "receipt_path",
        "receipt_history",
        "status",
        "reject_reason",
        "reviewer_id",
        "reviewed_at",
        "provisioned_sub_id",
    }
)


async def create_order(
    public_id: str,
    telegram_id: int,
    plan_id: Optional[int],
    plan_snapshot: Any,
    list_price: float,
    final_price: float,
    discount_code: Optional[str] = None,
    discount_toman: float = 0.0,
    volume_discount_toman: float = 0.0,
    receipt_path: Optional[str] = None,
    status: str = "pending",
    kind: str = "new",
    subscription_id: Optional[int] = None,
) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO orders "
        "(public_id, telegram_id, plan_id, plan_snapshot, kind, subscription_id, "
        " list_price, discount_code, discount_toman, volume_discount_toman, "
        " final_price, receipt_path, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            public_id, telegram_id, plan_id, json.dumps(plan_snapshot),
            kind, subscription_id, list_price, discount_code, discount_toman,
            volume_discount_toman, final_price, receipt_path, status,
        ),
    )
    await db.commit()
    return int(cur.lastrowid)


async def get_order(order_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as cur:
        return _row(await cur.fetchone())


async def get_order_by_public_id(public_id: str) -> Optional[Record]:
    db = await get_db()
    async with db.execute("SELECT * FROM orders WHERE public_id = ?", (public_id,)) as cur:
        return _row(await cur.fetchone())


async def get_pending_renewal_for_sub(sub_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM orders WHERE subscription_id = ? AND kind = 'renewal' "
        "AND status IN ('pending', 'needs_resend', 'under_review') LIMIT 1",
        (sub_id,),
    ) as cur:
        return _row(await cur.fetchone())


async def list_orders_for_user(telegram_id: int, limit: int = 50) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM orders WHERE telegram_id = ? ORDER BY created_at DESC LIMIT ?",
        (telegram_id, limit),
    ) as cur:
        return _rows(await cur.fetchall())


async def list_orders_by_status(statuses: Iterable[str], limit: int = 100) -> list[Record]:
    statuses = list(statuses)
    if not statuses:
        return []
    placeholders = ", ".join(["?"] * len(statuses))
    db = await get_db()
    async with db.execute(
        "SELECT * FROM orders WHERE status IN (" + placeholders + ") "
        "ORDER BY created_at ASC LIMIT ?",
        [*statuses, limit],
    ) as cur:
        return _rows(await cur.fetchall())


async def update_order(order_id: int, **fields: Any) -> None:
    if "plan_snapshot" in fields and not isinstance(fields["plan_snapshot"], str):
        fields["plan_snapshot"] = json.dumps(fields["plan_snapshot"])
    await _update("orders", "id", order_id, fields, ORDER_COLUMNS)


async def set_order_status(order_id: int, status: str, **extra: Any) -> None:
    await update_order(order_id, status=status, **extra)


# --------------------------------------------------------------------------
# order_notes
# --------------------------------------------------------------------------
async def add_order_note(order_id: int, admin_id: int, note: str) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO order_notes (order_id, admin_id, note) VALUES (?, ?, ?)",
        (order_id, admin_id, note),
    )
    await db.commit()
    return int(cur.lastrowid)


async def list_order_notes(order_id: int) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM order_notes WHERE order_id = ? ORDER BY created_at ASC",
        (order_id,),
    ) as cur:
        return _rows(await cur.fetchall())


# --------------------------------------------------------------------------
# tickets
# --------------------------------------------------------------------------
TICKET_COLUMNS = frozenset(
    {"category", "description", "screenshot_path", "status", "assigned_to", "updated_at"}
)


async def create_ticket(
    public_id: str,
    telegram_id: int,
    category: str,
    description: Optional[str] = None,
    screenshot_path: Optional[str] = None,
    status: str = "open",
) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO tickets (public_id, telegram_id, category, description, screenshot_path, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (public_id, telegram_id, category, description, screenshot_path, status),
    )
    await db.commit()
    return int(cur.lastrowid)


async def get_ticket(ticket_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)) as cur:
        return _row(await cur.fetchone())


async def get_ticket_by_public_id(public_id: str) -> Optional[Record]:
    db = await get_db()
    async with db.execute("SELECT * FROM tickets WHERE public_id = ?", (public_id,)) as cur:
        return _row(await cur.fetchone())


async def list_tickets_for_user(telegram_id: int, limit: int = 50) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM tickets WHERE telegram_id = ? ORDER BY created_at DESC LIMIT ?",
        (telegram_id, limit),
    ) as cur:
        return _rows(await cur.fetchall())


async def list_tickets_by_status(statuses: Iterable[str], limit: int = 100) -> list[Record]:
    statuses = list(statuses)
    if not statuses:
        return []
    placeholders = ", ".join(["?"] * len(statuses))
    db = await get_db()
    async with db.execute(
        "SELECT * FROM tickets WHERE status IN (" + placeholders + ") "
        "ORDER BY created_at ASC LIMIT ?",
        [*statuses, limit],
    ) as cur:
        return _rows(await cur.fetchall())


async def update_ticket(ticket_id: int, **fields: Any) -> None:
    fields.pop("updated_at", None)
    await _update("tickets", "id", ticket_id, fields, TICKET_COLUMNS)
    db = await get_db()
    await db.execute(
        "UPDATE tickets SET updated_at = datetime('now') WHERE id = ?", (ticket_id,)
    )
    await db.commit()


async def set_ticket_status(ticket_id: int, status: str, assigned_to: Optional[int] = None) -> None:
    db = await get_db()
    if assigned_to is None:
        await db.execute(
            "UPDATE tickets SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, ticket_id),
        )
    else:
        await db.execute(
            "UPDATE tickets SET status = ?, assigned_to = ?, updated_at = datetime('now') WHERE id = ?",
            (status, assigned_to, ticket_id),
        )
    await db.commit()


async def count_open_tickets_for_user(telegram_id: int) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS n FROM tickets WHERE telegram_id = ? AND status IN ('open', 'in_progress')",
        (telegram_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


# --------------------------------------------------------------------------
# ticket_messages
# --------------------------------------------------------------------------
async def add_ticket_message(
    ticket_id: int,
    sender_role: str,
    sender_id: Optional[int] = None,
    body: Optional[str] = None,
    file_path: Optional[str] = None,
) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO ticket_messages (ticket_id, sender_role, sender_id, body, file_path) "
        "VALUES (?, ?, ?, ?, ?)",
        (ticket_id, sender_role, sender_id, body, file_path),
    )
    await db.execute(
        "UPDATE tickets SET updated_at = datetime('now') WHERE id = ?", (ticket_id,)
    )
    await db.commit()
    return int(cur.lastrowid)


async def list_ticket_messages(ticket_id: int) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at ASC, id ASC",
        (ticket_id,),
    ) as cur:
        return _rows(await cur.fetchall())


# --------------------------------------------------------------------------
# discounts
# --------------------------------------------------------------------------
DISCOUNT_COLUMNS = frozenset(
    {"type", "value", "applies_to", "max_uses", "per_user_max", "expires_at", "active"}
)


async def create_discount(
    code: str,
    type: str,
    value: float,
    applies_to: str = "all",
    max_uses: Optional[int] = None,
    per_user_max: int = 1,
    expires_at: Optional[str] = None,
    active: bool = True,
) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO discounts (code, type, value, applies_to, max_uses, per_user_max, expires_at, active) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (code.upper(), type, value, applies_to, max_uses, per_user_max, expires_at, int(active)),
    )
    await db.commit()


async def get_discount(code: str) -> Optional[Record]:
    db = await get_db()
    async with db.execute("SELECT * FROM discounts WHERE code = ?", (code.upper(),)) as cur:
        return _row(await cur.fetchone())


async def list_discounts() -> list[Record]:
    db = await get_db()
    async with db.execute("SELECT * FROM discounts ORDER BY created_at DESC") as cur:
        return _rows(await cur.fetchall())


async def update_discount(code: str, **fields: Any) -> None:
    await _update("discounts", "code", code.upper(), fields, DISCOUNT_COLUMNS)


async def delete_discount(code: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM discounts WHERE code = ?", (code.upper(),))
    await db.commit()


async def add_redemption(code: str, telegram_id: int, order_id: Optional[int] = None) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO discount_redemptions (code, telegram_id, order_id) VALUES (?, ?, ?)",
        (code.upper(), telegram_id, order_id),
    )
    await db.commit()
    return int(cur.lastrowid)


async def count_redemptions(code: str) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS n FROM discount_redemptions WHERE code = ?", (code.upper(),)
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def count_user_redemptions(code: str, telegram_id: int) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS n FROM discount_redemptions WHERE code = ? AND telegram_id = ?",
        (code.upper(), telegram_id),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


# --------------------------------------------------------------------------
# notifications
# --------------------------------------------------------------------------
async def insert_notification(
    telegram_id: int,
    type: str,
    title: str,
    body: Optional[str] = None,
    dedupe_key: Optional[str] = None,
    sub_id: Optional[int] = None,
    order_id: Optional[int] = None,
    ticket_id: Optional[int] = None,
) -> Optional[int]:
    """Insert a notification; return new id, or None when deduped by UNIQUE."""
    db = await get_db()
    try:
        cur = await db.execute(
            "INSERT INTO notifications "
            "(telegram_id, type, dedupe_key, title, body, sub_id, order_id, ticket_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (telegram_id, type, dedupe_key, title, body, sub_id, order_id, ticket_id),
        )
        await db.commit()
        return int(cur.lastrowid)
    except aiosqlite.IntegrityError:
        return None


async def get_notification(notification_id: int) -> Optional[Record]:
    db = await get_db()
    async with db.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,)) as cur:
        return _row(await cur.fetchone())


async def get_notification_by_key(
    telegram_id: int, type: str, dedupe_key: str
) -> Optional[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM notifications WHERE telegram_id = ? AND type = ? AND dedupe_key = ?",
        (telegram_id, type, dedupe_key),
    ) as cur:
        return _row(await cur.fetchone())


async def list_notifications_for_user(telegram_id: int, limit: int = 30) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM notifications WHERE telegram_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        (telegram_id, limit),
    ) as cur:
        return _rows(await cur.fetchall())


async def list_pending_notifications(telegram_ids: Iterable[int], limit: int = 200) -> list[Record]:
    ids = list(telegram_ids)
    if not ids:
        return []
    placeholders = ", ".join(["?"] * len(ids))
    db = await get_db()
    async with db.execute(
        "SELECT * FROM notifications WHERE delivered = 0 AND type != 'broadcast' "
        "AND telegram_id IN (" + placeholders + ") ORDER BY created_at ASC LIMIT ?",
        [*ids, limit],
    ) as cur:
        return _rows(await cur.fetchall())


async def mark_notification_delivered(notification_id: int) -> None:
    db = await get_db()
    await db.execute("UPDATE notifications SET delivered = 1 WHERE id = ?", (notification_id,))
    await db.commit()


async def mark_notification_read(notification_id: int) -> None:
    db = await get_db()
    await db.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
    await db.commit()


async def mark_all_read(telegram_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE notifications SET is_read = 1 WHERE telegram_id = ?", (telegram_id,)
    )
    await db.commit()


async def count_unread(telegram_id: int) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS n FROM notifications WHERE telegram_id = ? AND is_read = 0",
        (telegram_id,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


# --------------------------------------------------------------------------
# admin_audit
# --------------------------------------------------------------------------
async def add_audit(
    admin_id: int,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    payload_before: Any = None,
    payload_after: Any = None,
) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO admin_audit "
        "(admin_id, action, target_type, target_id, payload_before, payload_after) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            admin_id, action, target_type, target_id,
            json.dumps(payload_before) if payload_before is not None else None,
            json.dumps(payload_after) if payload_after is not None else None,
        ),
    )
    await db.commit()
    return int(cur.lastrowid)


async def list_audit(limit: int = 100, offset: int = 0) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM admin_audit ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ) as cur:
        return _rows(await cur.fetchall())


# --------------------------------------------------------------------------
# ai_conversations
# --------------------------------------------------------------------------
async def add_ai_message(telegram_id: int, role: str, content: str) -> int:
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO ai_conversations (telegram_id, role, content) VALUES (?, ?, ?)",
        (telegram_id, role, content),
    )
    await db.commit()
    return int(cur.lastrowid)


async def list_ai_history(telegram_id: int, limit: int = 10) -> list[Record]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM (SELECT * FROM ai_conversations WHERE telegram_id = ? "
        "ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
        (telegram_id, limit),
    ) as cur:
        return _rows(await cur.fetchall())


async def clear_ai_history(telegram_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM ai_conversations WHERE telegram_id = ?", (telegram_id,))
    await db.commit()


# --------------------------------------------------------------------------
# manager_prefs
# --------------------------------------------------------------------------
async def get_manager_lang(telegram_id: int) -> Optional[str]:
    db = await get_db()
    async with db.execute(
        "SELECT lang FROM manager_prefs WHERE telegram_id = ?", (telegram_id,)
    ) as cur:
        row = await cur.fetchone()
    return str(row["lang"]) if row else None


async def set_manager_lang(telegram_id: int, lang: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO manager_prefs (telegram_id, lang) VALUES (?, ?) "
        "ON CONFLICT(telegram_id) DO UPDATE SET lang = excluded.lang",
        (telegram_id, lang),
    )
    await db.commit()


async def count_ai_messages_since(telegram_id: int, seconds: int = 3600) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS n FROM ai_conversations "
        "WHERE telegram_id = ? AND role = 'user' "
        "AND created_at >= datetime('now', ?)",
        (telegram_id, f"-{int(seconds)} seconds"),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0


async def count_ai_user_messages_since(modifier: str = "start of day") -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) AS n FROM ai_conversations "
        "WHERE role = 'user' AND created_at >= datetime('now', ?)",
        (modifier,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["n"]) if row else 0
