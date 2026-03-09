import random
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message,
)
from app.db import repositories as repo
from app.utils.helpers import today_str, progress_bar, safe_edit_text
from app.texts import (
    HOME_ACTIONS, HOME_TEXTS,
    HOME_ORDER_MIN_COMMENT, HOME_ORDER_MAX_COMMENT,
    HOME_ALREADY_DONE, HOME_ALL_DONE, GAMES_DISABLED,
)

router = Router()


def _score_tier(n: int) -> str:
    if n <= 9:
        return "low"
    elif n <= 14:
        return "mid"
    return "high"


def _home_kb(done_today: set[str]) -> InlineKeyboardMarkup:
    items = list(HOME_ACTIONS.items())
    rows = []
    for i in range(0, len(items), 2):
        row = []
        for key, (emoji, label) in items[i:i + 2]:
            if key in done_today:
                row.append(InlineKeyboardButton(
                    text=f"✅ {label}", callback_data=f"home:done:{key}",
                ))
            else:
                row.append(InlineKeyboardButton(
                    text=f"{emoji} {label}", callback_data=f"home:{key}",
                ))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:games")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _order_state(order: int) -> str:
    if order <= 0:
        return HOME_ORDER_MIN_COMMENT
    if order >= 90:
        return HOME_ORDER_MAX_COMMENT
    return ""


def _build_status(order: int, done_today: set[str]) -> str:
    bar = progress_bar(order)
    state = _order_state(order)
    not_done = [
        f"{HOME_ACTIONS[k][0]} {HOME_ACTIONS[k][1]}"
        for k in HOME_ACTIONS if k not in done_today
    ]
    text = f"🧹 <b>Порядок дома</b>\n\n{bar}{state}"
    if not not_done:
        text += f"\n\n{HOME_ALL_DONE}"
    else:
        text += f"\n\n💡 Ещё можно: {', '.join(not_done)}"
    return text


@router.callback_query(F.data == "game:home")
async def cb_home(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await callback.answer(GAMES_DISABLED, show_alert=True)
        return

    order = await repo.get_home_order(chat_id)
    done_today = await repo.get_home_actions_today(chat_id, user_id, today_str())
    text = _build_status(order, done_today)
    await safe_edit_text(callback.message, text, reply_markup=_home_kb(done_today), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("home:done:"))
async def cb_home_already_done(callback: CallbackQuery):
    key = callback.data[10:]
    action_data = HOME_ACTIONS.get(key)
    if not action_data:
        await callback.answer()
        return

    emoji, label = action_data
    not_done = [
        f"{HOME_ACTIONS[k][0]} {HOME_ACTIONS[k][1]}"
        for k in HOME_ACTIONS if k != key
    ]
    suggestion = random.choice(not_done) if not_done else "отдохнуть"
    await callback.answer(
        HOME_ALREADY_DONE.format(suggestion=suggestion),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("home:") & ~F.data.startswith("home:done:"))
async def cb_home_action(callback: CallbackQuery):
    action = callback.data[5:]
    if action not in HOME_ACTIONS:
        await callback.answer()
        return

    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    today = today_str()

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await callback.answer(GAMES_DISABLED, show_alert=True)
        return

    done_today = await repo.get_home_actions_today(chat_id, user_id, today)
    if action in done_today:
        not_done = [
            f"{HOME_ACTIONS[k][0]} {HOME_ACTIONS[k][1]}"
            for k in HOME_ACTIONS if k not in done_today
        ]
        suggestion = random.choice(not_done) if not_done else "отдохнуть"
        await callback.answer(HOME_ALREADY_DONE.format(suggestion=suggestion), show_alert=True)
        return

    n = random.randint(5, 20)
    tier = _score_tier(n)
    result_text = random.choice(HOME_TEXTS[action][tier])

    new_order = await repo.update_home_order(chat_id, n)
    await repo.add_home_action(chat_id, user_id, action, today)
    done_today.add(action)

    emoji, label = HOME_ACTIONS[action]
    header = f"{emoji} {result_text}\n<b>+{n} к порядку</b>\n\n"
    text = header + _build_status(new_order, done_today)
    await safe_edit_text(callback.message, text, reply_markup=_home_kb(done_today), parse_mode="HTML")
    await callback.answer()


@router.message(Command("home"))
async def cmd_home(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer(GAMES_DISABLED)
        return

    order = await repo.get_home_order(chat_id)
    done_today = await repo.get_home_actions_today(chat_id, user_id, today_str())
    text = _build_status(order, done_today)
    await message.answer(text, reply_markup=_home_kb(done_today), parse_mode="HTML")
