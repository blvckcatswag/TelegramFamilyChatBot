from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram import F
from app.db import repositories as repo
from app.bot.keyboards import back_to_menu_kb
from app.utils.helpers import mention_user, now_kyiv

router = Router()

AWARD_TYPES = {
    "cactus_king": "🌵 Колючий садовод",
    "cat_lover": "🐈 Любимец кота",
    "clean_master": "🧹 Чистюля",
    "duel_master": "⚔️ Дуэлянт",
    "lucky_survivor": "🔫 Везунчик",
    "clown": "🤡 Клоун месяца",
    "beloved": "❤️ Любимчик",
    "quote_star": "💬 Цитата месяца",
    "yasno_master": "🗣️ Мастер ясно",
}


async def calculate_monthly_awards(chat_id: int, year: int, month: int) -> list[dict]:
    from app.db.database import get_db
    db = await get_db()
    awards = []

    month_start = f"{year}-{month:02d}-01"
    if month == 12:
        month_end = f"{year + 1}-01-01"
    else:
        month_end = f"{year}-{month + 1:02d}-01"

    # 1. Cactus king
    rows = await db.fetch(
        'SELECT gc.user_id, gc.height_cm, u.first_name, u.username '
        'FROM GameCactus gc JOIN "User" u ON gc.user_id=u.user_id AND gc.chat_id=u.chat_id '
        'WHERE gc.chat_id=$1 ORDER BY gc.height_cm DESC LIMIT 1',
        chat_id,
    )
    if rows and rows[0]["height_cm"] > 0:
        awards.append({"type": "cactus_king", "user_id": rows[0]["user_id"],
                       "value": f"{rows[0]['height_cm']} см",
                       "name": rows[0]["first_name"] or rows[0]["username"]})

    # 2. Cat lover
    rows = await db.fetch(
        'SELECT gc.user_id, gc.mood_score, u.first_name, u.username '
        'FROM GameCat gc JOIN "User" u ON gc.user_id=u.user_id AND gc.chat_id=u.chat_id '
        'WHERE gc.chat_id=$1 ORDER BY gc.mood_score DESC LIMIT 1',
        chat_id,
    )
    if rows and rows[0]["mood_score"] > 0:
        awards.append({"type": "cat_lover", "user_id": rows[0]["user_id"],
                       "value": f"{rows[0]['mood_score']} очков",
                       "name": rows[0]["first_name"] or rows[0]["username"]})

    # 3. Duel master
    rows = await db.fetch(
        'SELECT winner_id, COUNT(*) as wins, u.first_name, u.username '
        'FROM Duel d JOIN "User" u ON d.winner_id=u.user_id AND d.chat_id=u.chat_id '
        'WHERE d.chat_id=$1 AND d.created_at >= $2 AND d.created_at < $3 AND d.winner_id IS NOT NULL '
        'GROUP BY d.winner_id, u.first_name, u.username ORDER BY wins DESC LIMIT 1',
        chat_id, month_start, month_end,
    )
    if rows:
        awards.append({"type": "duel_master", "user_id": rows[0]["winner_id"],
                       "value": f"{rows[0]['wins']} побед",
                       "name": rows[0]["first_name"] or rows[0]["username"]})

    # 4. Lucky survivor
    rows = await db.fetch(
        "SELECT participants, loser_id FROM Roulette "
        "WHERE chat_id=$1 AND created_at >= $2 AND created_at < $3",
        chat_id, month_start, month_end,
    )
    if rows:
        import json
        survival_count: dict[int, int] = {}
        for r in rows:
            try:
                participants = json.loads(r["participants"])
            except (json.JSONDecodeError, TypeError):
                continue
            for uid in participants:
                if uid != r["loser_id"]:
                    survival_count[uid] = survival_count.get(uid, 0) + 1

        if survival_count:
            best_uid = max(survival_count, key=survival_count.get)
            user_row = await db.fetch(
                'SELECT first_name, username FROM "User" WHERE user_id=$1 AND chat_id=$2',
                best_uid, chat_id,
            )
            name = user_row[0]["first_name"] if user_row else "?"
            awards.append({"type": "lucky_survivor", "user_id": best_uid,
                           "value": f"{survival_count[best_uid]} раз",
                           "name": name})

    # 5. Clown
    clown_top = await repo.get_clown_reactions_top(chat_id)
    if clown_top:
        awards.append({"type": "clown", "user_id": clown_top[0]["to_user_id"],
                       "value": f"{clown_top[0]['cnt']} 🤡",
                       "name": clown_top[0]["first_name"] or clown_top[0]["username"]})

    # 6. Beloved
    received_top = await repo.get_reactions_received_top(chat_id)
    if received_top:
        awards.append({"type": "beloved", "user_id": received_top[0]["to_user_id"],
                       "value": f"{received_top[0]['cnt']} реакций",
                       "name": received_top[0]["first_name"] or received_top[0]["username"]})

    # 7. Quote star
    quote_counts = await repo.get_quote_counts(chat_id)
    if quote_counts:
        awards.append({"type": "quote_star", "user_id": quote_counts[0]["author_id"],
                       "value": f"{quote_counts[0]['cnt']} цитат",
                       "name": quote_counts[0]["first_name"] or quote_counts[0]["username"]})

    # 8. Yasno master
    yasno_top = await repo.get_translator_top(chat_id)
    if yasno_top:
        awards.append({"type": "yasno_master", "user_id": yasno_top[0]["user_id"],
                       "value": f"{yasno_top[0]['cnt']} раз",
                       "name": yasno_top[0]["first_name"] or yasno_top[0]["username"]})

    return awards


async def publish_monthly_awards(bot: Bot, chat_id: int):
    now = now_kyiv()
    year, month = now.year, now.month

    awards = await calculate_monthly_awards(chat_id, year, month)
    if not awards:
        return

    for a in awards:
        await repo.save_award(chat_id, year, month, a["type"], a["user_id"], a["value"])

    lines = [f"🏆 <b>Награды месяца ({month:02d}.{year})</b>\n"]
    for a in awards:
        emoji_label = AWARD_TYPES.get(a["type"], a["type"])
        lines.append(f"{emoji_label} — <b>{a['name']}</b> ({a['value']})")

    lines.append("\n🎉 Поздравляем победителей!")

    try:
        await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
    except Exception:
        pass


def format_awards_list(awards: list[dict]) -> str:
    if not awards:
        return "🏆 Нет наград."

    lines = []
    current_period = None
    for a in awards:
        period = f"{a['month']:02d}.{a['year']}"
        if period != current_period:
            current_period = period
            lines.append(f"\n<b>📅 {period}</b>")

        emoji_label = AWARD_TYPES.get(a["award_type"], a["award_type"])
        name = a.get("first_name") or a.get("username") or "?"
        lines.append(f"  {emoji_label} — {name} ({a.get('value', '')})")

    return "\n".join(lines)


@router.message(Command("awards"))
async def cmd_awards(message: Message):
    args = message.text.split()
    now = now_kyiv()

    if len(args) > 1:
        try:
            parts = args[1].split(".")
            month = int(parts[0])
            year = int(parts[1]) if len(parts) > 1 else now.year
        except (ValueError, IndexError):
            await message.answer("Формат: /awards ММ.ГГГГ (напр: /awards 03.2026)")
            return
    else:
        year, month = now.year, now.month

    awards = await repo.get_awards(message.chat.id, year, month)
    if not awards:
        await message.answer(f"🏆 Нет наград за {month:02d}.{year}")
        return

    text = format_awards_list(awards)
    await message.answer(f"🏆 <b>Награды</b>\n{text}", parse_mode="HTML")


@router.message(Command("awards_all"))
async def cmd_awards_all(message: Message):
    awards = await repo.get_all_awards(message.chat.id)
    text = format_awards_list(awards)
    await message.answer(f"🏆 <b>Все награды</b>\n{text}", parse_mode="HTML")


@router.callback_query(F.data == "stats:awards")
async def cb_stats_awards(callback: CallbackQuery):
    now = now_kyiv()
    awards = await repo.get_awards(callback.message.chat.id, now.year, now.month)
    text = format_awards_list(awards)
    await callback.message.edit_text(
        f"🏆 <b>Награды</b>\n{text}",
        reply_markup=back_to_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()
