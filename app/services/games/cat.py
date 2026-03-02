import random
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from app.db import repositories as repo
from app.config import settings as cfg
from app.utils.helpers import today_str, progress_bar
from app.bot.keyboards import back_to_menu_kb

router = Router()

CAT_POSITIVE = [
    "\U0001f408 \u041a\u043e\u0442 \u0434\u043e\u0432\u043e\u043b\u0435\u043d! \u041e\u043d \u043c\u0443\u0440\u043b\u044b\u0447\u0435\u0442 \u0438 \u0443\u0431\u0440\u0430\u043b \u0437\u0430 \u0441\u043e\u0431\u043e\u0439. +1 \u043f\u043e\u0440\u044f\u0434\u043e\u043a!",
    "\U0001f408 \u041a\u043e\u0442 \u0441\u044a\u0435\u043b \u0432\u0441\u0451 \u0438 \u043f\u043e\u043c\u043e\u0433 \u043f\u043e\u043c\u044b\u0442\u044c \u043f\u043e\u043b! +1 \u043f\u043e\u0440\u044f\u0434\u043e\u043a!",
    "\U0001f408 \u041a\u043e\u0442\u0438\u043a \u0441\u0447\u0430\u0441\u0442\u043b\u0438\u0432! \u041e\u043d \u043f\u0440\u0438\u043d\u0451\u0441 \u0442\u0435\u0431\u0435 \u043f\u043e\u0434\u0430\u0440\u043e\u043a. +1 \u043f\u043e\u0440\u044f\u0434\u043e\u043a!",
]

CAT_NEUTRAL = [
    "\U0001f408 \u041a\u043e\u0442 \u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u043b \u0432 \u043e\u043a\u043d\u043e. \u041d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043f\u0440\u043e\u0438\u0437\u043e\u0448\u043b\u043e.",
    "\U0001f408 \u041a\u043e\u0442 \u043f\u043e\u043d\u044e\u0445\u0430\u043b \u0435\u0434\u0443 \u0438 \u0443\u0448\u0451\u043b \u0441\u043f\u0430\u0442\u044c.",
    "\U0001f408 \u041a\u043e\u0442 \u0438\u0433\u043d\u043e\u0440\u0438\u0440\u0443\u0435\u0442 \u0442\u0435\u0431\u044f. \u041a\u0430\u043a \u043e\u0431\u044b\u0447\u043d\u043e.",
]

CAT_NEGATIVE = [
    "\U0001f408 \u041a\u043e\u0442 \u0440\u0430\u0437\u043e\u0437\u043b\u0438\u043b\u0441\u044f \u0438 \u043f\u0435\u0440\u0435\u0432\u0435\u0440\u043d\u0443\u043b \u043c\u0438\u0441\u043a\u0443!",
    "\U0001f408 \u041a\u043e\u0442 \u043f\u043e\u0446\u0430\u0440\u0430\u043f\u0430\u043b \u0434\u0438\u0432\u0430\u043d! \u0411\u0435\u0441\u043f\u043e\u0440\u044f\u0434\u043e\u043a!",
    "\U0001f408 \u041a\u043e\u0442 \u0443\u0441\u0442\u0440\u043e\u0438\u043b \u0431\u0430\u0440\u0434\u0430\u043a \u043d\u0430 \u043a\u0443\u0445\u043d\u0435!",
]

EASTER_EGG = (
    "\U0001f408\U0001f335 <b>\u041f\u0410\u0421\u0425\u0410\u041b\u041a\u0410!</b>\n\n"
    "\u041a\u043e\u0442 \u043e\u043f\u0440\u043e\u043a\u0438\u043d\u0443\u043b \u043a\u0430\u043a\u0442\u0443\u0441! \u0413\u043e\u0440\u0448\u043e\u043a \u0440\u0430\u0437\u0431\u0438\u0442, \u0437\u0435\u043c\u043b\u044f \u043d\u0430 \u043f\u043e\u043b\u0443, "
    "\u043a\u043e\u0442 \u0432 \u0448\u043e\u043a\u0435, \u043a\u0430\u043a\u0442\u0443\u0441 \u043e\u0431\u0438\u0436\u0435\u043d!\n"
    "\U0001f4a5 \u041f\u043e\u0440\u044f\u0434\u043e\u043a \u0434\u043e\u043c\u0430: -10!\n"
    "\U0001f335 \u041a\u0430\u043a\u0442\u0443\u0441: -3 \u0441\u043c!\n"
    "\U0001f408 \u041a\u043e\u0442: -5 \u043e\u0447\u043a\u043e\u0432!"
)


async def play_cat(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer("\U0001f3ae \u0418\u0433\u0440\u044b \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u044b \u0432 \u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435.")
        return

    cat = await repo.get_cat(chat_id, user_id)
    today = today_str()

    if cat["last_play_date"] == today:
        await message.answer("\U0001f408 \u041a\u043e\u0442 \u0443\u0436\u0435 \u043d\u0430\u043a\u043e\u0440\u043c\u043b\u0435\u043d \u0441\u0435\u0433\u043e\u0434\u043d\u044f! \u041f\u0440\u0438\u0445\u043e\u0434\u0438 \u0437\u0430\u0432\u0442\u0440\u0430.")
        return

    # Easter egg check
    roll_easter = random.random()
    if roll_easter < cfg.CAT_CACTUS_EASTER_EGG_CHANCE:
        cactus = await repo.get_cactus(chat_id, user_id)
        new_height = max(0, cactus["height_cm"] - 3)
        await repo.update_cactus(chat_id, user_id, new_height, today)
        new_mood = cat["mood_score"] - 5
        await repo.update_cat(chat_id, user_id, new_mood, today)
        await repo.update_home_order(chat_id, -10)
        await message.answer(EASTER_EGG, parse_mode="HTML")
        return

    roll = random.random()

    if roll < cfg.CAT_POSITIVE_CHANCE:
        # Positive
        new_mood = cat["mood_score"] + 2
        await repo.update_cat(chat_id, user_id, new_mood, today)
        new_order = await repo.update_home_order(chat_id, 1)
        text = random.choice(CAT_POSITIVE)
        text += f"\n\U0001f408 \u041d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u0438\u0435 \u043a\u043e\u0442\u0430: {new_mood}"
    elif roll < cfg.CAT_POSITIVE_CHANCE + cfg.CAT_NEUTRAL_CHANCE:
        # Neutral
        await repo.update_cat(chat_id, user_id, cat["mood_score"], today)
        text = random.choice(CAT_NEUTRAL)
    else:
        # Negative
        delta = random.randint(1, 3)
        new_mood = cat["mood_score"] - 1
        await repo.update_cat(chat_id, user_id, new_mood, today)
        new_order = await repo.update_home_order(chat_id, -delta)
        text = random.choice(CAT_NEGATIVE)
        text += f"\n\U0001f3e0 \u041f\u043e\u0440\u044f\u0434\u043e\u043a: -{delta} ({progress_bar(new_order)})"

    await message.answer(text)


@router.message(Command("cat"))
async def cmd_cat(message: Message, bot: Bot):
    await play_cat(message, bot)


@router.callback_query(F.data == "game:cat")
async def cb_cat(callback: CallbackQuery, bot: Bot):
    await play_cat(callback.message, bot)
    await callback.answer()


@router.message(Command("home"))
async def cmd_home(message: Message):
    chat_id = message.chat.id
    order = await repo.get_home_order(chat_id)
    bar = progress_bar(order)

    extra = ""
    if order == 0:
        extra = "\n\U0001f629 \u041f\u043e\u043b\u043d\u044b\u0439 \u0431\u0435\u0441\u043f\u043e\u0440\u044f\u0434\u043e\u043a! \u041f\u043e\u043c\u043e\u0433\u0438\u0442\u0435!"
    elif order == 100:
        extra = "\n\U0001f389 \u0418\u0434\u0435\u0430\u043b\u044c\u043d\u0430\u044f \u0447\u0438\u0441\u0442\u043e\u0442\u0430!"

    await message.answer(f"\U0001f9f9 <b>\u041f\u043e\u0440\u044f\u0434\u043e\u043a \u0434\u043e\u043c\u0430</b>\n\n{bar}{extra}", parse_mode="HTML")


@router.callback_query(F.data == "game:home")
async def cb_home(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    order = await repo.get_home_order(chat_id)
    bar = progress_bar(order)

    extra = ""
    if order == 0:
        extra = "\n\U0001f629 \u041f\u043e\u043b\u043d\u044b\u0439 \u0431\u0435\u0441\u043f\u043e\u0440\u044f\u0434\u043e\u043a!"
    elif order == 100:
        extra = "\n\U0001f389 \u0418\u0434\u0435\u0430\u043b\u044c\u043d\u0430\u044f \u0447\u0438\u0441\u0442\u043e\u0442\u0430!"

    await callback.message.edit_text(
        f"\U0001f9f9 <b>\u041f\u043e\u0440\u044f\u0434\u043e\u043a \u0434\u043e\u043c\u0430</b>\n\n{bar}{extra}",
        reply_markup=back_to_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()
