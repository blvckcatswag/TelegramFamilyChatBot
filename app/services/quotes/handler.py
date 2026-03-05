from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from app.db import repositories as repo
from app.bot.keyboards import quotes_menu_kb, back_to_menu_kb
from app.utils.helpers import mention_user, safe_edit_text

router = Router()


@router.message(Command("quote"))
async def cmd_quote(message: Message):
    if not message.reply_to_message:
        await message.answer(
            "💬 Чтобы сохранить цитату, ответь на сообщение командой /quote"
        )
        return

    s = await repo.get_settings(message.chat.id)
    if not s.get("quotes_enabled"):
        await message.answer("💬 Цитаты отключены.")
        return

    reply = message.reply_to_message
    if not reply.text:
        await message.answer("❌ Можно сохранять только текстовые сообщения.")
        return

    author_id = reply.from_user.id if reply.from_user else 0
    saved_by_id = message.from_user.id

    quote_id = await repo.save_quote(
        message.chat.id, author_id, saved_by_id,
        reply.text, reply.message_id,
    )

    if quote_id is None:
        await message.answer("❌ Лимит цитат достигнут!")
        return

    author_name = reply.from_user.first_name if reply.from_user else "Неизвестный"
    await message.answer(
        f"✅ Цитата сохранена!\n"
        f"💬 «{reply.text[:100]}{'...' if len(reply.text) > 100 else ''}» — {author_name}"
    )


@router.message(Command("quote_random"))
async def cmd_quote_random(message: Message):
    quote = await repo.get_random_quote(message.chat.id)
    if not quote:
        await message.answer("💬 Нет сохранённых цитат.")
        return
    author = quote.get("first_name") or quote.get("username") or "Неизвестный"
    await message.answer(
        f"💬 <i>«{quote['text']}»</i>\n— {author}",
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
        await message.answer("💬 Нет цитат.")
        return

    lines = [f"📖 <b>Последние {len(quotes)} цитат</b>\n"]
    for q in quotes:
        author = q.get("first_name") or q.get("username") or "?"
        lines.append(f"💬 <i>«{q['text'][:80]}{'...' if len(q['text']) > 80 else ''}»</i> — {author}")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ──── Callback handlers ────

@router.callback_query(F.data == "quote:random")
async def cb_quote_random(callback: CallbackQuery):
    quote = await repo.get_random_quote(callback.message.chat.id)
    if not quote:
        await safe_edit_text(callback.message, "💬 Нет цитат.", reply_markup=quotes_menu_kb())
        await callback.answer()
        return
    author = quote.get("first_name") or quote.get("username") or "Неизвестный"
    await safe_edit_text(
        callback.message,
        f"💬 <i>«{quote['text']}»</i>\n— {author}",
        reply_markup=quotes_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "quote:last")
async def cb_quote_last(callback: CallbackQuery):
    quotes = await repo.get_last_quotes(callback.message.chat.id, 5)
    if not quotes:
        await safe_edit_text(callback.message, "💬 Нет цитат.", reply_markup=quotes_menu_kb())
        await callback.answer()
        return

    lines = ["📖 <b>Последние 5 цитат</b>\n"]
    for q in quotes:
        author = q.get("first_name") or q.get("username") or "?"
        lines.append(f"💬 <i>«{q['text'][:80]}»</i> — {author}")

    await safe_edit_text(callback.message, "\n".join(lines), reply_markup=quotes_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "quote:counts")
async def cb_quote_counts(callback: CallbackQuery):
    counts = await repo.get_quote_counts(callback.message.chat.id)
    if not counts:
        await safe_edit_text(callback.message, "💬 Нет цитат.", reply_markup=quotes_menu_kb())
        await callback.answer()
        return

    lines = ["📊 <b>Счётчик цитат</b>\n"]
    for i, c in enumerate(counts, 1):
        name = c.get("first_name") or c.get("username") or "?"
        lines.append(f"{i}. {name} — {c['cnt']} цитат")

    await safe_edit_text(callback.message, "\n".join(lines), reply_markup=quotes_menu_kb(), parse_mode="HTML")
    await callback.answer()
