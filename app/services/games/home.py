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
    HOME_ORDER_MIN_COMMENT, HOME_ORDER_MAX_COMMENT, HOME_ORDER_FULL_PHRASES,
    HOME_ALREADY_DONE, HOME_ALL_DONE, GAMES_DISABLED,
)

router = Router()

# Last home status message per chat (shared game — track per chat, not per user)
_last_home_msg: dict[int, int] = {}


def _score_tier(n: int) -> str:
    if n <= 9:
        return "low"
    elif n <= 14:
        return "mid"
    return "high"


def _home_inline_kb(done_today: set[str]) -> InlineKeyboardMarkup:
    """Inline buttons for the inline games menu path."""
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


def _build_status(order: int, done_today: set[str]) -> str:
    bar = progress_bar(order)
    if order <= 0:
        state = HOME_ORDER_MIN_COMMENT
    elif order >= 100:
        state = HOME_ORDER_MAX_COMMENT
    else:
        state = ""
    not_done = [
        f"{HOME_ACTIONS[k][0]} {HOME_ACTIONS[k][1]}"
        for k in HOME_ACTIONS if k not in done_today
    ]
    text = f"🧹 <b>Порядок дома</b>\n\n{bar}{state}"
    if order >= 100:
        return text
    if not not_done:
        text += f"\n\n{HOME_ALL_DONE}"
    else:
        text += f"\n\n💡 Ещё можно: {', '.join(not_done)}"
    return text


async def _do_home_action(message: Message, action: str) -> None:
    """Reply keyboard path: process action, edit last home msg or send new."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    today = today_str()

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer(GAMES_DISABLED)
        return

    order = await repo.get_home_order(chat_id)

    if order >= 100:
        phrase = random.choice(HOME_ORDER_FULL_PHRASES)
        await _send_or_edit(chat_id, message, f"🏆 {phrase}")
        return

    done_today = await repo.get_home_actions_today(chat_id, user_id, today)
    if action in done_today:
        not_done = [
            f"{HOME_ACTIONS[k][0]} {HOME_ACTIONS[k][1]}"
            for k in HOME_ACTIONS if k not in done_today
        ]
        if not_done:
            suggestion = random.choice(not_done)
            await message.answer(HOME_ALREADY_DONE.format(suggestion=suggestion))
        else:
            await _send_or_edit(chat_id, message, HOME_ALL_DONE + "\n\n" + _build_status(order, done_today))
        return

    n = random.randint(5, 20)
    tier = _score_tier(n)
    result_text = random.choice(HOME_TEXTS[action][tier])

    new_order = await repo.update_home_order(chat_id, n)
    await repo.add_home_action(chat_id, user_id, action, today)
    done_today.add(action)

    emoji, _ = HOME_ACTIONS[action]
    text = f"{emoji} {result_text}\n<b>+{n} к порядку</b>\n\n" + _build_status(new_order, done_today)
    await _send_or_edit(chat_id, message, text)


async def _send_or_edit(chat_id: int, message: Message, text: str) -> None:
    prev_id = _last_home_msg.get(chat_id)
    if prev_id:
        try:
            await message.bot.edit_message_text(text, chat_id=chat_id, message_id=prev_id, parse_mode="HTML")
            return
        except Exception:
            pass
    sent = await message.answer(text, parse_mode="HTML")
    _last_home_msg[chat_id] = sent.message_id


# ── Inline games menu path ─────────────────────────────────────────────

@router.callback_query(F.data == "game:home")
async def cb_home(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await callback.answer(GAMES_DISABLED, show_alert=True)
        return

    order = await repo.get_home_order(chat_id)
    if order >= 100:
        phrase = random.choice(HOME_ORDER_FULL_PHRASES)
        await safe_edit_text(
            callback.message,
            f"🏆 <b>Порядок дома</b>\n\n{progress_bar(order)}{HOME_ORDER_MAX_COMMENT}\n\n{phrase}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:games")]
            ]),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    done_today = await repo.get_home_actions_today(chat_id, user_id, today_str())
    text = _build_status(order, done_today)
    await safe_edit_text(callback.message, text, reply_markup=_home_inline_kb(done_today), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("home:done:"))
async def cb_home_already_done(callback: CallbackQuery):
    key = callback.data[10:]
    if key not in HOME_ACTIONS:
        await callback.answer()
        return
    not_done = [
        f"{HOME_ACTIONS[k][0]} {HOME_ACTIONS[k][1]}"
        for k in HOME_ACTIONS if k != key
    ]
    suggestion = random.choice(not_done) if not_done else "отдохнуть"
    await callback.answer(HOME_ALREADY_DONE.format(suggestion=suggestion), show_alert=True)


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

    order = await repo.get_home_order(chat_id)
    if order >= 100:
        phrase = random.choice(HOME_ORDER_FULL_PHRASES)
        await callback.answer(phrase, show_alert=True)
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

    emoji, _ = HOME_ACTIONS[action]
    header = f"{emoji} {result_text}\n<b>+{n} к порядку</b>\n\n"
    text = header + _build_status(new_order, done_today)
    await safe_edit_text(callback.message, text, reply_markup=_home_inline_kb(done_today), parse_mode="HTML")
    await callback.answer()


# ── Command / reply keyboard entry point ──────────────────────────────

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
    sent = await message.answer(text, parse_mode="HTML")
    _last_home_msg[chat_id] = sent.message_id
