import random
import json
from datetime import timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatPermissions
from app.db import repositories as repo
from app.config import settings as cfg
from app.bot.keyboards import roulette_join_kb
from app.utils.helpers import mention_user, now_kyiv, safe_edit_text, safe_edit_reply_markup

router = Router()

# In-memory active roulettes: {chat_id: {msg_id: {participants: [user_ids], creator_id}}}
_active_roulettes: dict[int, dict] = {}

NARRATIVES = [
    "{name} нажимает курок... Щелчок! Выжил! 😅",
    "{name} дрожащей рукой тянет спуск... Пусто! 😎",
    "{name} закрывает глаза и стреляет... Выживает и идёт менять трусишки 😅",
    "{name} смело нажимает... Пронесло! 🙏",
]

DEATH_NARRATIVE = "🔫💥 {name} нажимает курок... <b>БАНГ!</b> {name} покидает игру! 💀"


async def can_mute_user(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status not in ("creator", "administrator")
    except Exception:
        return False


@router.message(Command("roulette"))
async def cmd_roulette(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer("🎮 Игры отключены.")
        return

    # Check cooldown (minutes-based)
    last = await repo.get_last_roulette_time(chat_id, user_id)
    if last:
        from datetime import datetime
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            from app.utils.helpers import KYIV_TZ
            last_dt = last_dt.replace(tzinfo=KYIV_TZ)
        diff = now_kyiv() - last_dt
        if diff < timedelta(minutes=cfg.ROULETTE_COOLDOWN_MINUTES):
            remaining = cfg.ROULETTE_COOLDOWN_MINUTES - int(diff.total_seconds() / 60)
            await message.answer(f"🔫 Кулдаун! Подожди {remaining} мин.")
            return

    sent = await message.answer(
        f"🔫 <b>Русская рулетка!</b>\n\n"
        f"Барабан на 6 позиций, 1 патрон.\n"
        f"Участники: 1/{cfg.ROULETTE_MAX_PLAYERS}\n"
        f"⏳ {cfg.ROULETTE_JOIN_TIMEOUT} секунд на сбор!\n\n"
        f"1. {message.from_user.first_name}",
        reply_markup=roulette_join_kb(),
        parse_mode="HTML",
    )

    if chat_id not in _active_roulettes:
        _active_roulettes[chat_id] = {}

    _active_roulettes[chat_id][sent.message_id] = {
        "participants": [user_id],
        "names": {user_id: message.from_user.first_name},
        "creator_id": user_id,
    }


@router.callback_query(F.data == "roulette:join")
async def cb_roulette_join(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    msg_id = callback.message.message_id
    user_id = callback.from_user.id

    game = _active_roulettes.get(chat_id, {}).get(msg_id)
    if not game:
        await callback.answer("🔫 Игра уже завершена.", show_alert=True)
        return

    if user_id in game["participants"]:
        await callback.answer("Ты уже в игре!")
        return

    if len(game["participants"]) >= cfg.ROULETTE_MAX_PLAYERS:
        await callback.answer("Максимум игроков!", show_alert=True)
        return

    game["participants"].append(user_id)
    game["names"][user_id] = callback.from_user.first_name
    await repo.get_or_create_user(user_id, chat_id, callback.from_user.username, callback.from_user.first_name)

    players_list = "\n".join(
        f"{i+1}. {game['names'][uid]}" for i, uid in enumerate(game["participants"])
    )

    await safe_edit_text(callback.message, 
        f"🔫 <b>Русская рулетка!</b>\n\n"
        f"Барабан на 6 позиций, 1 патрон.\n"
        f"Участники: {len(game['participants'])}/{cfg.ROULETTE_MAX_PLAYERS}\n\n"
        f"{players_list}",
        reply_markup=roulette_join_kb(),
        parse_mode="HTML",
    )
    await callback.answer("✅ Ты в игре!")


@router.callback_query(F.data == "roulette:start")
async def cb_roulette_start(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    msg_id = callback.message.message_id
    user_id = callback.from_user.id

    game = _active_roulettes.get(chat_id, {}).get(msg_id)
    if not game:
        await callback.answer("🔫 Игра не найдена.", show_alert=True)
        return

    if user_id != game["creator_id"]:
        await callback.answer("Только создатель может начать!", show_alert=True)
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

    result_text = "🔫 <b>Барабан крутится...</b>\n\n"
    result_text += "\n".join(narrative_lines)

    # Try to mute loser
    loser_name = names.get(loser_id, "???")
    if await can_mute_user(bot, chat_id, loser_id):
        try:
            mute_until = now_kyiv() + timedelta(minutes=cfg.ROULETTE_MUTE_MINUTES)
            existing_until = await repo.get_active_mute_until(chat_id, loser_id)
            if existing_until and existing_until >= mute_until:
                result_text += f"\n\nℹ️ Мут не изменён — уже действует более длинный мут."
            else:
                await bot.restrict_chat_member(
                    chat_id, loser_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=mute_until,
                )
                await repo.log_mute(chat_id, loser_id, "roulette", mute_until.isoformat())
                result_text += f"\n\n🔇 {loser_name} в муте на {cfg.ROULETTE_MUTE_MINUTES} мин."
        except Exception:
            result_text += f"\n\nℹ️ Мут не применён (бот не админ)."
    else:
        result_text += f"\n\nℹ️ Мут не применён ({loser_name} — админ/владелец чата)."

    await safe_edit_text(callback.message, result_text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "game:roulette")
async def cb_roulette_info(callback: CallbackQuery):
    await safe_edit_text(callback.message, 
        "🔫 <b>Русская рулетка</b>\n\n"
        "Используй /roulette для запуска.\n"
        f"2–{cfg.ROULETTE_MAX_PLAYERS} игроков, {cfg.ROULETTE_JOIN_TIMEOUT} сек на сбор.\n"
        f"Проигравший получает мут на {cfg.ROULETTE_MUTE_MINUTES} мин.\n"
        "Соло: 1/6 шанс мута.",
        parse_mode="HTML",
    )
    await callback.answer()
