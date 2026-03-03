import random
import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from app.db import repositories as repo
from app.config import settings as cfg

router = Router()

TRIGGERS = [
    r"\bясно\b", r"\bну понятно\b", r"\bок\b", r"\bугу\b",
    r"\bпонял\b", r"\bпонятно\b", r"\bладно\b",
    r"\bокей\b", r"\bну ок\b",
]

RESPONSES = [
    "Ясно — это когда ничего не ясно, но уже лень спрашивать 😏",
    "«Ясно» — универсальный ответ на всё, что не понял 🤓",
    "Переводчик: «ясно» = «я тебя не слушал, но продолжай» 🙂",
    "Перевод: «ну понятно» = «ничего не понятно, но очень интересно» 🧐",
    "Ага, ясно. Как в том анекдоте... 👀",
    "«Ок» — самое длинное письмо, которое ты отправишь сегодня 📩",
    "«Понял» — ничего он не понял 😏",
    "Переводчик работает: «угу» = «я в телефоне, не мешай» 📱",
    "Так «ясно» или «ясно-ясно»? Это разные вещи! 🧐",
    "Внимание: зафиксировано очередное «ясно»! Счётчик +1 📈",
]


@router.message(F.text)
async def check_translator_trigger(message: Message):
    if not message.text or message.text.startswith("/"):
        return

    chat_id = message.chat.id
    s = await repo.get_settings(chat_id)
    if not s.get("translator_enabled"):
        return

    text_lower = message.text.lower().strip()
    triggered_word = None

    for trigger in TRIGGERS:
        if re.search(trigger, text_lower):
            triggered_word = re.search(trigger, text_lower).group()
            break

    if not triggered_word:
        return

    # Probability check
    if random.random() > cfg.TRANSLATOR_TRIGGER_CHANCE:
        return

    await repo.log_translator(chat_id, message.from_user.id, triggered_word)
    response = random.choice(RESPONSES)
    await message.reply(response)


@router.message(Command("ясно_топ"))
async def cmd_yasno_top(message: Message):
    top = await repo.get_translator_top(message.chat.id)
    if not top:
        await message.answer("🔎 Никто ещё не попался переводчику!")
        return

    lines = ["🔎 <b>Топ «ясно»</b>\n"]
    for i, t in enumerate(top, 1):
        name = t.get("first_name") or t.get("username") or "?"
        lines.append(f"{i}. {name} — {t['cnt']} раз")

    await message.answer("\n".join(lines), parse_mode="HTML")
