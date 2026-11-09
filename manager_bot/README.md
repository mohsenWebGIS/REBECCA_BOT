# manager_bot

Private, admin-only Telegram bot for reviewing orders, tickets, users,
discounts, broadcasts and statistics. It shares `core/` and the same SQLite DB
with user_bot; run both against the same `DB_PATH` and `./data` volume.

## Access gate
Every handler is wrapped with `@manager_only`, which only allows ids listed in
`MANAGER_IDS` (root `.env`). Open the hub with `/admin`.

`/admin` and `/start` install a persistent `🏠 Home / خانه` reply keyboard;
sending it from any manager flow clears the pending state and reopens the admin
menu. Slash commands are published on startup, so typing `/` lists `/admin`,
`/start`, `/language`, `/cancel`.

## Language and pricing
- First `/admin` asks each manager to pick English or Persian; `/language` and
  the 🌐 button change it later. Choice is stored in `manager_prefs`.
- All prices are Toman. Orders show the list price, volume discount, promo
  discount and final total. Numeric input accepts Persian/Arabic digits.
- User-facing notifications (approve/reject/resend/reply/DM) are rendered in the
  recipient's language; SLA alerts use the manager group's language (Persian by
  default when unset) and digests render per admin.

## Features
- Orders: pending queue + detail (receipt from disk, user context, notes),
  approve (with price edit + real Rebecca provisioning), reject, ask resend,
  custom message, internal note, under review, previous receipts.
- Tickets: queue, thread display (screenshot from disk), in-progress/resolve/
  close, reply/custom message.
- Users: paginated list + search, filter for bot users without a subscription,
  order/ticket history, ban, DM, and sub actions (extend, add traffic, reset
  usage, disable/enable, delete) via the Rebecca API.
- Unlinked panel users: scans Rebecca users with an empty `telegram_id`
  (60s cache), lets an admin attach a Telegram ID, upserts the local
  subscription, and queues a "start the bot" notification (delivered by the
  user bot, including after the recipient first starts it).
- Payment Card: edit the card number/holder stored in `schema_meta`, choose
  visibility (`all`, `request`, `none`), review/approve/reject card requests,
  and grant/revoke card access per user from user detail. Approvals notify the
  user; card requests notify all managers/group.
- Discounts: create flow (type, value, plan scope, limits, expiry), toggle,
  delete (disabled instead when redemptions exist).
- Broadcast: segments (all/active/expiring/high-traffic/custom), preview,
  force-critical, mute respected, ~20 msg/s delivery with `RetryAfter` handling.
- Statistics: live revenue/orders/users/subs/promos/API success rate + CSV export.
- Alerts: recent audit feed, per-admin category toggles, full audit log.
- Jobs: pending notification delivery to managers every 10 seconds (payment
  receipt alerts include a `Review order` button), SLA breach checks, daily and
  weekly digests.

## Run locally
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m manager_bot.main
```

Required `.env`: `MANAGER_BOT_TOKEN`, `MANAGER_IDS`, plus the shared
`REBECCA_*`, `DB_PATH`, `RECEIPTS_DIR`, `TZ`, `LOG_LEVEL`.
Optional: `MANAGER_GROUP_ID` (SLA alerts and digests), `REBECCA_SERVICE_ID`.

## Docker
`docker compose up --build manager-bot` (shares `./data` and `./logs`).

## systemd unit
```ini
[Unit]
Description=Moot manager bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/moot
EnvironmentFile=/opt/moot/.env
ExecStart=/opt/moot/.venv/bin/python -m manager_bot.main
Restart=always
RestartSec=5
User=bot

[Install]
WantedBy=multi-user.target
```
