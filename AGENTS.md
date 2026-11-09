# AGENTS.md

## Repository state
- **Spec-first repo.** All three specs are implemented: `core/` (`prompt1.md`), `user_bot/` (`prompt2.md`), and `manager_bot/` (`prompt3.md`). `core/` must stay the shared foundation; bots import from it and never duplicate DB/API code.
- `Readme.md` is intentionally empty; the real requirements live in `prompt*.md`.
- `Dockerfile`/`docker-compose.yml` expect `requirements.txt`, `core/`, `user_bot/`, `manager_bot/` — all now present.
- No test, lint, formatter, typecheck, or CI config exists. Add tooling only if you introduce it.
- A local `.venv/` is created with the pinned requirements; use `.venv/bin/python` to run scripts/tests without Docker.

## Architecture (from the specs)
- Python 3.12. Stack: `python-telegram-bot` v21+ (async), `aiosqlite`, `httpx`, `pydantic` v2 + `pydantic-settings`, `APScheduler`.
- Two separate Telegram bots share **one** SQLite DB (`DB_PATH`, default `./data/bot.sqlite3`) and `./data` / `./logs` volumes. Same image, different command (`python -m user_bot.main` vs `python -m manager_bot.main`).
- Polling only — no ports / webhooks unless deliberately switched.
- Config is read from root `.env` via `core.config.Settings`; each bot reads only its own token (`USER_BOT_TOKEN` / `MANAGER_BOT_TOKEN` + `MANAGER_IDS`).
- External Rebecca panel API is a Marzban 1.8 deployment; `openapi.json` is disabled, so the verified endpoint map lives in `TODO.md`/`scripts/probe_results.json`. Re-probe with `scripts/discover_api.py` then `scripts/probe_api.py` before assuming anything changed. Auth is `Authorization: Bearer <key>`; user creation also needs `REBECCA_SERVICE_ID` (default 1).
- The panel host resolves IPv6-first and httpx stalls on it; `core/net.py::prefer_ipv4()` is applied by `RebeccaClient` and both scripts.
- Notifications are delivered by whichever bot can reach the recipient, via shared DB rows. Respect `UNIQUE(telegram_id, type, dedupe_key)` — that constraint is what dedupes.
- New and re-uploaded payment receipts queue `new_order`/`order_new_receipt` alerts for every manager ID plus the manager group. The manager delivery job runs every 10 seconds and attaches a localized `Review order` button (`order:view:<id>`).
- Receipts/screenshots are stored **on disk as file paths, never Telegram `file_id`** — the two bots use different tokens and cannot reuse each other's file_ids.
- Both bots call `core.db.init_db()` on startup; schema creation is idempotent and seeds placeholder plans only on first run. `_migrate()` upgrades older USD databases (renames `price_usd`/`discount_usd`, adds `volume_discount_toman`/`lang_selected`, converts plan prices via `core/pricing.py`) and records completion in `schema_meta['pricing_toman_v1']`.
- Pricing is Toman-based: `PRICE_PER_GB_TOMAN` (default 4000), with `BULK_DISCOUNT_PERCENT` (10%) applied only when `gb > BULK_THRESHOLD_GB` (50). `plans.price_toman` is the **base** price; orders store `list_price` (base), `volume_discount_toman`, `discount_toman` (promo, applied after volume) and `final_price`.
- Both bots are bilingual (English/Persian) via `core/i18n.py`: English strings are catalog keys, `t()` falls back to English, and a ContextVar is set per update by middleware registered in handler group `-1`. User language lives in `users.preferred_lang` + `users.lang_selected`; manager language lives in `manager_prefs`. First `/start` (user) and `/admin` (manager) show a language picker; `/language` and the 🌐 button change it later.
- Both bots publish their slash-command menus from `_post_init` via `core/bot_commands.py` (`set_my_commands`, English default plus a `fa` scope). `/` therefore lists `/start`, `/help`, `/language`, `/cancel` for users and `/admin`, `/start`, `/language`, `/cancel` for managers.
- Subscriptions appear from either an approved order or `core/services/sync.py`, which imports panel users whose `telegram_id` is set (run by user_bot on `/start` and My Subscriptions). Provisioning sets the panel user's `telegram_id` alongside the `order {public_id}` note. Changing a panel `telegram_id` alone does not touch the local DB until a sync runs.
- `subscriptions.display_name` is the optional user-chosen label; user-bot lists/details prefer it over `plan_name`, then `rebecca_username`. Renaming only updates the local DB, not the panel.
- A subscription owner can transfer it to another user who has already started the user bot. The recipient must accept via inline buttons; on accept the panel user's `telegram_id` and the local `subscriptions.telegram_id` are both updated, the custom `display_name` is cleared, and both parties are notified. Pending transfers live in `subscription_transfers` (one pending per subscription).
- Users can renew a subscription from its detail screen. This creates an `orders.kind='renewal'` order using the subscription's own GB/days and the normal price/volume rules (no promo/invite). On approval, `renew_sub_for_order` extends panel expiry from `max(now, current_expiry)` by the plan days, adds the plan GB to `data_limit`, re-activates the subscription, and updates the local row. Pending renewal orders per subscription are blocked.
- Referral codes live in `users.invite_code` and `referrals`. Codes are usable only on the invitee's first approved purchase and cannot be self-referred; one active referral per invitee. After manager approval, `core/services/referrals.py` adds `REFERRAL_BONUS_PERCENT` (default 5%) of the purchased GB to the inviter's most recent active, non-expired subscription; no-subscription credits stay pending and are retried by a manager job. Users see/share code + `t.me/<bot>?start=ref_CODE` from 🎁 Invite Friends.
- The user-bot list always refreshes each local subscription against the panel. If `GET /api/user/{username}` returns 404, that local row is deleted, so panel-side deletions disappear from the bot after opening My Subscriptions/refresh.
- Manager Users offers two filters: bot users with no subscription (`users` minus `subscriptions`), and Rebecca panel users with an empty `telegram_id` (scanned via `core/services/panel_users.py`, 60s cache). Linking an ID calls `PUT /api/user/{username}`, upserts locally via `sync.link_panel_user`, and queues a notification; the user bot delivers it, including later if the recipient has not started the bot yet.

## Commands
- Build & run both: `docker compose up --build` (services `user-bot`, `manager-bot`).
- Run one bot locally: `pip install -r requirements.txt` then `python -m user_bot.main` / `python -m manager_bot.main`.
- Syntax check: `.venv/bin/python -m compileall -q core user_bot manager_bot`.
- API discovery: `python scripts/discover_api.py` then `python scripts/probe_api.py`.

## Gotchas
- `.env` is **git-tracked and contains live-looking secrets**; `.gitignore` is empty. Do not commit more secrets, and treat those credentials as needing rotation if real.
- SQL is always parameterized (no f-strings) per the specs.
- The user bot must accept free text only for: payment screenshot upload, ticket description/reply, AI chat, promo code entry, invitation code entry, subscription renaming, and transfer recipient IDs; everything else is inline buttons, with `/cancel` aborting stateful flows. The only text navigation exception is the persistent reply-keyboard button `🏠 Home / خانه`, which clears state and returns to the main menu. The manager bot installs the same persistent button on `/admin`/`/start`; sending it clears manager state and reopens the admin menu.
- Every manager-bot handler must be wrapped with `@manager_only` (gate on `MANAGER_IDS`); new handlers without it bypass authorization.
- Both bots suppress `httpx` INFO logs because Telegram request URLs embed the bot token.
- Notifications are localized **at creation time** using the recipient's language (or the manager's `manager_prefs`, with the manager group defaulting to Persian); queued rows created before a language switch keep their old text.
- The AI assistant supports `LLM_PROVIDER=openai|deepseek` plus optional `LLM_BASE_URL`/`LLM_MODEL` overrides. It has no tools, only sees the requesting user's own context, caps input/output length, and uses a hardened prompt that treats user text and context as untrusted data.
- User actions are protected by an in-memory sliding-window limiter (`user_bot/ratelimit.py`): receipt uploads 10/hour + 15s, tickets 5/hour + 60s, promo/invite attempts 15/10min + 2s, card requests 5/day + 30s, transfers 5/day + 30s. Panel sync reuses a 30-second snapshot and enforces a 60-second per-user cooldown. AI has the 20/hour per-user cap plus a global daily message cap (`LLM_DAILY_MESSAGE_LIMIT`).
- Dates remain Gregorian; numbers/currency are localized (`format_number`, `format_toman`, `parse_number` accepts Persian/Arabic digits). Do not re-add `$`/USD formatting.
- Payment is receipt-screenshot based: the payment page shows a card number/holder with a native Telegram copy button, then users upload a transaction screenshot for manager approval. Card values come from `schema_meta` (manager bot edits them) falling back to `PAYMENT_CARD_NUMBER`/`PAYMENT_CARD_HOLDER` defaults. Modes are `all`, `request` (returning users see it; new users must ask a manager), and `none` (only explicitly granted users see it). Access requests/grants live in `card_access`; manager grants notify the user. Broadcast is text-only and discount editing is not pre-filled yet (see `TODO.md`).
