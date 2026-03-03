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
    "🐈 Кот доволен! Он мурлычет и убрал за собой. +1 порядок!",
    "🐈 Кот съел всё и помог помыть пол! +1 порядок!",
    "🐈 Котик счастлив! Он принёс тебе подарок. +1 порядок!",
]

CAT_NEUTRAL = [
    "🐈 Кот посмотрел в окно. Ничего не произошло.",
    "🐈 Кот понюхал еду и ушёл спать.",
    "🐈 Кот игнорирует тебя. Как обычно.",
]

CAT_NEGATIVE = [
    "🐈 Кот разозлился и перевернул миску!",
    "🐈 Кот поцарапал диван! Беспорядок!",
    "🐈 Кот устроил бардак на кухне!",
]

EASTER_EGG = (
    "🐈🌵 <b>ПАСХАЛКА!</b>\n\n"
    "Кот опрокинул кактус! Горшок разбит, земля на полу, "
    "кот в шоке, кактус обижен!\n"
    "💥 Порядок дома: -10!\n"
    "🌵 Кактус: -3 см!\n"
    "🐈 Кот: -5 очков!"
)


async def play_cat(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer("🎮 Игры отключены в этом чате.")
        return

    cat = await repo.get_cat(chat_id, user_id)
    today = today_str()

    if cat["last_play_date"] == today:
        await message.answer("🐈 Кот уже накормлен сегодня! Приходи завтра.")
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
        new_mood = cat["mood_score"] + 2
        await repo.update_cat(chat_id, user_id, new_mood, today)
        new_order = await repo.update_home_order(chat_id, 1)
        text = random.choice(CAT_POSITIVE)
        text += f"\n🐈 Настроение кота: {new_mood}"
    elif roll < cfg.CAT_POSITIVE_CHANCE + cfg.CAT_NEUTRAL_CHANCE:
        await repo.update_cat(chat_id, user_id, cat["mood_score"], today)
        text = random.choice(CAT_NEUTRAL)
    else:
        delta = random.randint(1, 3)
        new_mood = cat["mood_score"] - 1
        await repo.update_cat(chat_id, user_id, new_mood, today)
        new_order = await repo.update_home_order(chat_id, -delta)
        text = random.choice(CAT_NEGATIVE)
        text += f"\n🏠 Порядок: -{delta} ({progress_bar(new_order)})"

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
        extra = "\n😩 Полный беспорядок! Помогите!"
    elif order == 100:
        extra = "\n🎉 Идеальная чистота!"

    await message.answer(f"🧹 <b>Порядок дома</b>\n\n{bar}{extra}", parse_mode="HTML")


@router.callback_query(F.data == "game:home")
async def cb_home(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    order = await repo.get_home_order(chat_id)
    bar = progress_bar(order)

    extra = ""
    if order == 0:
        extra = "\n😩 Полный беспорядок!"
    elif order == 100:
        extra = "\n🎉 Идеальная чистота!"

    await callback.message.edit_text(
        f"🧹 <b>Порядок дома</b>\n\n{bar}{extra}",
        reply_markup=back_to_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()
