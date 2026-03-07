import random
from datetime import timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatPermissions
from app.db import repositories as repo
from app.config import settings as cfg
from app.utils.helpers import today_str, now_kyiv
from app.texts import (
    CACTUS_POSITIVE, CACTUS_NEGATIVE, GAMES_DISABLED,
    CACTUS_OVERWATER, CACTUS_DEATH,
)

router = Router()

# Overwater chance by watering number today (0-indexed: 0=first, 1=second, ...)
# First watering is always safe, then risk grows
OVERWATER_CHANCES = [0.0, 0.10, 0.30, 0.60, 0.85, 1.0]

# Cactus growth stages
STAGES = [
    (0, "🌱", "Семечко"),
    (5, "🌿", "Росток"),
    (15, "🌵", "Маленький кактус"),
    (30, "🏜️🌵", "Взрослый кактус"),
    (50, "🌸🌵", "Цветущий кактус"),
    (100, "👑🌵", "Легендарный кактус"),
]


def _get_stage(height: int) -> tuple[str, str]:
    """Return (emoji, name) for cactus height."""
    result = STAGES[0]
    for threshold, emoji, name in STAGES:
        if height >= threshold:
            result = (emoji, name)
    return result


async def can_mute_user(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status not in ("creator", "administrator")
    except Exception:
        return False


async def play_cactus(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer(GAMES_DISABLED)
        return

    cactus = await repo.get_cactus(chat_id, user_id)
    today = today_str()

    # Reset daily counter if new day
    waters_today = cactus.get("waters_today", 0) or 0
    if cactus["last_play_date"] != today:
        waters_today = 0

    # Check overwater risk
    chance_idx = min(waters_today, len(OVERWATER_CHANCES) - 1)
    overwater_chance = OVERWATER_CHANCES[chance_idx]

    if random.random() < overwater_chance:
        # OVERWATERED — cactus dies!
        old_height = cactus["height_cm"]
        await repo.reset_cactus(chat_id, user_id)
        death_text = random.choice(CACTUS_DEATH).format(height=old_height)
        await message.answer(death_text)
        return

    waters_today += 1

    roll = random.random()
    if roll < cfg.CACTUS_NEGATIVE_CHANCE:
        # Negative event (prick)
        new_height = max(0, cactus["height_cm"] - 1)
        await repo.update_cactus(chat_id, user_id, new_height, today, waters_today)

        neg_text = random.choice(CACTUS_NEGATIVE)

        if await can_mute_user(bot, chat_id, user_id):
            try:
                mute_until = now_kyiv() + timedelta(minutes=cfg.CACTUS_MUTE_MINUTES)
                await bot.restrict_chat_member(
                    chat_id, user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=mute_until,
                )
                await repo.log_mute(chat_id, user_id, "cactus", mute_until.isoformat())
                neg_text += f"\n🔇 Мут на {cfg.CACTUS_MUTE_MINUTES} минут!"
            except Exception:
                neg_text += f"\n📉 Штраф: -1 см (= {new_height} см)"
        else:
            neg_text += f"\n📉 Штраф: -1 см (= {new_height} см)"

        await message.answer(neg_text)
    else:
        # Success
        new_height = cactus["height_cm"] + 1
        await repo.update_cactus(chat_id, user_id, new_height, today, waters_today)

        stage_emoji, stage_name = _get_stage(new_height)
        pos_text = random.choice(CACTUS_POSITIVE)
        pos_text += f"\n{stage_emoji} {stage_name} | {new_height} см"

        # Overwater warning
        next_chance_idx = min(waters_today, len(OVERWATER_CHANCES) - 1)
        next_chance = OVERWATER_CHANCES[next_chance_idx]
        if next_chance > 0:
            warning = random.choice(CACTUS_OVERWATER)
            pos_text += f"\n\n⚠️ {warning} (шанс перелива: {int(next_chance * 100)}%)"

        await message.answer(pos_text)


@router.message(Command("cactus"))
async def cmd_cactus(message: Message, bot: Bot):
    await play_cactus(message, bot)


@router.callback_query(F.data == "game:cactus")
async def cb_cactus(callback: CallbackQuery, bot: Bot):
    await play_cactus(callback.message, bot)
    await callback.answer()
