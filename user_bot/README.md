# user_bot

Customer-facing Telegram bot for the Moot VPN subscription service.

## What it does
- `/start` registers the user and opens the main menu. First-time users pick a language (English/Persian); `/language` changes it later. Numbers and prices use localized digits.
- `/start` also installs a persistent `🏠 Home / خانه` reply keyboard; sending it from anywhere clears the current flow and returns to the main menu.
- Slash commands are published to Telegram on startup, so typing `/` lists `/start`, `/help`, `/language`, `/cancel`.
- Prices are in Toman at 4,000/GB, with a 10% volume discount on plans above 50 GB; promo codes apply after the volume discount.
- My Subscriptions: live refresh, detail, QR (`qrcode[pil]`), URL, refresh, and a user-defined display name via `✏️ Rename` (stored locally in `subscriptions.display_name`). Opening the list reconciles with the panel; local rows whose panel user was deleted are removed.
- Renew: subscription detail → `🔄 Renew` opens payment using that subscription's GB/days; after manager approval the expiry is extended and the plan traffic is added (no promo/invite on renewals).
- Transfer: an owner can send a subscription to another Telegram user (who must have started the bot); the recipient accepts/declines inline. Acceptance updates the panel `telegram_id`, local ownership, clears the custom name, and notifies both sides.
- Invite Friends: each user gets a unique code and `t.me/<bot>?start=ref_CODE` link. New users can enter the code during Buy; after approval the inviter gets 5% of the purchased GB added to their most recent active subscription (pending credits retry in the background).
- Buy: plans → optional promo → payment info (bank card number/holder with a copy button) → payment screenshot upload. Card visibility is manager-controlled: returning users (approved order/subscription) see it automatically; new users can request approval from the manager bot.
- Report Issue: category → description/screenshot → ticket thread/reply/close.
- AI Assistant: context-aware chat, 20 messages/hour, rolling 10-message history.
- Notifications inbox with mark-all-read and broadcast mute.
- Background jobs: subscription expiry/traffic alerts and pending-notification delivery.

Payment screenshots are downloaded to `RECEIPTS_DIR` and stored in the DB as
**paths** (never Telegram `file_id`) so manager_bot can re-upload them under its
own token.

## Run locally
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # or edit the existing root .env
python -m user_bot.main
```

Required root `.env` keys: `USER_BOT_TOKEN`, `REBECCA_BASE_URL`,
`REBECCA_API_KEY`, `DB_PATH`, `RECEIPTS_DIR`, `TZ`, `LOG_LEVEL`.
Optional: `LLM_PROVIDER` (`openai`/`deepseek`), `LLM_BASE_URL`,
`LLM_API_KEY`, `LLM_MODEL`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT_SECONDS`,
`LLM_DAILY_MESSAGE_LIMIT`, `REBECCA_SERVICE_ID`. The AI is read-only (no tools),
uses a hardened system prompt, caps input/output length, and never receives API
keys or other users' data. User actions and panel sync are also rate-limited.

## Docker
`docker compose up --build user-bot` (shares `./data` and `./logs` with manager-bot).

## systemd unit
```ini
[Unit]
Description=Moot user bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/moot
EnvironmentFile=/opt/moot/.env
ExecStart=/opt/moot/.venv/bin/python -m user_bot.main
Restart=always
RestartSec=5
User=bot

[Install]
WantedBy=multi-user.target
```
