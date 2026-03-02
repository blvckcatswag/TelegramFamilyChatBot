import random
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatPermissions
from app.db import repositories as repo
from app.config import settings as cfg
from app.bot.keyboards import duel_accept_kb
from app.utils.helpers import mention_user

router = Router()

# In-memory pending duels: {chat_id: {challenger_id: {opponent_id, mute_minutes, msg_id, task}}}
_pending_duels: dict[int, dict] = {}


@router.message(Command("duel"))
async def cmd_duel(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer("\U0001f3ae \u0418\u0433\u0440\u044b \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u044b.")
        return

    # Check cooldown
    last = await repo.get_last_duel_time(chat_id, user_id)
    if last:
        last_dt = datetime.fromisoformat(last)
        if datetime.utcnow() - last_dt < timedelta(hours=cfg.DUEL_COOLDOWN_HOURS):
            remaining = cfg.DUEL_COOLDOWN_HOURS * 60 - int((datetime.utcnow() - last_dt).total_seconds() / 60)
            await message.answer(f"\u2694\ufe0f \u041a\u0443\u043b\u0434\u0430\u0443\u043d! \u041f\u043e\u0434\u043e\u0436\u0434\u0438 {remaining} \u043c\u0438\u043d.")
            return

    # Parse command arguments
    args = message.text.split()[1:]
    if not args:
        await message.answer(
            "\u2694\ufe0f <b>\u0414\u0443\u044d\u043b\u044c</b>\n\n"
            "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /duel @username [\u043c\u0438\u043d\u0443\u0442\u044b]\n"
            "\u041f\u0440\u0438\u043c\u0435\u0440: /duel @ivan 15",
            parse_mode="HTML",
        )
        return

    # Get opponent from reply or mention
    opponent = None
    mute_minutes = cfg.DUEL_DEFAULT_MUTE_MINUTES

    if message.reply_to_message and message.reply_to_message.from_user:
        opponent = message.reply_to_message.from_user
    elif message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                # We can't resolve @username to user_id without API call
                # The opponent will need to accept via button
                pass
            elif entity.type == "text_mention":
                opponent = entity.user

    # Parse mute minutes
    for arg in args:
        try:
            mute_minutes = max(5, min(120, int(arg)))
        except ValueError:
            pass

    if opponent and opponent.id == user_id:
        await message.answer("\u2694\ufe0f \u041d\u0435\u043b\u044c\u0437\u044f \u0432\u044b\u0437\u0432\u0430\u0442\u044c \u0441\u0430\u043c\u043e\u0433\u043e \u0441\u0435\u0431\u044f!")
        return

    if opponent and await repo.is_user_muted(chat_id, opponent.id):
        await message.answer("\u2694\ufe0f \u041d\u0435\u043b\u044c\u0437\u044f \u0432\u044b\u0437\u0432\u0430\u0442\u044c \u0442\u043e\u0433\u043e, \u043a\u0442\u043e \u0443\u0436\u0435 \u0432 \u043c\u0443\u0442\u0435!")
        return

    challenger_name = mention_user(message.from_user.first_name, message.from_user.username, user_id)
    target_text = ""
    if opponent:
        target_text = mention_user(opponent.first_name, opponent.username, opponent.id)
    else:
        target_text = args[0] if args else "\u043b\u044e\u0431\u043e\u0433\u043e \u0441\u043c\u0435\u043b\u044c\u0447\u0430\u043a\u0430"

    sent = await message.answer(
        f"\u2694\ufe0f <b>\u0412\u044b\u0437\u043e\u0432 \u043d\u0430 \u0434\u0443\u044d\u043b\u044c!</b>\n\n"
        f"{challenger_name} \u0432\u044b\u0437\u044b\u0432\u0430\u0435\u0442 {target_text}!\n"
        f"\u23f0 \u041c\u0443\u0442: {mute_minutes} \u043c\u0438\u043d.\n"
        f"\u23f3 {cfg.DUEL_ACCEPT_TIMEOUT} \u0441\u0435\u043a\u0443\u043d\u0434 \u043d\u0430 \u043e\u0442\u0432\u0435\u0442!",
        reply_markup=duel_accept_kb(user_id, mute_minutes),
        parse_mode="HTML",
    )

    # Store pending duel
    if chat_id not in _pending_duels:
        _pending_duels[chat_id] = {}

    async def timeout_duel():
        await asyncio.sleep(cfg.DUEL_ACCEPT_TIMEOUT)
        if chat_id in _pending_duels and user_id in _pending_duels[chat_id]:
            del _pending_duels[chat_id][user_id]
            try:
                await bot.edit_message_text(
                    "\u2694\ufe0f \u0414\u0443\u044d\u043b\u044c \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u0430 \u2014 \u0441\u043e\u043f\u0435\u0440\u043d\u0438\u043a \u043d\u0435 \u043f\u0440\u0438\u043d\u044f\u043b \u0432\u044b\u0437\u043e\u0432.",
                    chat_id=chat_id, message_id=sent.message_id,
                )
            except Exception:
                pass

    task = asyncio.create_task(timeout_duel())
    _pending_duels[chat_id][user_id] = {
        "opponent_id": opponent.id if opponent else None,
        "mute_minutes": mute_minutes,
        "msg_id": sent.message_id,
        "task": task,
    }


@router.callback_query(F.data.startswith("duel:accept:"))
async def cb_duel_accept(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    challenger_id = int(parts[2])
    mute_minutes = int(parts[3])
    chat_id = callback.message.chat.id
    acceptor_id = callback.from_user.id

    if acceptor_id == challenger_id:
        await callback.answer("\u2694\ufe0f \u041d\u0435\u043b\u044c\u0437\u044f \u043f\u0440\u0438\u043d\u044f\u0442\u044c \u0441\u0432\u043e\u044e \u0434\u0443\u044d\u043b\u044c!", show_alert=True)
        return

    pending = _pending_duels.get(chat_id, {}).get(challenger_id)
    if not pending:
        await callback.answer("\u2694\ufe0f \u0414\u0443\u044d\u043b\u044c \u0443\u0436\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430 \u0438\u043b\u0438 \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u0430.", show_alert=True)
        return

    # If specific opponent was set, only they can accept
    if pending["opponent_id"] and pending["opponent_id"] != acceptor_id:
        await callback.answer("\u2694\ufe0f \u042d\u0442\u043e\u0442 \u0432\u044b\u0437\u043e\u0432 \u043d\u0435 \u0434\u043b\u044f \u0442\u0435\u0431\u044f!", show_alert=True)
        return

    # Cancel timeout
    pending["task"].cancel()
    del _pending_duels[chat_id][challenger_id]

    # Register users
    await repo.get_or_create_user(acceptor_id, chat_id, callback.from_user.username, callback.from_user.first_name)

    # Determine winner
    winner_id = random.choice([challenger_id, acceptor_id])
    loser_id = acceptor_id if winner_id == challenger_id else challenger_id

    await repo.create_duel(chat_id, challenger_id, acceptor_id, winner_id, mute_minutes)

    # Get names
    winner = await bot.get_chat_member(chat_id, winner_id)
    loser = await bot.get_chat_member(chat_id, loser_id)
    winner_name = mention_user(winner.user.first_name, winner.user.username, winner_id)
    loser_name = mention_user(loser.user.first_name, loser.user.username, loser_id)

    result_text = (
        f"\u2694\ufe0f <b>\u0414\u0443\u044d\u043b\u044c \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430!</b>\n\n"
        f"\U0001f3c6 \u041f\u043e\u0431\u0435\u0434\u0438\u0442\u0435\u043b\u044c: {winner_name}\n"
        f"\U0001f480 \u041f\u0440\u043e\u0438\u0433\u0440\u0430\u0432\u0448\u0438\u0439: {loser_name}\n"
    )

    # Try to mute loser
    try:
        mute_until = datetime.utcnow() + timedelta(minutes=mute_minutes)
        await bot.restrict_chat_member(
            chat_id, loser_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=mute_until,
        )
        await repo.log_mute(chat_id, loser_id, "duel", mute_until.isoformat())
        result_text += f"\U0001f507 \u041c\u0443\u0442 \u043d\u0430 {mute_minutes} \u043c\u0438\u043d."
    except Exception:
        result_text += "\u2139\ufe0f \u041c\u0443\u0442 \u043d\u0435 \u043f\u0440\u0438\u043c\u0435\u043d\u0451\u043d (\u0431\u043e\u0442 \u043d\u0435 \u0430\u0434\u043c\u0438\u043d)."

    await callback.message.edit_text(result_text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "game:duel")
async def cb_duel_info(callback: CallbackQuery):
    await callback.message.edit_text(
        "\u2694\ufe0f <b>\u0414\u0443\u044d\u043b\u044c</b>\n\n"
        "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u043a\u043e\u043c\u0430\u043d\u0434\u0443:\n"
        "/duel @username [\u043c\u0438\u043d\u0443\u0442\u044b]\n\n"
        "\u041f\u0440\u0438\u043c\u0435\u0440: /duel @ivan 15\n"
        "\u041f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e: 30 \u043c\u0438\u043d\u0443\u0442 \u043c\u0443\u0442\u0430.",
        reply_markup=None, parse_mode="HTML",
    )
    await callback.answer()
