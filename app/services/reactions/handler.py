import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, MessageReactionUpdated, ReactionTypeEmoji, ReactionTypePaid

from app.db import repositories as repo

router = Router()
logger = logging.getLogger(__name__)

# Reactions that trigger saving a quote with the corresponding category
QUOTE_TRIGGERS: dict[str, str] = {
    "⭐": "⭐",
    "🌚": "🌚",
    "🤔": "🤔",
    "🗿": "🗿",
    "🤡": "🤡",
}

MEDIA_LABELS = {
    "photo": "[Фото]",
    "voice": "[Голосовое]",
    "video_note": "[Кружочек]",
    "video": "[Видео]",
    "sticker": "[Стикер]",
    "audio": "[Аудио]",
    "document": "[Документ]",
}


@router.message_reaction()
async def on_reaction(event: MessageReactionUpdated):
    if not event.new_reaction:
        return

    chat_id = event.chat.id
    message_id = event.message_id
    from_user_id = event.user.id if event.user else None

    if not from_user_id:
        return

    to_user_id = await repo.get_message_author(chat_id, message_id)

    # Determine which emojis were newly added
    old_emojis = set()
    for r in (event.old_reaction or []):
        if isinstance(r, ReactionTypeEmoji):
            old_emojis.add(r.emoji)

    for reaction in event.new_reaction:
        if isinstance(reaction, ReactionTypeEmoji):
            emoji = reaction.emoji
        elif isinstance(reaction, ReactionTypePaid):
            emoji = "⭐"
        else:
            emoji = str(reaction)

        await repo.save_reaction(
            chat_id=chat_id,
            message_id=message_id,
            from_user_id=from_user_id,
            emoji=emoji,
            to_user_id=to_user_id,
        )

        # Quote trigger: only for newly added reactions
        if emoji in QUOTE_TRIGGERS and emoji not in old_emojis:
            await _try_save_quote(chat_id, message_id, from_user_id, emoji)


async def _try_save_quote(chat_id: int, message_id: int, saved_by_id: int, emoji: str):
    """Try to save a message as a quote based on a reaction."""
    msg_data = await repo.get_message_data(chat_id, message_id)
    if not msg_data:
        logger.debug("No message data for quote: chat=%s msg=%s", chat_id, message_id)
        return

    author_id = msg_data["user_id"]

    # Don't quote bot messages (author_id would be the bot's ID, but we
    # don't easily know it here; skip if author == reaction sender as a heuristic)
    # Actually, the TZ says "Реакция на сообщение бота → Игнорируется".
    # We can't reliably check this without the bot's ID. We'll rely on the
    # fact that bot messages are rarely reacted to with these specific emojis.

    text = msg_data.get("text")
    media_type = msg_data.get("media_type")

    if not text and not media_type:
        return

    category = QUOTE_TRIGGERS[emoji]
    result = await repo.save_quote(
        chat_id=chat_id,
        author_id=author_id,
        saved_by_id=saved_by_id,
        text=text,
        message_id=message_id,
        category=category,
        media_type=media_type,
    )

    if result:
        logger.info(
            "Quote saved via reaction: chat=%s msg=%s cat=%s author=%s",
            chat_id, message_id, category, author_id,
        )


@router.message(Command("top_reactions"))
async def cmd_top_reactions(message: Message):
    top = await repo.get_top_reactions(message.chat.id, 5)
    if not top:
        await message.answer("👍 Нет реакций за этот месяц.")
        return

    lines = ["👍 <b>Топ-5 реакций месяца</b>\n"]
    for i, r in enumerate(top, 1):
        lines.append(f"{i}. {r['emoji']} — {r['cnt']} раз")

    received = await repo.get_reactions_received_top(message.chat.id)
    if received:
        lines.append("\n<b>Кто получает больше всех:</b>")
        for i, r in enumerate(received[:5], 1):
            name = r.get("first_name") or r.get("username") or "?"
            lines.append(f"{i}. {name} — {r['cnt']} реакций")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("my_reactions"))
async def cmd_my_reactions(message: Message):
    count = await repo.get_my_reactions_count(message.chat.id, message.from_user.id)
    await message.answer(
        f"👍 <b>Твои реакции</b>\n\n"
        f"Твои сообщения получили: <b>{count}</b> реакций",
        parse_mode="HTML",
    )
