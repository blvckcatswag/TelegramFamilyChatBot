import random
import asyncio
import json
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatPermissions
from app.db import repositories as repo
from app.config import settings as cfg
from app.bot.keyboards import roulette_join_kb
from app.utils.helpers import mention_user

router = Router()

# In-memory active roulettes: {chat_id: {msg_id: {participants: [user_ids], creator_id, task}}}
_active_roulettes: dict[int, dict] = {}

NARRATIVES = [
    "{name} \u043d\u0430\u0436\u0438\u043c\u0430\u0435\u0442 \u043a\u0443\u0440\u043e\u043a... \u0429\u0435\u043b\u0447\u043e\u043a! \u0412\u044b\u0436\u0438\u043b! \U0001f605",
    "{name} \u0434\u0440\u043e\u0436\u0430\u0449\u0435\u0439 \u0440\u0443\u043a\u043e\u0439 \u0442\u044f\u043d\u0435\u0442 \u0441\u043f\u0443\u0441\u043a... \u041f\u0443\u0441\u0442\u043e! \U0001f60e",
    "{name} \u0437\u0430\u043a\u0440\u044b\u0432\u0430\u0435\u0442 \u0433\u043b\u0430\u0437\u0430 \u0438 \u0441\u0442\u0440\u0435\u043b\u044f\u0435\u0442... \u0412\u044b\u0436\u0438\u0432\u0430\u0435\u0442 \u0438 \u0438\u0434\u0451\u0442 \u043c\u0435\u043d\u044f\u0442\u044c \u0442\u0440\u0443\u0441\u0438\u0448\u043a\u0438 \U0001f605",
    "{name} \u0441\u043c\u0435\u043b\u043e \u043d\u0430\u0436\u0438\u043c\u0430\u0435\u0442... \u041f\u0440\u043e\u043d\u0435\u0441\u043b\u043e! \U0001f64f",
]

DEATH_NARRATIVE = "\U0001f52b\U0001f4a5 {name} \u043d\u0430\u0436\u0438\u043c\u0430\u0435\u0442 \u043a\u0443\u0440\u043e\u043a... <b>\u0411\u0410\u041d\u0413!</b> {name} \u043f\u043e\u043a\u0438\u0434\u0430\u0435\u0442 \u0438\u0433\u0440\u0443! \U0001f480"


@router.message(Command("roulette"))
async def cmd_roulette(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer("\U0001f3ae \u0418\u0433\u0440\u044b \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u044b.")
        return

    # Check cooldown
    last = await repo.get_last_roulette_time(chat_id, user_id)
    if last:
        last_dt = datetime.fromisoformat(last)
        if datetime.utcnow() - last_dt < timedelta(hours=cfg.ROULETTE_COOLDOWN_HOURS):
            remaining = cfg.ROULETTE_COOLDOWN_HOURS * 60 - int((datetime.utcnow() - last_dt).total_seconds() / 60)
            await message.answer(f"\U0001f52b \u041a\u0443\u043b\u0434\u0430\u0443\u043d! \u041f\u043e\u0434\u043e\u0436\u0434\u0438 {remaining} \u043c\u0438\u043d.")
            return

    sent = await message.answer(
        f"\U0001f52b <b>\u0420\u0443\u0441\u0441\u043a\u0430\u044f \u0440\u0443\u043b\u0435\u0442\u043a\u0430!</b>\n\n"
        f"\u0411\u0430\u0440\u0430\u0431\u0430\u043d \u043d\u0430 6 \u043f\u043e\u0437\u0438\u0446\u0438\u0439, 1 \u043f\u0430\u0442\u0440\u043e\u043d.\n"
        f"\u0423\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0438: 1/{cfg.ROULETTE_MAX_PLAYERS}\n"
        f"\u23f3 {cfg.ROULETTE_JOIN_TIMEOUT} \u0441\u0435\u043a\u0443\u043d\u0434 \u043d\u0430 \u0441\u0431\u043e\u0440!\n\n"
        f"1. {message.from_user.first_name}",
        reply_markup=roulette_join_kb(0),
        parse_mode="HTML",
    )

    if chat_id not in _active_roulettes:
        _active_roulettes[chat_id] = {}

    _active_roulettes[chat_id][sent.message_id] = {
        "participants": [user_id],
        "names": {user_id: message.from_user.first_name},
        "creator_id": user_id,
    }

    # Update keyboard with correct msg_id
    await bot.edit_message_reply_markup(
        chat_id, sent.message_id,
        reply_markup=roulette_join_kb(sent.message_id),
    )


@router.callback_query(F.data.startswith("roulette:join:"))
async def cb_roulette_join(callback: CallbackQuery, bot: Bot):
    msg_id = int(callback.data.split(":")[2])
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    game = _active_roulettes.get(chat_id, {}).get(msg_id)
    if not game:
        await callback.answer("\U0001f52b \u0418\u0433\u0440\u0430 \u0443\u0436\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430.", show_alert=True)
        return

    if user_id in game["participants"]:
        await callback.answer("\u0422\u044b \u0443\u0436\u0435 \u0432 \u0438\u0433\u0440\u0435!")
        return

    if len(game["participants"]) >= cfg.ROULETTE_MAX_PLAYERS:
        await callback.answer("\u041c\u0430\u043a\u0441\u0438\u043c\u0443\u043c \u0438\u0433\u0440\u043e\u043a\u043e\u0432!", show_alert=True)
        return

    game["participants"].append(user_id)
    game["names"][user_id] = callback.from_user.first_name
    await repo.get_or_create_user(user_id, chat_id, callback.from_user.username, callback.from_user.first_name)

    players_list = "\n".join(
        f"{i+1}. {game['names'][uid]}" for i, uid in enumerate(game["participants"])
    )

    await callback.message.edit_text(
        f"\U0001f52b <b>\u0420\u0443\u0441\u0441\u043a\u0430\u044f \u0440\u0443\u043b\u0435\u0442\u043a\u0430!</b>\n\n"
        f"\u0411\u0430\u0440\u0430\u0431\u0430\u043d \u043d\u0430 6 \u043f\u043e\u0437\u0438\u0446\u0438\u0439, 1 \u043f\u0430\u0442\u0440\u043e\u043d.\n"
        f"\u0423\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u0438: {len(game['participants'])}/{cfg.ROULETTE_MAX_PLAYERS}\n\n"
        f"{players_list}",
        reply_markup=roulette_join_kb(msg_id),
        parse_mode="HTML",
    )
    await callback.answer(f"\u2705 \u0422\u044b \u0432 \u0438\u0433\u0440\u0435!")


@router.callback_query(F.data.startswith("roulette:start:"))
async def cb_roulette_start(callback: CallbackQuery, bot: Bot):
    msg_id = int(callback.data.split(":")[2])
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    game = _active_roulettes.get(chat_id, {}).get(msg_id)
    if not game:
        await callback.answer("\U0001f52b \u0418\u0433\u0440\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430.", show_alert=True)
        return

    if user_id != game["creator_id"]:
        await callback.answer("\u0422\u043e\u043b\u044c\u043a\u043e \u0441\u043e\u0437\u0434\u0430\u0442\u0435\u043b\u044c \u043c\u043e\u0436\u0435\u0442 \u043d\u0430\u0447\u0430\u0442\u044c!", show_alert=True)
        return

    participants = game["participants"]
    names = game["names"]
    del _active_roulettes[chat_id][msg_id]

    # Build narrative
    loser_id = random.choice(participants)
    narrative_lines = []

    # Shuffle order for dramatic effect
    order = participants.copy()
    random.shuffle(order)

    for uid in order:
        name = names.get(uid, "???")
        if uid == loser_id:
            narrative_lines.append(DEATH_NARRATIVE.format(name=name))
        else:
            narrative_lines.append(random.choice(NARRATIVES).format(name=name))

    # Save to DB
    await repo.create_roulette(chat_id, json.dumps(participants), loser_id)

    result_text = "\U0001f52b <b>\u0411\u0430\u0440\u0430\u0431\u0430\u043d \u043a\u0440\u0443\u0442\u0438\u0442\u0441\u044f...</b>\n\n"
    result_text += "\n".join(narrative_lines)

    # Try to mute loser
    loser_name = names.get(loser_id, "???")
    try:
        mute_until = datetime.utcnow() + timedelta(minutes=cfg.ROULETTE_MUTE_MINUTES)
        await bot.restrict_chat_member(
            chat_id, loser_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=mute_until,
        )
        await repo.log_mute(chat_id, loser_id, "roulette", mute_until.isoformat())
        result_text += f"\n\n\U0001f507 {loser_name} \u0432 \u043c\u0443\u0442\u0435 \u043d\u0430 {cfg.ROULETTE_MUTE_MINUTES} \u043c\u0438\u043d."
    except Exception:
        result_text += f"\n\n\u2139\ufe0f \u041c\u0443\u0442 \u043d\u0435 \u043f\u0440\u0438\u043c\u0435\u043d\u0451\u043d (\u0431\u043e\u0442 \u043d\u0435 \u0430\u0434\u043c\u0438\u043d)."

    await callback.message.edit_text(result_text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "game:roulette")
async def cb_roulette_info(callback: CallbackQuery):
    await callback.message.edit_text(
        "\U0001f52b <b>\u0420\u0443\u0441\u0441\u043a\u0430\u044f \u0440\u0443\u043b\u0435\u0442\u043a\u0430</b>\n\n"
        "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 /roulette \u0434\u043b\u044f \u0437\u0430\u043f\u0443\u0441\u043a\u0430.\n"
        f"2\u2013{cfg.ROULETTE_MAX_PLAYERS} \u0438\u0433\u0440\u043e\u043a\u043e\u0432, {cfg.ROULETTE_JOIN_TIMEOUT} \u0441\u0435\u043a \u043d\u0430 \u0441\u0431\u043e\u0440.\n"
        f"\u041f\u0440\u043e\u0438\u0433\u0440\u0430\u0432\u0448\u0438\u0439 \u043f\u043e\u043b\u0443\u0447\u0430\u0435\u0442 \u043c\u0443\u0442 \u043d\u0430 {cfg.ROULETTE_MUTE_MINUTES} \u043c\u0438\u043d.\n"
        "\u0421\u043e\u043b\u043e: 1/6 \u0448\u0430\u043d\u0441 \u043c\u0443\u0442\u0430.",
        parse_mode="HTML",
    )
    await callback.answer()
