import logging
import traceback

from aiogram import Bot, Router
from aiogram.exceptions import TelegramMigrateToChat
from aiogram.types import ErrorEvent

from app.config import settings as cfg
from app.db import repositories as repo

logger = logging.getLogger(__name__)
router = Router()


@router.error()
async def global_error_handler(event: ErrorEvent, bot: Bot) -> None:
    """Catch all unhandled handler exceptions, log them and notify superadmin."""
    exc = event.exception

    if isinstance(exc, TelegramMigrateToChat):
        old_chat_id = None
        update = event.update
        if update.message:
            old_chat_id = update.message.chat.id
        elif update.callback_query and update.callback_query.message:
            old_chat_id = update.callback_query.message.chat.id
        new_chat_id = exc.migrate_to_chat_id
        if old_chat_id and new_chat_id:
            logger.info("Chat migrated: %s -> %s, updating DB", old_chat_id, new_chat_id)
            try:
                await repo.migrate_chat(old_chat_id, new_chat_id)
                logger.info("Chat migration complete: %s -> %s", old_chat_id, new_chat_id)
            except Exception:
                logger.exception("Failed to migrate chat %s -> %s", old_chat_id, new_chat_id)
        return

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    logger.error("Unhandled exception:\n%s", tb)

    if not cfg.SUPERADMIN_ID:
        return

    update = event.update
    context_parts = []

    if update.message:
        msg = update.message
        context_parts.append(f"chat: {msg.chat.id} ({msg.chat.title or msg.chat.full_name})")
        if msg.from_user:
            context_parts.append(f"user: @{msg.from_user.username} ({msg.from_user.id})")
        context_parts.append(f"text: {(msg.text or '')[:80]}")
    elif update.callback_query:
        cb = update.callback_query
        context_parts.append(f"callback: {cb.data}")
        if cb.from_user:
            context_parts.append(f"user: @{cb.from_user.username} ({cb.from_user.id})")

    context = "\n".join(context_parts)
    tb_preview = tb[-2500:] if len(tb) > 2500 else tb

    text = (
        "🚨 <b>Необработанная ошибка</b>\n\n"
        f"<pre>{context}</pre>\n\n"
        f"<pre>{tb_preview}</pre>"
    )

    try:
        await bot.send_message(cfg.SUPERADMIN_ID, text)
    except Exception:
        logger.exception("Failed to send error notification to superadmin")
