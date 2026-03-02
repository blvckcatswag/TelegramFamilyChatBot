from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from app.db import repositories as repo
from app.config.settings import SUPERADMIN_ID
from app.bot.keyboards import main_menu_kb

router = Router()

WELCOME_MESSAGE = (
    "\U0001f916 <b>Family Chat Bot \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d!</b>\n\n"
    "\u041f\u0440\u0438\u0432\u0435\u0442! \u042f \u0441\u0435\u043c\u0435\u0439\u043d\u044b\u0439 \u0431\u043e\u0442 \u0441 \u0438\u0433\u0440\u0430\u043c\u0438, \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f\u043c\u0438 \u0438 \u043c\u043d\u043e\u0433\u0438\u043c \u0434\u0440\u0443\u0433\u0438\u043c.\n\n"
    "<b>\u0427\u0442\u043e \u044f \u0443\u043c\u0435\u044e:</b>\n"
    "\U0001f3ae \u041c\u0438\u043d\u0438-\u0438\u0433\u0440\u044b: \u043a\u0430\u043a\u0442\u0443\u0441, \u043a\u043e\u0442, \u0434\u0443\u044d\u043b\u0438, \u0440\u0443\u043b\u0435\u0442\u043a\u0430\n"
    "\U0001f4c5 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f\n"
    "\u26c5 \u0423\u0442\u0440\u0435\u043d\u043d\u044f\u044f \u043f\u043e\u0433\u043e\u0434\u0430\n"
    "\U0001f4ac \u0426\u0438\u0442\u0430\u0442\u044b \u0438 \u0448\u0443\u0442\u043a\u0438\n"
    "\U0001f382 \u0414\u043d\u0438 \u0440\u043e\u0436\u0434\u0435\u043d\u0438\u044f\n"
    "\U0001f3c6 \u0415\u0436\u0435\u043c\u0435\u0441\u044f\u0447\u043d\u044b\u0435 \u043d\u0430\u0433\u0440\u0430\u0434\u044b\n\n"
    "\u2757 <b>\u0412\u0430\u0436\u043d\u043e:</b> \u0434\u043b\u044f \u043c\u0443\u0442\u0430 \u0432 \u0438\u0433\u0440\u0430\u0445 \u0432\u044b\u0434\u0430\u0439\u0442\u0435 \u0431\u043e\u0442\u0443 \u043f\u0440\u0430\u0432\u0430 \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430.\n\n"
    "\U0001f449 \u041d\u0430\u0436\u043c\u0438 <b>\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043c\u0435\u043d\u044e</b> \u0438\u043b\u0438 /help \u0434\u043b\u044f \u043f\u043e\u043b\u043d\u043e\u0433\u043e \u0441\u043f\u0438\u0441\u043a\u0430."
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
        await message.answer("\u26d4 \u0422\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f OWNER!")
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("\u041e\u0442\u0432\u0435\u0442\u044c \u043d\u0430 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u043d\u043e\u0432\u043e\u0433\u043e OWNER")
        return

    new_owner = message.reply_to_message.from_user
    await repo.set_user_role(user_id, chat_id, "user")
    await repo.get_or_create_user(new_owner.id, chat_id, new_owner.username, new_owner.first_name)
    await repo.set_user_role(new_owner.id, chat_id, "owner")
    await message.answer(f"\u2705 OWNER \u043f\u0435\u0440\u0435\u0434\u0430\u043d {new_owner.first_name}!")


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
        f"\U0001f4ca <b>SUPERADMIN \u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430</b>\n\n"
        f"\U0001f4ac \u0427\u0430\u0442\u043e\u0432 \u0432\u0441\u0435\u0433\u043e: {chat_count['total']}\n"
        f"\u2705 \u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445: {chat_count['active']}\n"
        f"\U0001f465 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439: {user_count}",
        parse_mode="HTML",
    )


@router.message(Command("admin_broadcast"))
async def cmd_admin_broadcast(message: Message, bot: Bot):
    if not is_superadmin(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /admin_broadcast \u0442\u0435\u043a\u0441\u0442")
        return

    text = args[1]
    chats = await repo.get_all_active_chats()
    sent = 0
    failed = 0

    for chat in chats:
        try:
            await bot.send_message(chat["chat_id"], f"\U0001f4e2 <b>\u041e\u0431\u044a\u044f\u0432\u043b\u0435\u043d\u0438\u0435</b>\n\n{text}", parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await message.answer(f"\u2705 \u041e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e: {sent}, \u041e\u0448\u0438\u0431\u043e\u043a: {failed}")


@router.message(Command("admin_ban"))
async def cmd_admin_ban(message: Message):
    if not is_superadmin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /admin_ban chat_id")
        return

    try:
        target_chat_id = int(args[1])
    except ValueError:
        await message.answer("\u274c \u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 chat_id")
        return

    await repo.set_chat_banned(target_chat_id, True)
    await message.answer(f"\u26d4 \u0427\u0430\u0442 {target_chat_id} \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d.")


@router.message(Command("admin_unban"))
async def cmd_admin_unban(message: Message):
    if not is_superadmin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /admin_unban chat_id")
        return

    try:
        target_chat_id = int(args[1])
    except ValueError:
        await message.answer("\u274c \u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 chat_id")
        return

    await repo.set_chat_banned(target_chat_id, False)
    await message.answer(f"\u2705 \u0427\u0430\u0442 {target_chat_id} \u0440\u0430\u0437\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d.")


@router.message(Command("admin_chat"))
async def cmd_admin_chat(message: Message):
    if not is_superadmin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /admin_chat chat_id")
        return

    try:
        target_chat_id = int(args[1])
    except ValueError:
        await message.answer("\u274c \u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 chat_id")
        return

    from app.db.database import get_db
    db = await get_db()

    chat_row = await db.execute_fetchall("SELECT * FROM Chat WHERE chat_id=?", (target_chat_id,))
    if not chat_row:
        await message.answer("\u274c \u0427\u0430\u0442 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.")
        return

    chat = dict(chat_row[0])
    users = await db.execute_fetchall("SELECT * FROM User WHERE chat_id=?", (target_chat_id,))
    settings = await repo.get_settings(target_chat_id)

    text = (
        f"\U0001f4ac <b>\u0427\u0430\u0442: {chat.get('title', 'N/A')}</b>\n"
        f"ID: {target_chat_id}\n"
        f"\u0410\u043a\u0442\u0438\u0432\u0435\u043d: {'Yes' if chat.get('is_active') else 'No'}\n"
        f"\u0417\u0430\u0431\u0430\u043d\u0435\u043d: {'Yes' if chat.get('is_banned') else 'No'}\n"
        f"\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439: {len(users)}\n"
        f"\u041f\u043e\u0433\u043e\u0434\u0430: {'On' if settings.get('weather_enabled') else 'Off'}\n"
        f"\u0418\u0433\u0440\u044b: {'On' if settings.get('games_enabled') else 'Off'}"
    )
    await message.answer(text, parse_mode="HTML")
