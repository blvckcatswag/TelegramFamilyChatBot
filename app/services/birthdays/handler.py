from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from app.db import repositories as repo
from app.config import settings as cfg
from app.utils.helpers import parse_date, format_birthday_date, safe_edit_text


def _is_valid_name(name: str) -> bool:
    return bool(name) and len(name) <= 50 and '\n' not in name and '\r' not in name

router = Router()


class BirthdayForm(StatesGroup):
    waiting_name = State()
    waiting_date = State()


@router.message(Command("birthday_add"))
async def cmd_birthday_add(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    role = await repo.get_user_role(user_id, chat_id)
    if role != "owner" and user_id != cfg.SUPERADMIN_ID:
        await message.answer("⛔ Только для OWNER!")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "🎂 Использование: /birthday_add Имя дд.мм\n"
            "Пример: /birthday_add Мама 25.03"
        )
        return

    name = args[1]
    date_str = args[2]

    if not _is_valid_name(name):
        await message.answer("❌ Некорректное имя (макс. 50 символов).")
        return

    d = parse_date(date_str)

    if not d:
        await message.answer("❌ Неверный формат даты. Используй дд.мм")
        return

    # Store as MM-DD for easy sorting
    bdate = f"{d.month:02d}-{d.day:02d}"
    await repo.add_birthday(chat_id, name, bdate)
    await message.answer(
        f"✅ День рождения добавлен!\n"
        f"🎂 {name} — {format_birthday_date(bdate)}"
    )


@router.message(Command("birthdays"))
async def cmd_birthdays(message: Message):
    from app.bot.keyboards import birthdays_menu_kb
    role = await repo.get_user_role(message.from_user.id, message.chat.id)
    is_owner = role == "owner" or message.from_user.id == cfg.SUPERADMIN_ID
    birthdays = await repo.get_birthdays(message.chat.id)
    if not birthdays:
        await message.answer("🎂 Нет дней рождения.", reply_markup=birthdays_menu_kb(is_owner))
        return
    lines = ["🎂 <b>Дни рождения</b>\n"]
    for b in birthdays:
        lines.append(f"🎂 {b['name']} — {format_birthday_date(b['date'])}")
    await message.answer("\n".join(lines), reply_markup=birthdays_menu_kb(is_owner), parse_mode="HTML")


# ──────────────────── Menu callbacks ────────────────────

@router.callback_query(F.data == "menu:birthdays")
async def cb_menu_birthdays(callback: CallbackQuery):
    from app.bot.keyboards import birthdays_menu_kb
    role = await repo.get_user_role(callback.from_user.id, callback.message.chat.id)
    is_owner = role == "owner" or callback.from_user.id == cfg.SUPERADMIN_ID
    birthdays = await repo.get_birthdays(callback.message.chat.id)
    if not birthdays:
        await safe_edit_text(callback.message, "🎂 Нет дней рождения.", reply_markup=birthdays_menu_kb(is_owner))
    else:
        lines = ["🎂 <b>Дни рождения</b>\n"]
        for b in birthdays:
            lines.append(f"🎂 {b['name']} — {format_birthday_date(b['date'])}")
        await safe_edit_text(callback.message, "\n".join(lines), reply_markup=birthdays_menu_kb(is_owner), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "birthday:list")
async def cb_birthday_list(callback: CallbackQuery):
    from app.bot.keyboards import birthdays_menu_kb, birthday_delete_kb
    role = await repo.get_user_role(callback.from_user.id, callback.message.chat.id)
    is_owner = role == "owner" or callback.from_user.id == cfg.SUPERADMIN_ID
    birthdays = await repo.get_birthdays(callback.message.chat.id)
    if not birthdays:
        await safe_edit_text(callback.message, "🎂 Нет дней рождения.", reply_markup=birthdays_menu_kb(is_owner))
    elif is_owner:
        await safe_edit_text(
            callback.message,
            "🎂 <b>Дни рождения</b>\nНажми для удаления:",
            reply_markup=birthday_delete_kb(birthdays), parse_mode="HTML",
        )
    else:
        lines = ["🎂 <b>Дни рождения</b>\n"]
        for b in birthdays:
            lines.append(f"🎂 {b['name']} — {format_birthday_date(b['date'])}")
        await safe_edit_text(callback.message, "\n".join(lines), reply_markup=birthdays_menu_kb(False), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "birthday:add")
async def cb_birthday_add(callback: CallbackQuery, state: FSMContext):
    role = await repo.get_user_role(callback.from_user.id, callback.message.chat.id)
    if role != "owner" and callback.from_user.id != cfg.SUPERADMIN_ID:
        await callback.answer("⛔ Только для OWNER", show_alert=True)
        return
    await state.clear()
    await state.set_state(BirthdayForm.waiting_name)
    await safe_edit_text(
        callback.message,
        "🎂 <b>Добавить день рождения</b>\n\nНапиши имя:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(BirthdayForm.waiting_name)
async def process_birthday_name(message: Message, state: FSMContext):
    name = message.text.strip() if message.text else ""
    if not _is_valid_name(name):
        await message.answer("❌ Некорректное имя (макс. 50 символов).")
        return
    await state.update_data(name=name)
    await state.set_state(BirthdayForm.waiting_date)
    await message.answer(
        f"📅 Теперь напиши дату рождения для <b>{name}</b>:\n\n"
        "Формат: <code>дд.мм</code>\nПример: <code>25.03</code>",
        parse_mode="HTML",
    )


@router.message(BirthdayForm.waiting_date)
async def process_birthday_date(message: Message, state: FSMContext):
    from app.bot.keyboards import birthdays_menu_kb
    data = await state.get_data()
    name = data["name"]
    d = parse_date(message.text.strip() if message.text else "")
    if not d:
        await message.answer("❌ Неверный формат. Используй дд.мм, например: 25.03")
        return
    await state.clear()
    bdate = f"{d.month:02d}-{d.day:02d}"
    await repo.add_birthday(message.chat.id, name, bdate)
    role = await repo.get_user_role(message.from_user.id, message.chat.id)
    is_owner = role == "owner" or message.from_user.id == cfg.SUPERADMIN_ID
    await message.answer(
        f"✅ Добавлен!\n🎂 {name} — {format_birthday_date(bdate)}",
        reply_markup=birthdays_menu_kb(is_owner),
    )


@router.callback_query(F.data.startswith("birthday:del:"))
async def cb_birthday_delete(callback: CallbackQuery):
    from app.bot.keyboards import birthdays_menu_kb, birthday_delete_kb
    role = await repo.get_user_role(callback.from_user.id, callback.message.chat.id)
    if role != "owner" and callback.from_user.id != cfg.SUPERADMIN_ID:
        await callback.answer("⛔ Только для OWNER", show_alert=True)
        return
    birthday_id = int(callback.data.split(":")[2])
    await repo.delete_birthday(birthday_id, callback.message.chat.id)
    birthdays = await repo.get_birthdays(callback.message.chat.id)
    is_owner = True
    if not birthdays:
        await safe_edit_text(callback.message, "🎂 Нет дней рождения.", reply_markup=birthdays_menu_kb(is_owner))
    else:
        await safe_edit_text(
            callback.message,
            "🎂 <b>Дни рождения</b>\nНажми для удаления:",
            reply_markup=birthday_delete_kb(birthdays), parse_mode="HTML",
        )
    await callback.answer("✅ Удалено")
