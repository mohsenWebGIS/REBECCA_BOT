"""AI assistant chat with rate limiting and rolling history."""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from core.config import settings
from core.db import queries as q
from core.i18n import format_number, t
from core.services.ai_context import build_context
from user_bot import keyboards as kb, states, ui
from user_bot.handlers.util import answer, safe_edit

logger = logging.getLogger(__name__)

AI_HOURLY_LIMIT = 20
AI_MESSAGE_MAX_CHARS = 2000
AI_REPLY_MAX_CHARS = 3500
PROVIDER_BASES = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
}
PROVIDER_MODELS = {
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
}


def _llm_config() -> tuple[str, str, str]:
    provider = (settings.llm_provider or "openai").strip().lower()
    base = (settings.llm_base_url or PROVIDER_BASES.get(provider) or PROVIDER_BASES["openai"]).rstrip("/")
    model = settings.llm_model or PROVIDER_MODELS.get(provider) or PROVIDER_MODELS["openai"]
    return f"{base}/chat/completions", model, provider


async def _call_llm(system: str, history: list[dict]) -> Optional[str]:
    api_key = settings.llm_api_key
    if not api_key or api_key.strip() in {"", "sk-..."}:
        return None
    endpoint, model, _provider = _llm_config()
    messages = [{"role": "system", "content": system}]
    for row in history:
        role = row.get("role")
        if role in {"user", "assistant"} and row.get("content"):
            messages.append({"role": role, "content": row["content"]})
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max(64, int(settings.llm_max_tokens)),
        "temperature": 0.4,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            resp = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        reply = data["choices"][0]["message"]["content"]
        if not isinstance(reply, str):
            return None
        return reply[:AI_REPLY_MAX_CHARS]
    except Exception:
        logger.exception("LLM request failed")
        return None


async def start_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await answer(query)
    states.set_state(update.effective_user.id, states.FLOW_AI)
    text, markup = ui.render_ai_intro()
    await safe_edit(query, text, markup)


async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await q.clear_ai_history(update.effective_user.id)
    await answer(query, t("Chat cleared."))
    text, markup = ui.render_ai_intro()
    await safe_edit(query, text, markup)


async def on_chat_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    uid = update.effective_user.id
    if states.get_flow(uid) != states.FLOW_AI:
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    if len(text) > AI_MESSAGE_MAX_CHARS:
        await update.message.reply_text(
            t(
                "Your message is too long. Please keep it under {max} characters.",
                max=format_number(AI_MESSAGE_MAX_CHARS),
            ),
            reply_markup=kb.ai_footer(),
        )
        return

    if await q.count_ai_user_messages_since() >= max(
        1, int(settings.llm_daily_message_limit)
    ):
        await update.message.reply_text(
            t(
                "The AI assistant has reached its daily limit. Please try again later or use 🆘 Report Issue."
            ),
            reply_markup=kb.ai_footer(),
        )
        return

    db_count = await q.count_ai_messages_since(uid, 3600)
    if db_count >= AI_HOURLY_LIMIT or states.ai_rate_limited(uid, AI_HOURLY_LIMIT):
        await update.message.reply_text(
            t("⏳ You have reached the AI limit (20 messages/hour). Please try again later, or use 🆘 Report Issue."),
            reply_markup=kb.ai_footer(),
        )
        return

    await q.add_ai_message(uid, "user", text)
    history = await q.list_ai_history(uid, limit=10)
    system = await build_context(uid)
    reply = await _call_llm(system, history)
    if reply is None:
        reply = t(
            "The AI assistant is temporarily unavailable. Please use 🆘 Report Issue and our team will help."
        )
        await update.message.reply_text(reply, reply_markup=kb.ai_footer())
        return
    await q.add_ai_message(uid, "assistant", reply)
    await update.message.reply_text(reply, reply_markup=kb.ai_footer())


def register(application: Application) -> None:
    application.add_handler(CallbackQueryHandler(start_chat, pattern=r"^ai:start$"))
    application.add_handler(CallbackQueryHandler(clear_chat, pattern=r"^ai:clear$"))
