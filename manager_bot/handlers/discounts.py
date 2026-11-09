"""Discount CRUD (create flow, list, toggle, delete/disable)."""
from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.db import queries as q
from core.i18n import format_number, parse_number, t
from manager_bot import keyboards as kb, states, ui
from manager_bot.util import answer, manager_only, safe_edit


@manager_only
async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    text, markup = await ui.render_discounts()
    await safe_edit(query, text, markup)


@manager_only
async def show_one(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    code = query.data.split(":", 2)[-1]
    await answer(query)
    text, markup = await ui.render_discount_view(code)
    await safe_edit(query, text, markup)


@manager_only
async def toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    code = query.data.split(":", 2)[-1]
    discount = await q.get_discount(code)
    if discount is None:
        await answer(query, t("Not found."))
        return
    await q.update_discount(code, active=0 if discount.get("active") else 1)
    await q.add_audit(
        update.effective_user.id, "toggle_discount", "discount", code,
        payload_before={"active": discount.get("active")},
        payload_after={"active": not discount.get("active")},
    )
    await answer(query, t("Toggled."))
    text, markup = await ui.render_discount_view(code)
    await safe_edit(query, text, markup)


@manager_only
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    code = query.data.split(":", 2)[-1]
    discount = await q.get_discount(code)
    if discount is None:
        await answer(query, t("Not found."))
        return
    used = await q.count_redemptions(code)
    if used > 0:
        await q.update_discount(code, active=0)
        await q.add_audit(update.effective_user.id, "disable_discount", "discount", code)
        await answer(
            query,
            t("{count} redemptions exist; disabled instead.", count=format_number(used)),
            alert=True,
        )
    else:
        await q.delete_discount(code)
        await q.add_audit(update.effective_user.id, "delete_discount", "discount", code)
        await answer(query, t("Deleted."))
    text, markup = await ui.render_discounts()
    await safe_edit(query, text, markup)


@manager_only
async def new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await answer(query)
    states.set_state(update.effective_user.id, "disc_code", data={})
    await query.message.reply_text(
        "<b>" + t("➕ New discount") + "</b>\n\n"
        + t("Send the code (letters/numbers), or /cancel."),
        parse_mode="HTML",
    )


@manager_only
async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    state = states.get_state(update.effective_user.id)
    if state.get("action") != "disc_type":
        await answer(query, t("Start from Discounts → New."))
        return
    discount_type = query.data.rsplit(":", 1)[-1]
    data = state.get("data", {})
    data["type"] = discount_type
    states.set_state(update.effective_user.id, "disc_value", data=data)
    await answer(query)
    suffix = "%" if discount_type == "percent" else t("Toman")
    await query.message.reply_text(
        t("Send the value in {unit}, or /cancel.", unit=suffix)
    )


@manager_only
async def choose_applies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    state = states.get_state(update.effective_user.id)
    if state.get("action") != "disc_applies":
        await answer(query, t("Start from Discounts → New."))
        return
    target = query.data.rsplit(":", 1)[-1]
    data = state.get("data", {})
    data["applies_to"] = "all" if target == "all" else target
    states.set_state(update.effective_user.id, "disc_max_uses", data=data)
    await answer(query)
    await query.message.reply_text(
        t("Send max uses (e.g. 100), or send 'skip' for unlimited."), reply_markup=kb.cancel()
    )


async def _create(update: Update, data: dict[str, Any]) -> None:
    await q.create_discount(
        code=data["code"],
        type=data["type"],
        value=float(data["value"]),
        applies_to=str(data.get("applies_to", "all")),
        max_uses=data.get("max_uses"),
        per_user_max=int(data.get("per_user_max", 1)),
        expires_at=data.get("expires_at"),
    )
    await q.add_audit(
        update.effective_user.id, "create_discount", "discount", data["code"],
        payload_after=data,
    )
    states.clear_state(update.effective_user.id)
    text, markup = await ui.render_discount_view(data["code"])
    await update.message.reply_text(
        t("✅ Discount created.") + "\n\n" + text, reply_markup=markup, parse_mode="HTML"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, text: str) -> bool:
    action = state.get("action")
    if not action or not action.startswith("disc_"):
        return False
    admin_id = update.effective_user.id
    data = dict(state.get("data", {}))
    value = text.strip()

    if action == "disc_code":
        if not value.replace("_", "").replace("-", "").isalnum():
            await update.message.reply_text(t("Use only letters, numbers, _ or -."))
            return True
        data["code"] = value.upper()
        states.set_state(admin_id, "disc_type", data=data)
        await update.message.reply_text(
            t("Type of discount:"), reply_markup=kb.discount_type()
        )
        return True
    if action == "disc_value":
        number = parse_number(value.rstrip("%"))
        if number is None:
            await update.message.reply_text(t("Send a number."))
            return True
        data["value"] = number
        states.set_state(admin_id, "disc_applies", data=data)
        plans = await q.list_plans()
        await update.message.reply_text(
            t("Which plans does this apply to?"), reply_markup=kb.discount_applies(plans)
        )
        return True
    if action == "disc_max_uses":
        if value.lower() in {"skip", "none", "unlimited", "0"}:
            data["max_uses"] = None
        else:
            parsed = parse_number(value)
            if parsed is None or parsed != int(parsed):
                await update.message.reply_text(t("Send an integer or 'skip'."))
                return True
            data["max_uses"] = int(parsed)
        states.set_state(admin_id, "disc_per_user", data=data)
        await update.message.reply_text(
            t("Send per-user max redemptions (e.g. 1)."), reply_markup=kb.cancel()
        )
        return True
    if action == "disc_per_user":
        parsed = parse_number(value)
        if parsed is None or parsed != int(parsed):
            await update.message.reply_text(t("Send an integer, e.g. 1."))
            return True
        data["per_user_max"] = max(1, int(parsed))
        states.set_state(admin_id, "disc_expires", data=data)
        await update.message.reply_text(
            t("Send expiry date (YYYY-MM-DD) or 'skip' for no expiry."), reply_markup=kb.cancel()
        )
        return True
    if action == "disc_expires":
        if value.lower() not in {"skip", "none", "never"}:
            from datetime import datetime
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                await update.message.reply_text(t("Use YYYY-MM-DD or 'skip'."))
                return True
            data["expires_at"] = value
        else:
            data["expires_at"] = None
        await _create(update, data)
        return True
    return False


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(new, pattern=r"^discount:new$"))
    application.add_handler(CallbackQueryHandler(show_list, pattern=r"^discounts:list$"))
    application.add_handler(CallbackQueryHandler(show_one, pattern=r"^discount:view:.+$"))
    application.add_handler(CallbackQueryHandler(toggle, pattern=r"^discount:toggle:.+$"))
    application.add_handler(CallbackQueryHandler(delete, pattern=r"^discount:delete:.+$"))
    application.add_handler(CallbackQueryHandler(choose_type, pattern=r"^discount:type:(percent|flat)$"))
    application.add_handler(CallbackQueryHandler(choose_applies, pattern=r"^discount:applies:.+$"))
