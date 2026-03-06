import logging
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from app.config import settings as cfg
from app.utils.reply_keyboards import kb_start

router = Router()
logger = logging.getLogger(__name__)


class FeedbackForm(StatesGroup):
    waiting_text = State()


@router.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext):
    await state.set_state(FeedbackForm.waiting_text)
    await message.answer(
        "📣 <b>Обратная связь</b>\n\n"
        "Напиши своё сообщение — баг, идея, жалоба, что угодно.\n"
        "Оно придёт разработчику.\n\n"
        "Для отмены: /cancel",
        parse_mode="HTML",
    )


def _has_content(message: Message) -> bool:
    """Проверяет что в сообщении есть хоть какой-то контент."""
    return bool(
        message.text or message.photo or message.voice or
        message.video or message.video_note or message.audio or
        message.document or message.sticker
    )


@router.message(FeedbackForm.waiting_text)
async def process_feedback(message: Message, state: FSMContext):
    if not _has_content(message):
        await message.answer("❌ Отправь текст, фото, голосовое или кружочек.")
        return

    if message.text and len(message.text) > 2000:
        await message.answer(f"❌ Слишком длинный текст ({len(message.text)} символов). Максимум — 2000.")
        return

    await state.clear()

    if not cfg.SUPERADMIN_ID:
        await message.answer("✅ Спасибо за обратную связь!", reply_markup=kb_start())
        return

    user = message.from_user
    chat = message.chat
    chat_info = f"{chat.title} ({chat.id})" if chat.title else f"лс ({chat.id})"
    user_info = f"@{user.username}" if user.username else user.first_name

    try:
        # Сначала шлём контекст, потом пересылаем само сообщение
        await message.bot.send_message(
            cfg.SUPERADMIN_ID,
            f"📣 <b>Фидбек от пользователя</b>\n\n"
            f"Кто: {user_info} ({user.id})\n"
            f"Откуда: {chat_info}",
            parse_mode="HTML",
        )
        await message.forward(cfg.SUPERADMIN_ID)
    except Exception:
        logger.exception("Не удалось отправить фидбек суперадмину")

    await message.answer(
        "✅ Спасибо! Сообщение отправлено разработчику.",
        reply_markup=kb_start(),
    )


@router.message(
    F.chat.type == "private",
    F.reply_to_message,
    F.reply_to_message.text.regexp(r"📣 Фидбек от пользователя"),
)
async def superadmin_reply_to_feedback(message: Message):
    if message.from_user.id != cfg.SUPERADMIN_ID:
        return
    if not message.text:
        return

    original = message.reply_to_message.text

    user_match = re.search(r"Кто:.*?\((\d+)\)", original)
    chat_match = re.search(r"Откуда:.*?\((-?\d+)\)", original)
    if not user_match or not chat_match:
        await message.answer("Не удалось распознать получателя из сообщения фидбека.")
        return

    target_user_id = int(user_match.group(1))
    target_chat_id = int(chat_match.group(1))
    reply_text = (
        f"💬 <b>Ответ разработчика на твой фидбек:</b>\n\n"
        f"{message.text}"
    )

    sent = False

    # Сначала пробуем в лс пользователю
    try:
        await message.bot.send_message(target_user_id, reply_text, parse_mode="HTML")
        sent = True
        await message.answer("✅ Ответ отправлен пользователю в лс.")
    except Exception:
        pass

    # Если лс недоступно — шлём в чат
    if not sent:
        try:
            await message.bot.send_message(target_chat_id, reply_text, parse_mode="HTML")
            sent = True
            await message.answer("✅ Ответ отправлен в чат (лс недоступно).")
        except Exception:
            pass

    if not sent:
        await message.answer("❌ Не удалось доставить ответ — ни в лс, ни в чат.")
