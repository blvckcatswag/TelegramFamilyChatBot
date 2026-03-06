import logging

from aiogram import Router
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


@router.message(FeedbackForm.waiting_text)
async def process_feedback(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Только текст, пожалуйста.")
        return

    text = message.text.strip()
    if len(text) > 2000:
        await message.answer(f"❌ Слишком длинно ({len(text)} символов). Максимум — 2000.")
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
        from aiogram import Bot
        bot: Bot = message.bot
        await bot.send_message(
            cfg.SUPERADMIN_ID,
            f"📣 <b>Фидбек от пользователя</b>\n\n"
            f"Кто: {user_info} ({user.id})\n"
            f"Откуда: {chat_info}\n\n"
            f"<blockquote>{text}</blockquote>",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Не удалось отправить фидбек суперадмину")

    await message.answer(
        "✅ Спасибо! Сообщение отправлено разработчику.",
        reply_markup=kb_start(),
    )
