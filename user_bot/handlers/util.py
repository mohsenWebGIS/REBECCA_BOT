"""Small handler helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from telegram import CallbackQuery, InlineKeyboardMarkup, Message
from telegram.error import BadRequest

from core.config import settings
from core.rebecca_api import RebeccaClient

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_MIME_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _extension(file_name: Optional[str], mime: Optional[str]) -> str:
    if file_name and "." in file_name:
        ext = file_name.rsplit(".", 1)[-1].lower()
        if ext.isalnum() and len(ext) <= 5:
            return ext
    if mime and mime in _MIME_EXT:
        return _MIME_EXT[mime]
    return "bin"


async def save_uploaded_file(
    context: Any,
    message: Message,
    kind: str,
    public_id: str,
    index: int = 1,
) -> tuple[Optional[str], Optional[str]]:
    """Download a screenshot (photo or image document) to disk. Returns (path, error)."""
    if message.photo:
        media = message.photo[-1]
        file_id = media.file_id
        size = media.file_size or 0
        ext = "jpg"
    elif message.document:
        media = message.document
        file_id = media.file_id
        size = media.file_size or 0
        mime = media.mime_type or ""
        if not mime.startswith("image/"):
            return None, "Please send a screenshot (image) of the payment."
        ext = _extension(media.file_name, mime)
    else:
        return None, "Please send a screenshot (image)."

    if size and size > MAX_UPLOAD_BYTES:
        return None, "File is too large. Maximum size is 20 MB."

    target_dir = Path(settings.receipts_dir) / kind
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"{public_id}_{index}.{ext}"
    tg_file = await context.bot.get_file(file_id)
    await tg_file.download_to_drive(str(dest))
    return str(dest), None


def client(context: Any) -> RebeccaClient:
    return context.application.bot_data["rebecca"]


async def safe_edit(
    query: CallbackQuery,
    text: str,
    markup: Optional[InlineKeyboardMarkup] = None,
    *,
    disable_preview: bool = True,
) -> None:
    kwargs = {"parse_mode": "HTML", "reply_markup": markup}
    if disable_preview:
        kwargs["disable_web_page_preview"] = True
    try:
        await query.edit_message_text(text, **kwargs)
    except BadRequest:
        if query.message is not None:
            await query.message.reply_text(text, **kwargs)


async def answer(query: CallbackQuery, text: Optional[str] = None) -> None:
    try:
        await query.answer(text=text)
    except BadRequest:
        pass
