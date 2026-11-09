"""Shared SQLite access for both bots.

A single aiosqlite connection per process (SQLite serialises writes anyway)
with WAL mode so the user bot and manager bot processes can safely share one
database file. ``init_db()`` is idempotent and safe to call on every startup.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import aiosqlite

from core.config import settings

_db: Optional[aiosqlite.Connection] = None
_lock = asyncio.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id     INTEGER PRIMARY KEY,
    username        TEXT,
    display_name    TEXT,
    invite_code     TEXT,
    joined_at       TEXT NOT NULL DEFAULT (datetime('now')),
    banned          INTEGER NOT NULL DEFAULT 0,
    mute_broadcasts INTEGER NOT NULL DEFAULT 0,
    preferred_lang  TEXT NOT NULL DEFAULT 'en',
    lang_selected   INTEGER NOT NULL DEFAULT 0,
    last_seen_at    TEXT
);

CREATE TABLE IF NOT EXISTS plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    gb          REAL NOT NULL,
    days        INTEGER NOT NULL,
    price_toman REAL NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id         INTEGER NOT NULL,
    rebecca_username    TEXT NOT NULL UNIQUE,
    display_name        TEXT,
    plan_name           TEXT,
    plan_gb             REAL,
    plan_days           INTEGER,
    subscription_url    TEXT,
    status              TEXT NOT NULL DEFAULT 'active',
    traffic_used_gb     REAL NOT NULL DEFAULT 0,
    traffic_total_gb    REAL NOT NULL DEFAULT 0,
    expires_at          TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    source_order_id     INTEGER
);

CREATE TABLE IF NOT EXISTS orders (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id          TEXT NOT NULL UNIQUE,
    telegram_id        INTEGER NOT NULL,
    plan_id            INTEGER,
    plan_snapshot      TEXT,
    kind               TEXT NOT NULL DEFAULT 'new',
    subscription_id    INTEGER,
    list_price              REAL,
    discount_code           TEXT,
    discount_toman          REAL NOT NULL DEFAULT 0,
    volume_discount_toman   REAL NOT NULL DEFAULT 0,
    final_price             REAL,
    receipt_path       TEXT,
    receipt_history    TEXT NOT NULL DEFAULT '[]',
    status             TEXT NOT NULL DEFAULT 'pending',
    reject_reason      TEXT,
    reviewer_id        INTEGER,
    reviewed_at        TEXT,
    provisioned_sub_id INTEGER,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    admin_id   INTEGER NOT NULL,
    note       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id       TEXT NOT NULL UNIQUE,
    telegram_id     INTEGER NOT NULL,
    category        TEXT NOT NULL,
    description     TEXT,
    screenshot_path TEXT,
    status          TEXT NOT NULL DEFAULT 'open',
    assigned_to     INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   INTEGER NOT NULL,
    sender_role TEXT NOT NULL,
    sender_id   INTEGER,
    body        TEXT,
    file_path   TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS discounts (
    code         TEXT PRIMARY KEY,
    type         TEXT NOT NULL,
    value        REAL NOT NULL,
    applies_to   TEXT NOT NULL DEFAULT 'all',
    max_uses     INTEGER,
    per_user_max INTEGER NOT NULL DEFAULT 1,
    expires_at   TEXT,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS discount_redemptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    telegram_id INTEGER NOT NULL,
    order_id    INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    type        TEXT NOT NULL,
    dedupe_key  TEXT,
    title       TEXT NOT NULL,
    body        TEXT,
    sub_id      INTEGER,
    order_id    INTEGER,
    ticket_id   INTEGER,
    is_read     INTEGER NOT NULL DEFAULT 0,
    delivered   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(telegram_id, type, dedupe_key)
);

CREATE TABLE IF NOT EXISTS admin_audit (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id       INTEGER NOT NULL,
    action         TEXT NOT NULL,
    target_type    TEXT,
    target_id      TEXT,
    payload_before TEXT,
    payload_after  TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ai_conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS manager_prefs (
    telegram_id INTEGER PRIMARY KEY,
    lang        TEXT NOT NULL DEFAULT 'en'
);

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS card_access (
    telegram_id  INTEGER PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'pending',
    requested_at TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_by  INTEGER,
    reviewed_at  TEXT
);

CREATE TABLE IF NOT EXISTS subscription_transfers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sub_id      INTEGER NOT NULL,
    from_id     INTEGER NOT NULL,
    to_id       INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS referrals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id       INTEGER NOT NULL UNIQUE,
    inviter_id     INTEGER NOT NULL,
    invitee_id     INTEGER NOT NULL,
    invite_code    TEXT NOT NULL,
    plan_gb        REAL NOT NULL,
    bonus_gb       REAL NOT NULL,
    inviter_sub_id INTEGER,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    credited_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_status        ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_telegram      ON orders(telegram_id);
CREATE INDEX IF NOT EXISTS idx_subs_telegram        ON subscriptions(telegram_id);
CREATE INDEX IF NOT EXISTS idx_subs_status          ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_tickets_status       ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_telegram     ON tickets(telegram_id);
CREATE INDEX IF NOT EXISTS idx_notif_pending        ON notifications(delivered, telegram_id);
CREATE INDEX IF NOT EXISTS idx_notif_telegram       ON notifications(telegram_id, is_read);
CREATE INDEX IF NOT EXISTS idx_ai_telegram          ON ai_conversations(telegram_id, id);
CREATE INDEX IF NOT EXISTS idx_redemptions_code     ON discount_redemptions(code);
CREATE INDEX IF NOT EXISTS idx_redemptions_user     ON discount_redemptions(telegram_id);
CREATE INDEX IF NOT EXISTS idx_card_access_status   ON card_access(status);
CREATE INDEX IF NOT EXISTS idx_transfers_sub         ON subscription_transfers(sub_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_transfer_pending_sub
    ON subscription_transfers(sub_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_referrals_inviter      ON referrals(inviter_id);
CREATE INDEX IF NOT EXISTS idx_referrals_status       ON referrals(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_active_invitee
    ON referrals(invitee_id) WHERE status IN ('pending', 'credited');
"""

SEED_PLANS = [
    ("Starter", 30.0, 30, 120000, 0),
    ("Standard", 80.0, 30, 320000, 1),
    ("Pro", 200.0, 30, 800000, 2),
]


async def _columns(db: aiosqlite.Connection, table: str) -> set[str]:
    allowed = {"users", "plans", "orders", "subscriptions"}
    if table not in allowed:
        raise ValueError("unexpected table")
    async with db.execute("PRAGMA table_info(" + table + ")") as cur:
        return {row["name"] for row in await cur.fetchall()}


async def _add_column(db: aiosqlite.Connection, table: str, column: str, ddl: str) -> bool:
    if column in await _columns(db, table):
        return False
    try:
        await db.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + ddl)
        await db.commit()
    except aiosqlite.OperationalError:
        # Another process added it concurrently; only a real failure matters.
        if column not in await _columns(db, table):
            raise
        return False
    return True


async def _rename_column(
    db: aiosqlite.Connection, table: str, old: str, new: str
) -> bool:
    cols = await _columns(db, table)
    if old not in cols:
        return False
    if new in cols:
        return False
    try:
        await db.execute("ALTER TABLE " + table + " RENAME COLUMN " + old + " TO " + new)
        await db.commit()
    except aiosqlite.OperationalError:
        cols = await _columns(db, table)
        if new not in cols:
            raise
        return False
    return True


async def _migrate(db: aiosqlite.Connection) -> None:
    """Bring an existing database up to the Toman/bilingual schema."""
    from core.pricing import base_price

    await _add_column(db, "users", "lang_selected", "INTEGER NOT NULL DEFAULT 0")
    await _add_column(db, "users", "invite_code", "TEXT")
    await _add_column(db, "orders", "volume_discount_toman", "REAL NOT NULL DEFAULT 0")
    await _add_column(db, "orders", "kind", "TEXT NOT NULL DEFAULT 'new'")
    await _add_column(db, "orders", "subscription_id", "INTEGER")
    await _add_column(db, "subscriptions", "display_name", "TEXT")
    await db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_invite_code ON users(invite_code)"
    )
    await db.commit()

    renamed_plans = await _rename_column(db, "plans", "price_usd", "price_toman")
    renamed_orders = await _rename_column(db, "orders", "discount_usd", "discount_toman")

    async with db.execute(
        "SELECT value FROM schema_meta WHERE key = 'pricing_toman_v1'"
    ) as cur:
        done = await cur.fetchone()
    if done is None:
        if renamed_plans or renamed_orders:
            async with db.execute("SELECT id, gb FROM plans") as cur:
                for row in await cur.fetchall():
                    await db.execute(
                        "UPDATE plans SET price_toman = ? WHERE id = ?",
                        (base_price(row["gb"]), row["id"]),
                    )
        await db.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('pricing_toman_v1', '1')"
        )
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    """Return the shared connection, opening it on first use."""
    global _db
    if _db is not None:
        return _db
    async with _lock:
        if _db is None:
            db_file = Path(settings.db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(str(db_file))
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute("PRAGMA busy_timeout=5000")
            await conn.commit()
            _db = conn
    return _db


async def init_db() -> None:
    """Create the schema if needed and seed placeholder plans on first run."""
    db = await get_db()
    await db.executescript(SCHEMA)
    await db.commit()
    await _migrate(db)
    async with db.execute("SELECT COUNT(*) AS n FROM plans") as cur:
        row = await cur.fetchone()
    if row is not None and row["n"] == 0:
        await db.executemany(
            "INSERT INTO plans (name, gb, days, price_toman, active, sort_order) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            SEED_PLANS,
        )
        await db.commit()


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def reset_db_for_tests(path: str) -> aiosqlite.Connection:
    """Re-open the shared connection against ``path`` (test helper)."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
    settings.db_path = path
    return await get_db()


__all__ = ["SCHEMA", "get_db", "init_db", "close_db", "reset_db_for_tests"]
