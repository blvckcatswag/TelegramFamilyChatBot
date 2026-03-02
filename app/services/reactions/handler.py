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

    # Get the latest reaction emoji
    for reaction in event.new_reaction:
        emoji = reaction.emoji if hasattr(reaction, "emoji") else str(reaction)
        await repo.save_reaction(
            chat_id=chat_id,
            message_id=message_id,
            from_user_id=from_user_id,
            emoji=emoji,
            to_user_id=None,  # We can't always know the message author
        )


@router.message(Command("top_reactions"))
async def cmd_top_reactions(message: Message):
    top = await repo.get_top_reactions(message.chat.id, 5)
    if not top:
        await message.answer("\U0001f44d \u041d\u0435\u0442 \u0440\u0435\u0430\u043a\u0446\u0438\u0439 \u0437\u0430 \u044d\u0442\u043e\u0442 \u043c\u0435\u0441\u044f\u0446.")
        return

    lines = ["\U0001f44d <b>\u0422\u043e\u043f-5 \u0440\u0435\u0430\u043a\u0446\u0438\u0439 \u043c\u0435\u0441\u044f\u0446\u0430</b>\n"]
    for i, r in enumerate(top, 1):
        lines.append(f"{i}. {r['emoji']} \u2014 {r['cnt']} \u0440\u0430\u0437")

    # Also show who received most reactions
    received = await repo.get_reactions_received_top(message.chat.id)
    if received:
        lines.append("\n<b>\u041a\u0442\u043e \u043f\u043e\u043b\u0443\u0447\u0430\u0435\u0442 \u0431\u043e\u043b\u044c\u0448\u0435 \u0432\u0441\u0435\u0445:</b>")
        for i, r in enumerate(received[:5], 1):
            name = r.get("first_name") or r.get("username") or "?"
            lines.append(f"{i}. {name} \u2014 {r['cnt']} \u0440\u0435\u0430\u043a\u0446\u0438\u0439")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("my_reactions"))
async def cmd_my_reactions(message: Message):
    count = await repo.get_my_reactions_count(message.chat.id, message.from_user.id)
    await message.answer(
        f"\U0001f44d <b>\u0422\u0432\u043e\u0438 \u0440\u0435\u0430\u043a\u0446\u0438\u0438</b>\n\n"
        f"\u0422\u0432\u043e\u0438 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u043f\u043e\u043b\u0443\u0447\u0438\u043b\u0438: <b>{count}</b> \u0440\u0435\u0430\u043a\u0446\u0438\u0439",
        parse_mode="HTML",
    )
