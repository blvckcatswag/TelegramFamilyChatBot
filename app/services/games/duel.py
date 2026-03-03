import random
import asyncio
from datetime import timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatPermissions
from app.db import repositories as repo
from app.config import settings as cfg
from app.bot.keyboards import duel_accept_kb
from app.utils.helpers import mention_user, now_kyiv

router = Router()

# In-memory pending duels: {chat_id: {challenger_id: {opponent_id, mute_minutes, msg_id, task}}}
_pending_duels: dict[int, dict] = {}


async def can_mute_user(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Check if the bot can mute a specific user (not owner/admin)."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        # Can't mute creators or admins
        return member.status not in ("creator", "administrator")
    except Exception:
        return False


@router.message(Command("duel"))
async def cmd_duel(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer("🎮 Игры отключены.")
        return

    # Check cooldown (minutes-based)
    last = await repo.get_last_duel_time(chat_id, user_id)
    if last:
        from datetime import datetime
        last_dt = datetime.fromisoformat(last)
        # Handle naive datetimes from old records
        if last_dt.tzinfo is None:
            from app.utils.helpers import KYIV_TZ
            last_dt = last_dt.replace(tzinfo=KYIV_TZ)
        diff = now_kyiv() - last_dt
        if diff < timedelta(minutes=cfg.DUEL_COOLDOWN_MINUTES):
            remaining = cfg.DUEL_COOLDOWN_MINUTES - int(diff.total_seconds() / 60)
            await message.answer(f"⚔️ Кулдаун! Подожди {remaining} мин.")
            return

    # Parse command arguments
    args = message.text.split()[1:]
    if not args:
        await message.answer(
            "⚔️ <b>Дуэль</b>\n\n"
            "Использование: /duel @username [минуты]\n"
            "Пример: /duel @ivan 15",
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
            if entity.type == "text_mention":
                opponent = entity.user

    # Parse mute minutes
    for arg in args:
        try:
            mute_minutes = max(5, min(120, int(arg)))
        except ValueError:
            pass

    if opponent and opponent.id == user_id:
        await message.answer("⚔️ Нельзя вызвать самого себя!")
        return

    if opponent and await repo.is_user_muted(chat_id, opponent.id):
        await message.answer("⚔️ Нельзя вызвать того, кто уже в муте!")
        return

    challenger_name = mention_user(message.from_user.first_name, message.from_user.username, user_id)
    if opponent:
        target_text = mention_user(opponent.first_name, opponent.username, opponent.id)
    else:
        target_text = args[0] if args else "любого смельчака"

    sent = await message.answer(
        f"⚔️ <b>Вызов на дуэль!</b>\n\n"
        f"{challenger_name} вызывает {target_text}!\n"
        f"⏰ Мут: {mute_minutes} мин.\n"
        f"⏳ {cfg.DUEL_ACCEPT_TIMEOUT} секунд на ответ!",
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
                    "⚔️ Дуэль отменена — соперник не принял вызов.",
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
        await callback.answer("⚔️ Нельзя принять свою дуэль!", show_alert=True)
        return

    pending = _pending_duels.get(chat_id, {}).get(challenger_id)
    if not pending:
        await callback.answer("⚔️ Дуэль уже завершена или отменена.", show_alert=True)
        return

    # If specific opponent was set, only they can accept
    if pending["opponent_id"] and pending["opponent_id"] != acceptor_id:
        await callback.answer("⚔️ Этот вызов не для тебя!", show_alert=True)
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
        f"⚔️ <b>Дуэль завершена!</b>\n\n"
        f"🏆 Победитель: {winner_name}\n"
        f"💀 Проигравший: {loser_name}\n"
    )

    # Try to mute loser (check if mutable first)
    if await can_mute_user(bot, chat_id, loser_id):
        try:
            mute_until = now_kyiv() + timedelta(minutes=mute_minutes)
            await bot.restrict_chat_member(
                chat_id, loser_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=mute_until,
            )
            await repo.log_mute(chat_id, loser_id, "duel", mute_until.isoformat())
            result_text += f"🔇 Мут на {mute_minutes} мин."
        except Exception:
            result_text += "ℹ️ Мут не применён (бот не админ)."
    else:
        result_text += "ℹ️ Мут не применён (проигравший — админ/владелец чата)."

    await callback.message.edit_text(result_text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "game:duel")
async def cb_duel_info(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚔️ <b>Дуэль</b>\n\n"
        "Используй команду:\n"
        "/duel @username [минуты]\n\n"
        "Пример: /duel @ivan 15\n"
        f"По умолчанию: {cfg.DUEL_DEFAULT_MUTE_MINUTES} минут мута.",
        parse_mode="HTML",
    )
    await callback.answer()
