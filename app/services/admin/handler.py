from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from app.db import repositories as repo
from app.config.settings import SUPERADMIN_ID
from app.bot.keyboards import main_menu_kb

router = Router()

WELCOME_MESSAGE = (
    "🤖 <b>Family Chat Bot добавлен!</b>\n\n"
    "Привет! Я семейный бот с играми, напоминаниями и многим другим.\n\n"
    "<b>Что я умею:</b>\n"
    "🎮 Мини-игры: кактус, кот, дуэли, рулетка\n"
    "📅 Напоминания\n"
    "⛅ Утренняя погода\n"
    "💬 Цитаты и шутки\n"
    "🎂 Дни рождения\n"
    "🏆 Ежемесячные награды\n\n"
    "❗ <b>Важно:</b> для мута в играх выдайте боту права администратора.\n\n"
    "👉 Нажми <b>Открыть меню</b> или /help для полного списка."
)


# ──────────────────── Auto-registration on bot added to chat ────────────────────

@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_bot_added(event: ChatMemberUpdated, bot: Bot):
    chat_id = event.chat.id
    adder_id = event.from_user.id

    # Register chat and set adder as owner
    await repo.get_or_create_chat(chat_id, event.chat.title, adder_id)
    await repo.get_or_create_user(
        adder_id, chat_id, event.from_user.username, event.from_user.first_name, role="owner"
    )
    await repo.set_user_role(adder_id, chat_id, "owner")

    try:
        await bot.send_message(chat_id, WELCOME_MESSAGE, reply_markup=main_menu_kb(), parse_mode="HTML")
    except Exception:
        pass


@router.my_chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def on_bot_removed(event: ChatMemberUpdated):
    await repo.set_chat_active(event.chat.id, False)


# ──────────────────── Transfer ownership ────────────────────

@router.message(Command("transfer_owner"))
async def cmd_transfer_owner(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    role = await repo.get_user_role(user_id, chat_id)
    if role != "owner" and user_id != SUPERADMIN_ID:
        await message.answer("⛔ Только для OWNER!")
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("Ответь на сообщение нового OWNER")
        return

    new_owner = message.reply_to_message.from_user
    await repo.set_user_role(user_id, chat_id, "user")
    await repo.get_or_create_user(new_owner.id, chat_id, new_owner.username, new_owner.first_name)
    await repo.set_user_role(new_owner.id, chat_id, "owner")
    await message.answer(f"✅ OWNER передан {new_owner.first_name}!")


# ──────────────────── SUPERADMIN commands ────────────────────

def is_superadmin(user_id: int) -> bool:
    return user_id == SUPERADMIN_ID


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message):
    if not is_superadmin(message.from_user.id):
        return

    chat_count = await repo.get_chat_count()
    user_count = await repo.get_user_count()

    await message.answer(
        f"📊 <b>SUPERADMIN Статистика</b>\n\n"
        f"💬 Чатов всего: {chat_count['total']}\n"
        f"✅ Активных: {chat_count['active']}\n"
        f"👥 Пользователей: {user_count}",
        parse_mode="HTML",
    )


@router.message(Command("admin_broadcast"))
async def cmd_admin_broadcast(message: Message, bot: Bot):
    if not is_superadmin(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /admin_broadcast текст")
        return

    text = args[1]
    chats = await repo.get_all_active_chats()
    sent = 0
    failed = 0

    for chat in chats:
        try:
            await bot.send_message(chat["chat_id"], f"📢 <b>Объявление</b>\n\n{text}", parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await message.answer(f"✅ Отправлено: {sent}, Ошибок: {failed}")


@router.message(Command("admin_ban"))
async def cmd_admin_ban(message: Message):
    if not is_superadmin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /admin_ban chat_id")
        return

    try:
        target_chat_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный chat_id")
        return

    await repo.set_chat_banned(target_chat_id, True)
    await message.answer(f"⛔ Чат {target_chat_id} заблокирован.")


@router.message(Command("admin_unban"))
async def cmd_admin_unban(message: Message):
    if not is_superadmin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /admin_unban chat_id")
        return

    try:
        target_chat_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный chat_id")
        return

    await repo.set_chat_banned(target_chat_id, False)
    await message.answer(f"✅ Чат {target_chat_id} разблокирован.")


@router.message(Command("admin_chat"))
async def cmd_admin_chat(message: Message):
    if not is_superadmin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /admin_chat chat_id")
        return

    try:
        target_chat_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный chat_id")
        return

    from app.db.database import get_db
    db = await get_db()

    chat_row = await db.execute_fetchall("SELECT * FROM Chat WHERE chat_id=?", (target_chat_id,))
    if not chat_row:
        await message.answer("❌ Чат не найден.")
        return

    chat = dict(chat_row[0])
    users = await db.execute_fetchall("SELECT * FROM User WHERE chat_id=?", (target_chat_id,))
    settings = await repo.get_settings(target_chat_id)

    text = (
        f"💬 <b>Чат: {chat.get('title', 'N/A')}</b>\n"
        f"ID: {target_chat_id}\n"
        f"Активен: {'Yes' if chat.get('is_active') else 'No'}\n"
        f"Забанен: {'Yes' if chat.get('is_banned') else 'No'}\n"
        f"Пользователей: {len(users)}\n"
        f"Погода: {'On' if settings.get('weather_enabled') else 'Off'}\n"
        f"Игры: {'On' if settings.get('games_enabled') else 'Off'}"
    )
    await message.answer(text, parse_mode="HTML")
