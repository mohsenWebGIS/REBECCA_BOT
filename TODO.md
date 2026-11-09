# TODO

## Rebecca panel API discovery (Step 1)

- `GET {REBECCA_BASE_URL}/openapi.json` returns **404 `{"detail": "API docs are
  disabled"}`**. The raw response is saved in `scripts/openapi.json`; no schema
  was available to enumerate.
- **Workaround:** probed the deployment directly (it is a Marzban-style panel,
  version 1.8.0 `dev`). All required routes were confirmed live with the real
  API key. Results are in `scripts/probe_results.json` — 7/7 returned 2xx.
- Authentication is `Authorization: Bearer <REBECCA_API_KEY>` (not `X-API-Key`).

### Verified endpoint mapping

| Purpose | Method | Path | Probe |
|---|---|---|---|
| ping | GET | `/api/system` | 200 |
| list users | GET | `/api/users?offset=&limit=` | 200 |
| create user | POST | `/api/user` | 201 |
| fetch user by username | GET | `/api/user/{username}` | 200 |
| get user usage | GET | `/api/user/{username}/usage` | 200 |
| update user | PUT | `/api/user/{username}` | 200 |
| delete user | DELETE | `/api/user/{username}` | 200 |

### Service requirement

- This panel requires every user to be assigned to a service:
  `POST /api/user` returns `400 "service_id is required. Users must be assigned
  to a service."` when it is omitted. The existing sample user is on
  `service_id=1` (`PRO`).
- No service-list endpoint is exposed to this API key (`/api/services`,
  `/api/service`, `/api/admin/services`, … all 404).
- **Workaround:** added optional `REBECCA_SERVICE_ID` (default `1`). The
  provisioner sends it on create. Set it in `.env` if the target service differs.

### IPv6 stall

- The panel host resolves to IPv6 first; httpx stalls on the AAAA record in this
  environment (curl works because it falls back). `core/net.py::prefer_ipv4()`
  is called by `RebeccaClient` and both scripts to drop IPv6 answers.

## Pricing and i18n (implemented)

- Prices are now Toman at 4,000/GB with 10% off above 50 GB. Promo discounts
  apply to the post-volume price. `plans.price_toman` stores the base price and
  orders store `list_price`, `volume_discount_toman`, `discount_toman`,
  `final_price`.
- Startup migration renames `plans.price_usd` → `price_toman` and
  `orders.discount_usd` → `discount_toman`, adds `orders.volume_discount_toman`
  and `users.lang_selected`, and converts existing plan rows via
  `core/pricing.py::base_price` once (`schema_meta['pricing_toman_v1']`).
- Both bots are bilingual (English/Persian) with a per-update language
  ContextVar, language pickers on first use, and `/language`. English strings
  are the catalog keys in `core/i18n.py`; missing keys fall back to English.
- Notifications are localized when created. Existing rows created before a
  language switch keep their original language.
- The original `prompt*.md` files still describe the USD pricing and English-only
  flows; `AGENTS.md`, this file and the bot READMEs reflect the current behavior.

## Subscriptions (implemented)

- Panel users are created with `note="order {public_id}"`; this Marzban build
  ignores `telegram_id` on `POST /api/user`, so the provisioner immediately
  follows up with `PUT /api/user/{username}` to store the Telegram id. If that
  update fails it is logged and the order still provisions.
- Users can rename their subscription from the detail screen (`✏️ Rename`).
  The label is stored in `subscriptions.display_name` and shown ahead of
  `plan_name`/`rebecca_username` in the user-bot list and detail.
- The local subscriptions table is a cache. Opening My Subscriptions/refresh
  checks each panel user and deletes the local row when the panel returns 404,
  so manual panel deletions no longer linger in the user list.

## Rate limiting and abuse protection (implemented)

- In-memory sliding-window limits for receipts, tickets, promo/invite attempts,
  card requests, and transfers (`user_bot/ratelimit.py`).
- Panel sync uses a 30-second shared snapshot plus a 60-second per-user
  cooldown, preventing `/start`/My Subscriptions spam from hammering Rebecca.
- AI has the per-user hourly limit plus a global daily message cap.
- `.env` is local-only, ignored by git, and restricted to mode `600`.

## Subscription renewal (implemented)

- Subscription detail has `🔄 Renew`, creating a `kind='renewal'` order for the
  same GB/days. Renewals hide promo/invite controls and block duplicate pending
  renewal orders. On approval the panel expiry is extended from
  `max(now, current_expiry)`, the plan GB is added to `data_limit`, and the
  subscription is reactivated locally/on the panel.

## Referral codes (implemented)

- `users.invite_code` + `referrals`; codes are first-purchase-only, no
  self-referral and one active referral per invitee. Invite purchase codes and
  `?start=ref_CODE` links are supported.
- After order approval, 5% of the purchased GB is added to the inviter's most
  recent active, non-expired subscription (panel `data_limit` + local total).
  Credits with no active subscription stay pending and retry every 10 minutes.

## AI assistant security (implemented)

- Supports OpenAI-compatible providers (`openai`, `deepseek`, or a custom
  `LLM_BASE_URL`), configurable model/max tokens/timeout.
- No tools/actions; the prompt is hardened against role/rule overrides and
  prompt leakage, USER CONTEXT is delimited as untrusted data, DB values are
  sanitized/truncated, and user/reply lengths are capped.

## Receipt alerts (implemented)

- Every new or re-uploaded payment screenshot queues a localized alert for all
  `MANAGER_IDS` and `MANAGER_GROUP_ID`. The manager bot delivers pending
  notifications every 10 seconds and attaches a `Review order` button that
  opens the existing order detail for approve/reject.

## Subscription transfer (implemented)

- Users can transfer a subscription to another Telegram user who has started
  the bot. The recipient must accept via inline buttons; no manager approval is
  required. Acceptance updates the Rebecca `telegram_id`, local ownership, and
  clears `subscriptions.display_name`; both sides are notified. One pending
  transfer per subscription is enforced.

## Payment card (implemented)

- Card values are manager-editable (stored in `schema_meta`, falling back to
  `PAYMENT_CARD_NUMBER`/`PAYMENT_CARD_HOLDER`) and shown above the payment
  breakdown with a Telegram `CopyTextButton` for the raw digits.
- Visibility modes: `all`, `request` (returning users see it; others request
  approval), and `none` (only explicit grants). Requests are stored in
  `card_access`, notify managers, and approvals notify the user. Managers can
  also grant/revoke access from the user detail screen.

## Admin user audiences (implemented)

- Manager → Users now exposes `📭 Without subscription` (bot users with no
  local subscription) and `🔗 Panel without Telegram ID` (Rebecca users whose
  `telegram_id` is empty). The panel view is scanned on demand and cached for
  60 seconds; `↻ Refresh` forces a rescan.
- Linking a Telegram ID writes it to the panel user, upserts the local
  subscription, records an audit entry, and queues a `panel_link` notification.
  Delivery is attempted by the user bot; if the recipient has never started the
  bot yet, delivery waits until they do.

## Manager bot follow-ups

- **Broadcast** supports text only; image attachments and scheduled send are not
  implemented yet (send-now works, mute/force/rate-limit respected).
- **Discount editing** supports create + toggle + delete/disable; a full
  pre-filled edit form is not implemented.
- Subscription reset uses the newly verified `POST /api/user/{username}/reset`
  (200 OK); `POST /api/user/{username}/revoke_sub` also works but is unused.
- Settings screen is read-only (plans) as allowed by the spec.
