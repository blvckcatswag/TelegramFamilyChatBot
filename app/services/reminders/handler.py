from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.db import repositories as repo
from app.bot.keyboards import reminder_delete_kb, back_to_menu_kb, reminders_menu_kb
from app.utils.helpers import KYIV_TZ, now_kyiv

router = Router()


class ReminderForm(StatesGroup):
    waiting_text = State()
    waiting_time = State()
    waiting_type = State()


@router.message(Command("remind"))
async def cmd_remind(message: Message, state: FSMContext):
    await state.set_state(ReminderForm.waiting_text)
    await message.answer(
        "📝 <b>Новое напоминание</b>\n\n"
        "Напиши текст напоминания:",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "remind:create")
async def cb_remind_create(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ReminderForm.waiting_text)
    await callback.message.edit_text(
        "📝 <b>Новое напоминание</b>\n\n"
        "Напиши текст напоминания:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ReminderForm.waiting_text)
async def process_reminder_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text, chat_id=message.chat.id, user_id=message.from_user.id)
    await state.set_state(ReminderForm.waiting_time)
    await message.answer(
        "⏰ Когда напомнить?\n\n"
        "Формат: <code>DD.MM.YYYY HH:MM</code>\n"
        "Пример: <code>25.12.2026 09:00</code>\n\n"
        "Или просто время (сегодня): <code>18:30</code>",
        parse_mode="HTML",
    )


@router.message(ReminderForm.waiting_time)
async def process_reminder_time(message: Message, state: FSMContext):
    text = message.text.strip()
    run_at = None

    # Try full datetime
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m %H:%M", "%H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            now = now_kyiv()
            if fmt == "%H:%M":
                run_at = now.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
                if run_at <= now:
                    from datetime import timedelta
                    run_at = run_at + timedelta(days=1)
            elif fmt == "%d.%m %H:%M":
                run_at = parsed.replace(year=now.year, tzinfo=KYIV_TZ)
            else:
                run_at = parsed.replace(tzinfo=KYIV_TZ)
            break
        except ValueError:
            continue

    if not run_at:
        await message.answer("❌ Не понял время. Попробуй формат: DD.MM.YYYY HH:MM")
        return

    # Ensure timezone
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=KYIV_TZ)

    data = await state.get_data()
    await state.clear()

    reminder_id = await repo.create_reminder(
        data["chat_id"], data["user_id"], data["text"], run_at.isoformat()
    )

    if reminder_id is None:
        await message.answer("❌ Лимит напоминаний достигнут!")
        return

    # Schedule it
    from app.scheduler.jobs import schedule_reminder
    await schedule_reminder(reminder_id, data["chat_id"], data["text"], run_at)

    await message.answer(
        f"✅ Напоминание создано!\n"
        f"📝 {data['text']}\n"
        f"⏰ {run_at.strftime('%d.%m.%Y %H:%M')} (Киев)",
        reply_markup=back_to_menu_kb(),
    )


@router.message(Command("reminders"))
async def cmd_reminders(message: Message):
    reminders = await repo.get_active_reminders(message.chat.id)
    if not reminders:
        await message.answer("📋 Нет активных напоминаний.", reply_markup=back_to_menu_kb())
        return
    await message.answer(
        "📋 <b>Активные напоминания</b>\nНажми для удаления:",
        reply_markup=reminder_delete_kb(reminders), parse_mode="HTML",
    )


@router.callback_query(F.data == "remind:list")
async def cb_remind_list(callback: CallbackQuery):
    reminders = await repo.get_active_reminders(callback.message.chat.id)
    if not reminders:
        await callback.message.edit_text(
            "📋 Нет активных напоминаний.",
            reply_markup=reminders_menu_kb(),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "📋 <b>Активные напоминания</b>\nНажми для удаления:",
        reply_markup=reminder_delete_kb(reminders), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remind:del:"))
async def cb_remind_delete(callback: CallbackQuery):
    reminder_id = int(callback.data.split(":")[2])
    chat_id = callback.message.chat.id
    await repo.delete_reminder(reminder_id, chat_id)

    from app.scheduler.jobs import remove_reminder_job
    remove_reminder_job(reminder_id)

    reminders = await repo.get_active_reminders(chat_id)
    if not reminders:
        await callback.message.edit_text(
            "✅ Удалено! Напоминаний больше нет.",
            reply_markup=reminders_menu_kb(),
        )
    else:
        await callback.message.edit_reply_markup(reply_markup=reminder_delete_kb(reminders))
    await callback.answer("✅ Удалено")
