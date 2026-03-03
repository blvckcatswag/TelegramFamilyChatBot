from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from app.db import repositories as repo
from app.config import settings as cfg
from app.utils.helpers import parse_date, format_birthday_date

router = Router()


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
    birthdays = await repo.get_birthdays(message.chat.id)
    if not birthdays:
        await message.answer("🎂 Нет дней рождения.")
        return

    lines = ["🎂 <b>Дни рождения</b>\n"]
    for b in birthdays:
        lines.append(f"🎂 {b['name']} — {format_birthday_date(b['date'])}")

    await message.answer("\n".join(lines), parse_mode="HTML")
