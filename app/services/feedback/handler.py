import logging
import math
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

from app.config import settings as cfg
from app.db import repositories as repo
from app.utils.reply_keyboards import kb_start

router = Router()
logger = logging.getLogger(__name__)

PAGE_SIZE = 5

CATEGORIES = {
    "bug":       ("🐛", "Баг"),
    "idea":      ("💡", "Идея"),
    "complaint": ("😤", "Жалоба"),
}


class FeedbackForm(StatesGroup):
    waiting_content = State()


def _category_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🐛 Баг", callback_data="feedback:cat:bug"),
        InlineKeyboardButton(text="💡 Идея", callback_data="feedback:cat:idea"),
        InlineKeyboardButton(text="😤 Жалоба", callback_data="feedback:cat:complaint"),
    ]])


def _backlog_kb(items: list[dict], page: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        icon, label = CATEGORIES.get(item["category"], ("📣", item["category"]))
        who = f"@{item['username']}" if item["username"] else f"id{item['user_id']}"
        preview = (item["text"] or "[медиа]")[:50]
        rows.append([InlineKeyboardButton(
            text=f"{icon} #{item['id']} {who}: {preview}",
            callback_data="backlog:noop",
        )])
        rows.append([InlineKeyboardButton(
            text="✅ Закрыть",
            callback_data=f"backlog:close:{item['id']}",
        )])

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"backlog:page:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="backlog:noop"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"backlog:page:{page + 1}"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def cmd_feedback(message: Message, state: FSMContext) -> None:
    await message.answer(
        "📣 <b>Обратная связь</b>\n\nВыбери тип:",
        reply_markup=_category_kb(),
        parse_mode="HTML",
    )


@router.message(Command("feedback"))
async def cmd_feedback_command(message: Message, state: FSMContext) -> None:
    await cmd_feedback(message, state)


@router.callback_query(F.data.startswith("feedback:cat:"))
async def cb_pick_category(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[2]
    if cat not in CATEGORIES:
        await callback.answer("Неизвестная категория.", show_alert=True)
        return

    icon, label = CATEGORIES[cat]
    await state.set_state(FeedbackForm.waiting_content)
    await state.update_data(category=cat)

    await callback.message.edit_text(
        f"📣 <b>{icon} {label}</b>\n\n"
        "Отправь сообщение — текст, голосовое, фото, кружочек, что угодно.\n"
        "Для отмены: /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(FeedbackForm.waiting_content)
async def process_feedback(message: Message, state: FSMContext) -> None:
    has_content = bool(
        message.text or message.photo or message.voice or
        message.video or message.video_note or message.audio or
        message.document or message.sticker
    )
    if not has_content:
        await message.answer("❌ Отправь текст, фото, голосовое или кружочек.")
        return

    if message.text and len(message.text) > 2000:
        await message.answer(f"❌ Слишком длинный текст ({len(message.text)} символов). Максимум — 2000.")
        return

    data = await state.get_data()
    category = data.get("category", "bug")
    await state.clear()

    user = message.from_user
    chat = message.chat
    icon, label = CATEGORIES[category]
    chat_info = f"{chat.title} ({chat.id})" if chat.title else f"лс ({chat.id})"
    user_info = f"@{user.username}" if user.username else user.first_name

    # Сохраняем в БД
    text_to_save = message.text or message.caption or None
    try:
        await repo.create_feedback(user.id, chat.id, user.username, category, text_to_save)
    except Exception:
        logger.exception("Не удалось сохранить фидбек в БД")

    # Уведомляем суперадмина
    if cfg.SUPERADMIN_ID:
        try:
            await message.bot.send_message(
                cfg.SUPERADMIN_ID,
                f"{icon} <b>{label}</b>\n\n"
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


# ── Ответ суперадмина пользователю ──────────────────────────────────

@router.message(
    F.chat.type == "private",
    F.reply_to_message,
    F.reply_to_message.text.regexp(r"Кто:.*?\(\d+\)"),
)
async def superadmin_reply_to_feedback(message: Message) -> None:
    if message.from_user.id != cfg.SUPERADMIN_ID:
        return
    if not message.text:
        return

    original = message.reply_to_message.text
    user_match = re.search(r"Кто:.*?\((\d+)\)", original)
    chat_match = re.search(r"Откуда:.*?\((-?\d+)\)", original)
    if not user_match or not chat_match:
        await message.answer("Не удалось распознать получателя.")
        return

    target_user_id = int(user_match.group(1))
    target_chat_id = int(chat_match.group(1))
    reply_text = f"💬 <b>Ответ разработчика:</b>\n\n{message.text}"

    sent = False
    try:
        await message.bot.send_message(target_user_id, reply_text, parse_mode="HTML")
        sent = True
        await message.answer("✅ Ответ отправлен пользователю в лс.")
    except Exception:
        pass

    if not sent:
        try:
            await message.bot.send_message(target_chat_id, reply_text, parse_mode="HTML")
            sent = True
            await message.answer("✅ Ответ отправлен в чат (лс недоступно).")
        except Exception:
            pass

    if not sent:
        await message.answer("❌ Не удалось доставить ответ.")


# ── Беклог (только суперадмин) ──────────────────────────────────────

async def _show_backlog(target: Message | CallbackQuery, page: int = 0) -> None:
    total = await repo.count_open_feedback()
    if total == 0:
        text = "✅ Беклог пуст — открытых обращений нет."
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text)
        else:
            await target.answer(text)
        return

    items = await repo.get_open_feedback(limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    kb = _backlog_kb(items, page, total)
    text = f"📋 <b>Беклог</b> — открытых: {total}"

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("backlog"))
async def cmd_backlog(message: Message) -> None:
    if message.from_user.id != cfg.SUPERADMIN_ID:
        return
    await _show_backlog(message)


@router.callback_query(F.data.startswith("backlog:page:"))
async def cb_backlog_page(callback: CallbackQuery) -> None:
    if callback.from_user.id != cfg.SUPERADMIN_ID:
        await callback.answer()
        return
    page = int(callback.data.split(":")[2])
    await _show_backlog(callback, page)


@router.callback_query(F.data.startswith("backlog:close:"))
async def cb_backlog_close(callback: CallbackQuery) -> None:
    if callback.from_user.id != cfg.SUPERADMIN_ID:
        await callback.answer()
        return
    feedback_id = int(callback.data.split(":")[2])
    await repo.close_feedback(feedback_id)
    await callback.answer("✅ Закрыто")
    # Обновляем список с той же страницы
    await _show_backlog(callback, page=0)


@router.callback_query(F.data == "backlog:noop")
async def cb_backlog_noop(callback: CallbackQuery) -> None:
    await callback.answer()
