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
        await message.answer("\u26d4 \u0422\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f OWNER!")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "\U0001f382 \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /birthday_add \u0418\u043c\u044f \u0434\u0434.\u043c\u043c\n"
            "\u041f\u0440\u0438\u043c\u0435\u0440: /birthday_add \u041c\u0430\u043c\u0430 25.03"
        )
        return

    name = args[1]
    date_str = args[2]
    d = parse_date(date_str)

    if not d:
        await message.answer("\u274c \u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0434\u0430\u0442\u044b. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0434\u0434.\u043c\u043c")
        return

    # Store as MM-DD for easy sorting
    bdate = f"{d.month:02d}-{d.day:02d}"
    await repo.add_birthday(chat_id, name, bdate)
    await message.answer(
        f"\u2705 \u0414\u0435\u043d\u044c \u0440\u043e\u0436\u0434\u0435\u043d\u0438\u044f \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d!\n"
        f"\U0001f382 {name} \u2014 {format_birthday_date(bdate)}"
    )


@router.message(Command("birthdays"))
async def cmd_birthdays(message: Message):
    birthdays = await repo.get_birthdays(message.chat.id)
    if not birthdays:
        await message.answer("\U0001f382 \u041d\u0435\u0442 \u0434\u043d\u0435\u0439 \u0440\u043e\u0436\u0434\u0435\u043d\u0438\u044f.")
        return

    lines = ["\U0001f382 <b>\u0414\u043d\u0438 \u0440\u043e\u0436\u0434\u0435\u043d\u0438\u044f</b>\n"]
    for b in birthdays:
        lines.append(f"\U0001f382 {b['name']} \u2014 {format_birthday_date(b['date'])}")

    await message.answer("\n".join(lines), parse_mode="HTML")
