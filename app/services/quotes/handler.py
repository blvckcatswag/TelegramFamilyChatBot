from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from app.db import repositories as repo
from app.bot.keyboards import quotes_menu_kb, back_to_menu_kb
from app.utils.helpers import mention_user

router = Router()


@router.message(Command("quote"))
async def cmd_quote(message: Message):
    if not message.reply_to_message:
        await message.answer(
            "\U0001f4ac \u0427\u0442\u043e\u0431\u044b \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0446\u0438\u0442\u0430\u0442\u0443, \u043e\u0442\u0432\u0435\u0442\u044c \u043d\u0430 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u043a\u043e\u043c\u0430\u043d\u0434\u043e\u0439 /quote"
        )
        return

    s = await repo.get_settings(message.chat.id)
    if not s.get("quotes_enabled"):
        await message.answer("\U0001f4ac \u0426\u0438\u0442\u0430\u0442\u044b \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u044b.")
        return

    reply = message.reply_to_message
    if not reply.text:
        await message.answer("\u274c \u041c\u043e\u0436\u043d\u043e \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u0442\u044c \u0442\u043e\u043b\u044c\u043a\u043e \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u044b\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f.")
        return

    author_id = reply.from_user.id if reply.from_user else 0
    saved_by_id = message.from_user.id

    quote_id = await repo.save_quote(
        message.chat.id, author_id, saved_by_id,
        reply.text, reply.message_id,
    )

    if quote_id is None:
        await message.answer("\u274c \u041b\u0438\u043c\u0438\u0442 \u0446\u0438\u0442\u0430\u0442 \u0434\u043e\u0441\u0442\u0438\u0433\u043d\u0443\u0442!")
        return

    author_name = reply.from_user.first_name if reply.from_user else "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439"
    await message.answer(
        f"\u2705 \u0426\u0438\u0442\u0430\u0442\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0430!\n"
        f"\U0001f4ac \u00ab{reply.text[:100]}{'...' if len(reply.text) > 100 else ''}\u00bb \u2014 {author_name}"
    )


@router.message(Command("quote_random"))
async def cmd_quote_random(message: Message):
    quote = await repo.get_random_quote(message.chat.id)
    if not quote:
        await message.answer("\U0001f4ac \u041d\u0435\u0442 \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d\u043d\u044b\u0445 \u0446\u0438\u0442\u0430\u0442.")
        return
    author = quote.get("first_name") or quote.get("username") or "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439"
    await message.answer(
        f"\U0001f4ac <i>\u00ab{quote['text']}\u00bb</i>\n\u2014 {author}",
        parse_mode="HTML",
    )


@router.message(Command("quote_last"))
async def cmd_quote_last(message: Message):
    args = message.text.split()
    n = 5
    if len(args) > 1:
        try:
            n = max(1, min(20, int(args[1])))
        except ValueError:
            pass

    quotes = await repo.get_last_quotes(message.chat.id, n)
    if not quotes:
        await message.answer("\U0001f4ac \u041d\u0435\u0442 \u0446\u0438\u0442\u0430\u0442.")
        return

    lines = [f"\U0001f4d6 <b>\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 {len(quotes)} \u0446\u0438\u0442\u0430\u0442</b>\n"]
    for q in quotes:
        author = q.get("first_name") or q.get("username") or "?"
        lines.append(f"\U0001f4ac <i>\u00ab{q['text'][:80]}{'...' if len(q['text']) > 80 else ''}\u00bb</i> \u2014 {author}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ──── Callback handlers ────

@router.callback_query(F.data == "quote:random")
async def cb_quote_random(callback: CallbackQuery):
    quote = await repo.get_random_quote(callback.message.chat.id)
    if not quote:
        await callback.message.edit_text("\U0001f4ac \u041d\u0435\u0442 \u0446\u0438\u0442\u0430\u0442.", reply_markup=quotes_menu_kb())
        await callback.answer()
        return
    author = quote.get("first_name") or quote.get("username") or "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439"
    await callback.message.edit_text(
        f"\U0001f4ac <i>\u00ab{quote['text']}\u00bb</i>\n\u2014 {author}",
        reply_markup=quotes_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "quote:last")
async def cb_quote_last(callback: CallbackQuery):
    quotes = await repo.get_last_quotes(callback.message.chat.id, 5)
    if not quotes:
        await callback.message.edit_text("\U0001f4ac \u041d\u0435\u0442 \u0446\u0438\u0442\u0430\u0442.", reply_markup=quotes_menu_kb())
        await callback.answer()
        return

    lines = ["\U0001f4d6 <b>\u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 5 \u0446\u0438\u0442\u0430\u0442</b>\n"]
    for q in quotes:
        author = q.get("first_name") or q.get("username") or "?"
        lines.append(f"\U0001f4ac <i>\u00ab{q['text'][:80]}\u00bb</i> \u2014 {author}")

    await callback.message.edit_text("\n".join(lines), reply_markup=quotes_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "quote:counts")
async def cb_quote_counts(callback: CallbackQuery):
    counts = await repo.get_quote_counts(callback.message.chat.id)
    if not counts:
        await callback.message.edit_text("\U0001f4ac \u041d\u0435\u0442 \u0446\u0438\u0442\u0430\u0442.", reply_markup=quotes_menu_kb())
        await callback.answer()
        return

    lines = ["\U0001f4ca <b>\u0421\u0447\u0451\u0442\u0447\u0438\u043a \u0446\u0438\u0442\u0430\u0442</b>\n"]
    for i, c in enumerate(counts, 1):
        name = c.get("first_name") or c.get("username") or "?"
        lines.append(f"{i}. {name} \u2014 {c['cnt']} \u0446\u0438\u0442\u0430\u0442")

    await callback.message.edit_text("\n".join(lines), reply_markup=quotes_menu_kb(), parse_mode="HTML")
    await callback.answer()
