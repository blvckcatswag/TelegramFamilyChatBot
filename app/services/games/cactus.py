import random
from datetime import timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatPermissions
from app.db import repositories as repo
from app.config import settings as cfg
from app.utils.helpers import today_str, mention_user, now_kyiv
from app.bot.keyboards import back_to_menu_kb

router = Router()

CACTUS_POSITIVE = [
    "🌵 Ты полил кактус! Он подрос на 1 см!",
    "🌵 Кактус рад водичке! +1 см!",
    "🌵 Кактус тянется к солнцу! +1 см!",
    "🌵 Отличный полив! Кактус вырос на 1 см!",
]

CACTUS_NEGATIVE = [
    "🌵💥 Ой! Ты случайно укололся о кактус!",
    "🌵🤕 Кактус отомстил за чрезмерный полив!",
    "🌵⚠️ Кактус не в настроении...",
]


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
        await message.answer("🎮 Игры отключены в этом чате.")
        return

    cactus = await repo.get_cactus(chat_id, user_id)
    today = today_str()

    if cactus["last_play_date"] == today:
        await message.answer("🌵 Ты уже поливал кактус сегодня! Приходи завтра.")
        return

    roll = random.random()

    if roll < cfg.CACTUS_NEGATIVE_CHANCE:
        # Negative event
        new_height = max(0, cactus["height_cm"] - 1)
        await repo.update_cactus(chat_id, user_id, new_height, today)

        neg_text = random.choice(CACTUS_NEGATIVE)

        # Try to mute
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
        await repo.update_cactus(chat_id, user_id, new_height, today)

        pos_text = random.choice(CACTUS_POSITIVE)
        pos_text += f"\n📏 Текущий рост: {new_height} см"
        await message.answer(pos_text)


@router.message(Command("cactus"))
async def cmd_cactus(message: Message, bot: Bot):
    await play_cactus(message, bot)


@router.callback_query(F.data == "game:cactus")
async def cb_cactus(callback: CallbackQuery, bot: Bot):
    await play_cactus(callback.message, bot)
    await callback.answer()
