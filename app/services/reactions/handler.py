from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, MessageReactionUpdated
from app.db import repositories as repo
from app.bot.keyboards import back_to_menu_kb

router = Router()


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

    for reaction in event.new_reaction:
        emoji = reaction.emoji if hasattr(reaction, "emoji") else str(reaction)
        await repo.save_reaction(
            chat_id=chat_id,
            message_id=message_id,
            from_user_id=from_user_id,
            emoji=emoji,
            to_user_id=to_user_id,
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
