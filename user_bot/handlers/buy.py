"""Buy flow: plans → promo → payment → receipt upload."""
from __future__ import annotations

import json
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.db import queries as q
from core.i18n import format_toman, normalize_lang, t, use_lang
from core.notifications import notify
from core.pricing import plan_prices
from core.services import discounts as discount_svc
from core.services import orders as order_svc
from core.services import referrals as referral_svc
from core.services.order_alerts import notify_managers_pending_order
from core.services.payment_card import card_state, notify_managers_card_request
from user_bot import keyboards as kb, ratelimit, states, ui
from user_bot.handlers.util import answer, safe_edit, save_uploaded_file


async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await answer(query)
    states.set_state(update.effective_user.id, "", plan_id=None, off=0.0, discount_code=None)
    invite_code = context.user_data.get("invite_code")
    text, markup = await ui.render_plans(
        update.effective_user.id, None, invite_code
    )
    await safe_edit(query, text, markup)


async def promo_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await answer(query)
    states.set_state(update.effective_user.id, states.FLOW_PROMO, plan_id=None)
    await query.message.reply_text(
        t("🎁 Send your promo code as a message, or tap Cancel."),
        reply_markup=kb.cancel_only(),
    )


async def on_promo_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    code = (update.message.text or "").strip()
    uid = update.effective_user.id
    if not ratelimit.allow(uid, "promo", 15, 600) or not ratelimit.allow(
        uid, "promo_cooldown", 1, 2
    ):
        await update.message.reply_text(
            t("Too many requests. Please wait and try again later."),
            reply_markup=kb.cancel_only(),
        )
        return
    plans = await q.list_active_plans()
    if not plans:
        states.clear_state(uid)
        await update.message.reply_text(t("No plans are available right now."))
        return

    ok = False
    reason = "Invalid promo code."
    for plan in plans:
        valid, plan_reason, _ = await discount_svc.validate_code(uid, int(plan["id"]), code)
        if valid:
            ok = True
            break
        reason = plan_reason

    if not ok:
        await update.message.reply_text(
            t(
                "❌ {reason}\n\nSend another code or tap Cancel.",
                reason=ui.esc(t(reason)),
            ),
            reply_markup=kb.cancel_only(),
            parse_mode="HTML",
        )
        return

    states.set_state(uid, "", plan_id=None, off=0.0, discount_code=code.upper())
    text, markup = await ui.render_plans(
        uid, code.upper(), context.user_data.get("invite_code")
    )
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def invite_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await answer(query)
    previous = {
        key: value
        for key, value in states.get_state(update.effective_user.id).items()
        if key != "flow"
    }
    states.set_state(
        update.effective_user.id, states.FLOW_INVITE, **previous
    )
    await query.message.reply_text(
        t("🎟 Send your invitation code as a message, or tap Cancel."),
        reply_markup=kb.cancel_only(),
    )


async def on_invite_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    uid = update.effective_user.id
    state = states.get_state(uid)
    if state.get("flow") != states.FLOW_INVITE:
        return
    if not ratelimit.allow(uid, "invite", 10, 600) or not ratelimit.allow(
        uid, "invite_cooldown", 1, 2
    ):
        await update.message.reply_text(
            t("Too many requests. Please wait and try again later."),
            reply_markup=kb.cancel_only(),
        )
        return
    code = referral_svc.normalize_code(update.message.text)
    _inviter, error = await referral_svc.validate_invite_code(code, uid)
    if error is not None:
        await update.message.reply_text(
            t(
                "❌ {reason}\n\nSend another code or tap Cancel.",
                reason=t(error),
            ),
            reply_markup=kb.cancel_only(),
        )
        return
    context.user_data["invite_code"] = code
    restored = {k: v for k, v in state.items() if k != "flow"}
    states.set_state(uid, "", **restored)
    text, markup = await ui.render_plans(
        uid, state.get("discount_code"), code
    )
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def select_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    uid = update.effective_user.id
    plan_id = int(query.data.rsplit(":", 1)[-1])
    plan = await q.get_plan(plan_id)
    if plan is None or not plan["active"]:
        await answer(query, t("That plan is no longer available."))
        return

    state = states.get_state(uid)
    code = state.get("discount_code")
    off = 0.0
    discount = None
    if code:
        valid, reason, off = await discount_svc.validate_code(uid, plan_id, code)
        if valid:
            discount = await q.get_discount(code)
        else:
            off = 0.0
            code = None
            await answer(query, t(reason))
    states.set_state(uid, "", plan_id=plan_id, off=off, discount_code=code)
    text, markup = await ui.render_payment(
        plan, discount, off, uid, context.user_data.get("invite_code")
    )
    await answer(query)
    await safe_edit(query, text, markup)


async def _payment_from_state(uid: int, context: ContextTypes.DEFAULT_TYPE):
    state = states.get_state(uid)
    renewal_sub_id = state.get("renewal_sub_id")
    if renewal_sub_id:
        sub = await q.get_subscription(int(renewal_sub_id))
        if sub is None or int(sub["telegram_id"]) != uid:
            return None
        plan = dict(
            state.get("renewal_plan")
            or {
                "name": sub.get("plan_name") or t("Renewal"),
                "gb": float(sub.get("plan_gb") or sub.get("traffic_total_gb") or 0),
                "days": int(sub.get("plan_days") or 30),
            }
        )
        return await ui.render_payment(
            plan, None, 0.0, uid, None, int(renewal_sub_id)
        )
    plan_id = state.get("plan_id")
    if not plan_id:
        return None
    plan = await q.get_plan(int(plan_id))
    if plan is None:
        return None
    code = state.get("discount_code")
    discount = await q.get_discount(code) if code else None
    off = float(state.get("off") or 0.0)
    return await ui.render_payment(
        plan, discount, off, uid, context.user_data.get("invite_code")
    )


async def request_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    uid = update.effective_user.id
    card = await card_state(uid)
    if not card["number"]:
        await answer(query, t("Card payment is currently unavailable."))
        return
    if card["show"]:
        await answer(query, t("Card details are already available."))
        rendered = await _payment_from_state(uid, context)
        if rendered is not None:
            await safe_edit(query, rendered[0], rendered[1])
        return
    if card["mode"] != "request":
        await answer(query, t("Card payment is currently unavailable."))
        return
    if card["pending"]:
        await answer(query, t("Your card request is already pending."))
        return
    if not ratelimit.allow(uid, "card_request", 5, 86400) or not ratelimit.allow(
        uid, "card_request_cooldown", 1, 30
    ):
        await answer(query, t("Too many requests. Please wait and try again later."))
        return
    await q.upsert_card_request(uid)
    await notify_managers_card_request(uid, update.effective_user.username)
    await answer(query, t("📩 Card request sent to the manager."))
    rendered = await _payment_from_state(uid, context)
    if rendered is not None:
        await safe_edit(query, rendered[0], rendered[1])


async def refresh_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    rendered = await _payment_from_state(update.effective_user.id, context)
    if rendered is None:
        await answer(query, t("Please choose a plan first."))
        return
    await answer(query)
    await safe_edit(query, rendered[0], rendered[1])


async def receipt_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    uid = update.effective_user.id
    state = states.get_state(uid)
    if not state.get("plan_id") and not state.get("renewal_sub_id"):
        await answer(query, t("Please choose a plan first."))
        return
    await answer(query)
    keys = ("plan_id", "off", "discount_code", "renewal_sub_id", "renewal_plan")
    states.set_state(
        uid, states.FLOW_RECEIPT, **{k: state[k] for k in keys if k in state}
    )
    await query.message.reply_text(
        t("📸 Send a screenshot of your payment transaction (max 20 MB), or /cancel."),
        reply_markup=kb.cancel_only(),
    )


async def _create_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state: dict,
    path: str,
    public_id: str,
) -> None:
    uid = update.effective_user.id
    renewal_sub_id = state.get("renewal_sub_id")
    code = state.get("discount_code")
    off = 0.0
    subscription_id = None
    kind = "new"
    if renewal_sub_id:
        sub = await q.get_subscription(int(renewal_sub_id))
        if sub is None or int(sub["telegram_id"]) != uid:
            await update.message.reply_text(t("Subscription not found."))
            states.clear_state(uid)
            return
        if await q.get_pending_renewal_for_sub(int(sub["id"])) is not None:
            await update.message.reply_text(
                t("A renewal order is already pending for this subscription.")
            )
            states.clear_state(uid)
            return
        plan = dict(
            state.get("renewal_plan")
            or {
                "name": sub.get("plan_name") or t("Renewal"),
                "gb": float(sub.get("plan_gb") or sub.get("traffic_total_gb") or 0),
                "days": int(sub.get("plan_days") or 30),
            }
        )
        plan_id = None
        subscription_id = int(sub["id"])
        kind = "renewal"
        code = None
    else:
        plan = await q.get_plan(int(state["plan_id"]))
        if plan is None:
            await update.message.reply_text(t("That plan is no longer available."))
            states.clear_state(uid)
            return
        plan_id = int(plan["id"])
        off = float(state.get("off") or 0.0)
    base, volume, after = plan_prices(plan)
    final = max(0.0, after - off)
    snapshot = {
        "id": plan_id,
        "name": plan.get("name") or "Plan",
        "gb": float(plan["gb"]),
        "days": int(plan["days"]),
        "price_toman": base,
    }
    if kind == "renewal":
        snapshot["kind"] = "renewal"
        snapshot["subscription_id"] = subscription_id
    order_id = await q.create_order(
        public_id=public_id,
        telegram_id=uid,
        plan_id=plan_id,
        plan_snapshot=snapshot,
        list_price=base,
        final_price=final,
        discount_code=code,
        discount_toman=off,
        volume_discount_toman=volume,
        receipt_path=path,
        status="pending",
        kind=kind,
        subscription_id=subscription_id,
    )
    if code:
        await q.add_redemption(code, uid, order_id)
    if kind == "new":
        invite_code = context.user_data.pop("invite_code", None)
        if invite_code:
            await referral_svc.record_referral(
                order_id, uid, invite_code, float(plan["gb"])
            )
    await notify_managers_pending_order(
        {
            "id": order_id,
            "public_id": public_id,
            "telegram_id": uid,
            "plan_snapshot": snapshot,
            "final_price": final,
            "kind": kind,
            "subscription_id": subscription_id,
        }
    )
    user = await q.get_user(uid)
    with use_lang(normalize_lang(user.get("preferred_lang") if user else "en")):
        await notify(
            uid,
            "order_created",
            t("Order #{public_id} received", public_id=public_id),
            t(
                "Plan {plan} · {amount}. We will review your receipt shortly.",
                plan=plan["name"],
                amount=format_toman(final),
            ),
            order_id=order_id,
            dedupe_key=f"order_created:{order_id}",
            bot=context.bot,
        )
    await update.message.reply_text(ui.receipt_ack(public_id), parse_mode="HTML")
    states.clear_state(uid)


async def _handle_resend(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, path: str) -> None:
    uid = update.effective_user.id
    order_id = int(state["existing_order_id"])
    order = await q.get_order(order_id)
    if order is None or int(order["telegram_id"]) != uid:
        await update.message.reply_text(t("Order not found."))
        states.clear_state(uid)
        return
    history = []
    try:
        history = json.loads(order.get("receipt_history") or "[]")
    except (ValueError, TypeError):
        history = []
    if order.get("receipt_path"):
        history.append(order["receipt_path"])
    await q.update_order(
        order_id,
        receipt_path=path,
        receipt_history=json.dumps(history),
        status="pending",
    )
    await notify_managers_pending_order(
        order, resend=True, receipt_index=len(history)
    )
    await update.message.reply_text(
        t(
            "✅ New receipt received for order #{public_id}. Awaiting review.",
            public_id=ui.esc(order["public_id"]),
        ),
        parse_mode="HTML",
    )
    states.clear_state(uid)


async def on_receipt_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    uid = update.effective_user.id
    if not ratelimit.allow(uid, "receipt", 10, 3600) or not ratelimit.allow(
        uid, "receipt_cooldown", 1, 15
    ):
        await update.message.reply_text(
            t("Too many requests. Please wait and try again later.")
        )
        return
    state = states.get_state(uid)
    existing = state.get("existing_order_id")
    public_id = None
    index = 1
    if existing:
        order = await q.get_order(int(existing))
        if order is not None:
            public_id = order["public_id"]
            try:
                index = len(json.loads(order.get("receipt_history") or "[]")) + 1
            except (ValueError, TypeError):
                index = 1
    if public_id is None:
        public_id = await order_svc.generate_public_id()

    path, error = await save_uploaded_file(context, update.message, "receipt", public_id, index)
    if error or path is None:
        await update.message.reply_text(t(error or "Please send a screenshot (image)."))
        return

    if existing:
        await _handle_resend(update, context, state, path)
    else:
        await _create_order(update, context, state, path, public_id)


async def on_receipt_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if (update.message.text or "").strip() == "/cancel":
        return
    await update.message.reply_text(
        t("Please send the payment screenshot (image), or /cancel."),
        reply_markup=kb.cancel_only(),
    )


async def resend_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    public_id = query.data.split(":", 1)[1]
    order = await q.get_order_by_public_id(public_id)
    if order is None or int(order["telegram_id"]) != update.effective_user.id:
        await answer(query, t("Order not found."))
        return
    await answer(query)
    await q.update_order(int(order["id"]), status="needs_resend")
    states.set_state(update.effective_user.id, states.FLOW_RECEIPT, existing_order_id=int(order["id"]))
    await query.message.reply_text(
        t("📸 Please upload a screenshot of your payment transaction."),
        reply_markup=kb.cancel_only(),
    )


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(show_plans, pattern=r"^buy:start$"))
    application.add_handler(CallbackQueryHandler(promo_prompt, pattern=r"^buy:promo$"))
    application.add_handler(CallbackQueryHandler(invite_prompt, pattern=r"^buy:invite$"))
    application.add_handler(CallbackQueryHandler(select_plan, pattern=r"^buy:plan:\d+$"))
    application.add_handler(CallbackQueryHandler(receipt_prompt, pattern=r"^pay:receipt$"))
    application.add_handler(CallbackQueryHandler(request_card, pattern=r"^pay:card_request$"))
    application.add_handler(CallbackQueryHandler(refresh_card, pattern=r"^pay:card_refresh$"))
    application.add_handler(CallbackQueryHandler(resend_prompt, pattern=r"^resend:.+$"))
