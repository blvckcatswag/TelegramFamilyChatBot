from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.db import repositories as repo
from app.bot.keyboards import reminder_delete_kb, back_to_menu_kb, reminders_menu_kb

router = Router()


class ReminderForm(StatesGroup):
    waiting_text = State()
    waiting_time = State()
    waiting_type = State()


@router.message(Command("remind"))
async def cmd_remind(message: Message, state: FSMContext):
    await state.set_state(ReminderForm.waiting_text)
    await message.answer(
        "\U0001f4dd <b>\u041d\u043e\u0432\u043e\u0435 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435</b>\n\n"
        "\u041d\u0430\u043f\u0438\u0448\u0438 \u0442\u0435\u043a\u0441\u0442 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f:",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "remind:create")
async def cb_remind_create(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ReminderForm.waiting_text)
    await callback.message.edit_text(
        "\U0001f4dd <b>\u041d\u043e\u0432\u043e\u0435 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435</b>\n\n"
        "\u041d\u0430\u043f\u0438\u0448\u0438 \u0442\u0435\u043a\u0441\u0442 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ReminderForm.waiting_text)
async def process_reminder_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text, chat_id=message.chat.id, user_id=message.from_user.id)
    await state.set_state(ReminderForm.waiting_time)
    await message.answer(
        "\u23f0 \u041a\u043e\u0433\u0434\u0430 \u043d\u0430\u043f\u043e\u043c\u043d\u0438\u0442\u044c?\n\n"
        "\u0424\u043e\u0440\u043c\u0430\u0442: <code>DD.MM.YYYY HH:MM</code>\n"
        "\u041f\u0440\u0438\u043c\u0435\u0440: <code>25.12.2026 09:00</code>\n\n"
        "\u0418\u043b\u0438 \u043f\u0440\u043e\u0441\u0442\u043e \u0432\u0440\u0435\u043c\u044f (\u0441\u0435\u0433\u043e\u0434\u043d\u044f): <code>18:30</code>",
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
            if fmt == "%H:%M":
                now = datetime.utcnow()
                run_at = now.replace(hour=parsed.hour, minute=parsed.minute, second=0)
                if run_at <= now:
                    run_at = run_at.replace(day=now.day + 1)
            elif fmt == "%d.%m %H:%M":
                run_at = parsed.replace(year=datetime.utcnow().year)
            else:
                run_at = parsed
            break
        except ValueError:
            continue

    if not run_at:
        await message.answer("\u274c \u041d\u0435 \u043f\u043e\u043d\u044f\u043b \u0432\u0440\u0435\u043c\u044f. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439 \u0444\u043e\u0440\u043c\u0430\u0442: DD.MM.YYYY HH:MM")
        return

    data = await state.get_data()
    await state.clear()

    reminder_id = await repo.create_reminder(
        data["chat_id"], data["user_id"], data["text"], run_at.isoformat()
    )

    if reminder_id is None:
        await message.answer("\u274c \u041b\u0438\u043c\u0438\u0442 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0439 \u0434\u043e\u0441\u0442\u0438\u0433\u043d\u0443\u0442!")
        return

    # Schedule it
    from app.scheduler.jobs import schedule_reminder
    await schedule_reminder(reminder_id, data["chat_id"], data["text"], run_at)

    await message.answer(
        f"\u2705 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435 \u0441\u043e\u0437\u0434\u0430\u043d\u043e!\n"
        f"\U0001f4dd {data['text']}\n"
        f"\u23f0 {run_at.strftime('%d.%m.%Y %H:%M')}",
        reply_markup=back_to_menu_kb(),
    )


@router.message(Command("reminders"))
async def cmd_reminders(message: Message):
    reminders = await repo.get_active_reminders(message.chat.id)
    if not reminders:
        await message.answer("\U0001f4cb \u041d\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0439.", reply_markup=back_to_menu_kb())
        return
    await message.answer(
        "\U0001f4cb <b>\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f</b>\n\u041d\u0430\u0436\u043c\u0438 \u0434\u043b\u044f \u0443\u0434\u0430\u043b\u0435\u043d\u0438\u044f:",
        reply_markup=reminder_delete_kb(reminders), parse_mode="HTML",
    )


@router.callback_query(F.data == "remind:list")
async def cb_remind_list(callback: CallbackQuery):
    reminders = await repo.get_active_reminders(callback.message.chat.id)
    if not reminders:
        await callback.message.edit_text(
            "\U0001f4cb \u041d\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0439.",
            reply_markup=reminders_menu_kb(),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "\U0001f4cb <b>\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f</b>\n\u041d\u0430\u0436\u043c\u0438 \u0434\u043b\u044f \u0443\u0434\u0430\u043b\u0435\u043d\u0438\u044f:",
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
            "\u2705 \u0423\u0434\u0430\u043b\u0435\u043d\u043e! \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0439 \u0431\u043e\u043b\u044c\u0448\u0435 \u043d\u0435\u0442.",
            reply_markup=reminders_menu_kb(),
        )
    else:
        await callback.message.edit_reply_markup(reply_markup=reminder_delete_kb(reminders))
    await callback.answer("\u2705 \u0423\u0434\u0430\u043b\u0435\u043d\u043e")
