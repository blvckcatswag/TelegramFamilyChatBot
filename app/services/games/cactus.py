import random
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatPermissions
from app.db import repositories as repo
from app.config import settings as cfg
from app.utils.helpers import today_str, mention_user
from app.bot.keyboards import back_to_menu_kb

router = Router()

CACTUS_POSITIVE = [
    "\U0001f335 \u0422\u044b \u043f\u043e\u043b\u0438\u043b \u043a\u0430\u043a\u0442\u0443\u0441! \u041e\u043d \u043f\u043e\u0434\u0440\u043e\u0441 \u043d\u0430 1 \u0441\u043c!",
    "\U0001f335 \u041a\u0430\u043a\u0442\u0443\u0441 \u0440\u0430\u0434 \u0432\u043e\u0434\u0438\u0447\u043a\u0435! +1 \u0441\u043c!",
    "\U0001f335 \u041a\u0430\u043a\u0442\u0443\u0441 \u0442\u044f\u043d\u0435\u0442\u0441\u044f \u043a \u0441\u043e\u043b\u043d\u0446\u0443! +1 \u0441\u043c!",
    "\U0001f335 \u041e\u0442\u043b\u0438\u0447\u043d\u044b\u0439 \u043f\u043e\u043b\u0438\u0432! \u041a\u0430\u043a\u0442\u0443\u0441 \u0432\u044b\u0440\u043e\u0441 \u043d\u0430 1 \u0441\u043c!",
]

CACTUS_NEGATIVE = [
    "\U0001f335\U0001f4a5 \u041e\u0439! \u0422\u044b \u0441\u043b\u0443\u0447\u0430\u0439\u043d\u043e \u0443\u043a\u043e\u043b\u043e\u043b\u0441\u044f \u043e \u043a\u0430\u043a\u0442\u0443\u0441!",
    "\U0001f335\U0001f915 \u041a\u0430\u043a\u0442\u0443\u0441 \u043e\u0442\u043e\u043c\u0441\u0442\u0438\u043b \u0437\u0430 \u0447\u0440\u0435\u0437\u043c\u0435\u0440\u043d\u044b\u0439 \u043f\u043e\u043b\u0438\u0432!",
    "\U0001f335\u26a0\ufe0f \u041a\u0430\u043a\u0442\u0443\u0441 \u043d\u0435 \u0432 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u0438\u0438...",
]


async def play_cactus(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer("\U0001f3ae \u0418\u0433\u0440\u044b \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u044b \u0432 \u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435.")
        return

    cactus = await repo.get_cactus(chat_id, user_id)
    today = today_str()

    if cactus["last_play_date"] == today:
        await message.answer("\U0001f335 \u0422\u044b \u0443\u0436\u0435 \u043f\u043e\u043b\u0438\u0432\u0430\u043b \u043a\u0430\u043a\u0442\u0443\u0441 \u0441\u0435\u0433\u043e\u0434\u043d\u044f! \u041f\u0440\u0438\u0445\u043e\u0434\u0438 \u0437\u0430\u0432\u0442\u0440\u0430.")
        return

    roll = random.random()

    if roll < cfg.CACTUS_NEGATIVE_CHANCE:
        # Negative event
        new_height = max(0, cactus["height_cm"] - 1)
        await repo.update_cactus(chat_id, user_id, new_height, today)

        neg_text = random.choice(CACTUS_NEGATIVE)

        # Try to mute
        try:
            mute_until = datetime.utcnow() + timedelta(minutes=cfg.CACTUS_MUTE_MINUTES)
            await bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=mute_until,
            )
            await repo.log_mute(chat_id, user_id, "cactus", mute_until.isoformat())
            neg_text += f"\n\U0001f507 \u041c\u0443\u0442 \u043d\u0430 {cfg.CACTUS_MUTE_MINUTES} \u043c\u0438\u043d\u0443\u0442!"
        except Exception:
            neg_text += f"\n\U0001f4c9 \u0428\u0442\u0440\u0430\u0444: -1 \u0441\u043c (= {new_height} \u0441\u043c)"

        await message.answer(neg_text)
    else:
        # Success
        new_height = cactus["height_cm"] + 1
        await repo.update_cactus(chat_id, user_id, new_height, today)

        pos_text = random.choice(CACTUS_POSITIVE)
        pos_text += f"\n\U0001f4cf \u0422\u0435\u043a\u0443\u0449\u0438\u0439 \u0440\u043e\u0441\u0442: {new_height} \u0441\u043c"
        await message.answer(pos_text)


@router.message(Command("cactus"))
async def cmd_cactus(message: Message, bot: Bot):
    await play_cactus(message, bot)


@router.callback_query(F.data == "game:cactus")
async def cb_cactus(callback: CallbackQuery, bot: Bot):
    await play_cactus(callback.message, bot)
    await callback.answer()
