import random
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from app.db import repositories as repo
from app.config import settings as cfg
from app.utils.helpers import today_str, progress_bar, safe_edit_text
from app.texts import (
    CAT_NEUTRAL, CAT_NEGATIVE, CAT_EASTER_EGG,
    GAMES_DISABLED,
    CAT_FEED_DONE, CAT_PET_DONE, CAT_PLAY_DONE,
    CAT_FEED_COOLDOWN, CAT_PET_COOLDOWN, CAT_PLAY_COOLDOWN,
    CAT_LOW_AFFINITY_EVENTS,
)

router = Router()

# Track last bot message per user to edit instead of sending new (command path)
_last_cat_msg: dict[tuple[int, int], int] = {}


def _affinity_bar(affinity: int) -> str:
    """Visual bar for affinity level."""
    if affinity >= 80:
        label = "обожает тебя"
    elif affinity >= 55:
        label = "доверяет тебе"
    elif affinity >= 30:
        label = "привыкает"
    elif affinity >= 19:
        label = "настороженно смотрит"
    else:
        label = "шипит и прячется"
    return f"{progress_bar(affinity)} ({label})"


async def _check_games_enabled(chat_id: int) -> bool:
    s = await repo.get_settings(chat_id)
    return bool(s.get("games_enabled"))


async def _build_cat_response(chat_id: int, user_id: int, bot: Bot, action: str) -> str:
    """Compute cat action result, update DB, return text to display."""
    if not await _check_games_enabled(chat_id):
        return GAMES_DISABLED

    cat = await repo.get_cat(chat_id, user_id)
    today = today_str()
    affinity = cat.get("affinity", 25) or 25
    actions_today = cat.get("actions_today", 0) or 0

    cooldown_field = {
        "feed": "last_feed_date",
        "pet": "last_pet_date",
        "play": "last_played_date",
    }[action]

    if cat.get(cooldown_field) == today:
        return {"feed": CAT_FEED_COOLDOWN, "pet": CAT_PET_COOLDOWN, "play": CAT_PLAY_COOLDOWN}[action]

    if cat["last_play_date"] != today:
        actions_today = 0

    actions_today += 1

    # Easter egg check (very rare)
    if random.random() < cfg.CAT_CACTUS_EASTER_EGG_CHANCE:
        cactus = await repo.get_cactus(chat_id, user_id)
        new_height = max(0, cactus["height_cm"] - 3)
        await repo.update_cactus(chat_id, user_id, new_height, today)
        new_mood = cat["mood_score"] - 5
        new_affinity = max(0, affinity - 5)
        await repo.update_cat(chat_id, user_id, new_mood, today,
                              affinity=new_affinity, action_field=cooldown_field,
                              actions_today=actions_today)
        await repo.update_home_order(chat_id, -10)
        return CAT_EASTER_EGG

    # Low affinity negative events (<19%)
    if affinity < 19 and random.random() < 0.35:
        event = random.choice(CAT_LOW_AFFINITY_EVENTS)
        new_mood = cat["mood_score"] - 2

        if "кактус" in event.lower():
            await repo.reset_cactus(chat_id, user_id)

        delta = random.randint(2, 5)
        new_order = await repo.update_home_order(chat_id, -delta)
        await repo.update_cat(chat_id, user_id, new_mood, today,
                              affinity=affinity, action_field=cooldown_field,
                              actions_today=actions_today)
        text = f"{event}\n🏠 Порядок: -{delta} ({progress_bar(new_order)})"
        text += f"\n❤️ Привязанность: {_affinity_bar(affinity)}"
        return text

    # Affinity bonus: higher affinity = better outcomes
    affinity_bonus = affinity / 100
    positive_chance = cfg.CAT_POSITIVE_CHANCE + (affinity_bonus * 0.15)
    negative_chance = max(0.05, cfg.CAT_NEGATIVE_CHANCE - (affinity_bonus * 0.15))

    affinity_gain = {"feed": 2, "pet": 3, "play": 2}[action]
    new_affinity = min(100, affinity + affinity_gain)

    action_done_texts = {"feed": CAT_FEED_DONE, "pet": CAT_PET_DONE, "play": CAT_PLAY_DONE}[action]

    roll = random.random()
    if roll < positive_chance:
        new_mood = cat["mood_score"] + 2
        await repo.update_cat(chat_id, user_id, new_mood, today,
                              affinity=new_affinity, action_field=cooldown_field,
                              actions_today=actions_today)
        text = f"🐈 {random.choice(action_done_texts)}"
        text += f"\n😺 +2 настроения"
    elif roll < positive_chance + cfg.CAT_NEUTRAL_CHANCE:
        await repo.update_cat(chat_id, user_id, cat["mood_score"], today,
                              affinity=new_affinity, action_field=cooldown_field,
                              actions_today=actions_today)
        text = random.choice(CAT_NEUTRAL)
    else:
        delta = random.randint(1, 3)
        new_mood = cat["mood_score"] - 1
        new_affinity = max(0, affinity + 1)
        await repo.update_cat(chat_id, user_id, new_mood, today,
                              affinity=new_affinity, action_field=cooldown_field,
                              actions_today=actions_today)
        new_order = await repo.update_home_order(chat_id, -delta)
        text = random.choice(CAT_NEGATIVE)
        text += f"\n🏠 Порядок: -{delta} ({progress_bar(new_order)})"

    if actions_today >= 3:
        text += f"\n❤️ Привязанность: {_affinity_bar(new_affinity)}"

    return text


async def _send_cat(message: Message, bot: Bot, user_id: int, action: str):
    """Command path: delete previous message, send new."""
    chat_id = message.chat.id
    text = await _build_cat_response(chat_id, user_id, bot, action)

    key = (chat_id, user_id)
    prev_id = _last_cat_msg.get(key)
    if prev_id:
        try:
            await bot.delete_message(chat_id, prev_id)
        except Exception:
            pass
    sent = await message.answer(text)
    _last_cat_msg[key] = sent.message_id


async def _edit_cat(callback: CallbackQuery, bot: Bot, action: str):
    """Callback path: edit the callback message, use correct user_id."""
    text = await _build_cat_response(
        callback.message.chat.id, callback.from_user.id, bot, action,
    )
    await safe_edit_text(callback.message, text, reply_markup=None)
    await callback.answer()


# ── Commands ──────────────────────────────────────────────────────────

@router.message(Command("cat"))
async def cmd_cat(message: Message, bot: Bot):
    await _send_cat(message, bot, message.from_user.id, "feed")


@router.message(Command("cat_pet"))
async def cmd_cat_pet(message: Message, bot: Bot):
    await _send_cat(message, bot, message.from_user.id, "pet")


@router.message(Command("cat_play"))
async def cmd_cat_play(message: Message, bot: Bot):
    await _send_cat(message, bot, message.from_user.id, "play")


# ── Callbacks ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "game:cat")
async def cb_cat(callback: CallbackQuery, bot: Bot):
    await _edit_cat(callback, bot, "feed")


@router.callback_query(F.data == "game:cat_pet")
async def cb_cat_pet(callback: CallbackQuery, bot: Bot):
    await _edit_cat(callback, bot, "pet")


@router.callback_query(F.data == "game:cat_play")
async def cb_cat_play(callback: CallbackQuery, bot: Bot):
    await _edit_cat(callback, bot, "play")


