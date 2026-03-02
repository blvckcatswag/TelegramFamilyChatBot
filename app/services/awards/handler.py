from datetime import datetime
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram import F
from app.db import repositories as repo
from app.db.database import get_db
from app.bot.keyboards import back_to_menu_kb
from app.utils.helpers import mention_user

router = Router()

AWARD_TYPES = {
    "cactus_king": "\U0001f335 \u041a\u043e\u043b\u044e\u0447\u0438\u0439 \u0441\u0430\u0434\u043e\u0432\u043e\u0434",
    "cat_lover": "\U0001f408 \u041b\u044e\u0431\u0438\u043c\u0435\u0446 \u043a\u043e\u0442\u0430",
    "clean_master": "\U0001f9f9 \u0427\u0438\u0441\u0442\u044e\u043b\u044f",
    "duel_master": "\u2694\ufe0f \u0414\u0443\u044d\u043b\u044f\u043d\u0442",
    "lucky_survivor": "\U0001f52b \u0412\u0435\u0437\u0443\u043d\u0447\u0438\u043a",
    "clown": "\U0001f921 \u041a\u043b\u043e\u0443\u043d \u043c\u0435\u0441\u044f\u0446\u0430",
    "beloved": "\u2764\ufe0f \u041b\u044e\u0431\u0438\u043c\u0447\u0438\u043a",
    "quote_star": "\U0001f4ac \u0426\u0438\u0442\u0430\u0442\u0430 \u043c\u0435\u0441\u044f\u0446\u0430",
    "yasno_master": "\U0001f5e3\ufe0f \u041c\u0430\u0441\u0442\u0435\u0440 \u044f\u0441\u043d\u043e",
}


async def calculate_monthly_awards(chat_id: int, year: int, month: int) -> list[dict]:
    """Calculate awards for a specific month in a chat."""
    db = await get_db()
    awards = []

    month_start = f"{year}-{month:02d}-01"
    if month == 12:
        month_end = f"{year + 1}-01-01"
    else:
        month_end = f"{year}-{month + 1:02d}-01"

    # 1. Cactus king - tallest cactus
    rows = await db.execute_fetchall(
        "SELECT gc.user_id, gc.height_cm, u.first_name, u.username "
        "FROM GameCactus gc JOIN User u ON gc.user_id=u.user_id AND gc.chat_id=u.chat_id "
        "WHERE gc.chat_id=? ORDER BY gc.height_cm DESC LIMIT 1",
        (chat_id,),
    )
    if rows and rows[0]["height_cm"] > 0:
        awards.append({"type": "cactus_king", "user_id": rows[0]["user_id"],
                       "value": f"{rows[0]['height_cm']} \u0441\u043c",
                       "name": rows[0]["first_name"] or rows[0]["username"]})

    # 2. Cat lover - best cat score
    rows = await db.execute_fetchall(
        "SELECT gc.user_id, gc.mood_score, u.first_name, u.username "
        "FROM GameCat gc JOIN User u ON gc.user_id=u.user_id AND gc.chat_id=u.chat_id "
        "WHERE gc.chat_id=? ORDER BY gc.mood_score DESC LIMIT 1",
        (chat_id,),
    )
    if rows and rows[0]["mood_score"] > 0:
        awards.append({"type": "cat_lover", "user_id": rows[0]["user_id"],
                       "value": f"{rows[0]['mood_score']} \u043e\u0447\u043a\u043e\u0432",
                       "name": rows[0]["first_name"] or rows[0]["username"]})

    # 3. Duel master - most wins this month
    rows = await db.execute_fetchall(
        "SELECT winner_id, COUNT(*) as wins, u.first_name, u.username "
        "FROM Duel d JOIN User u ON d.winner_id=u.user_id AND d.chat_id=u.chat_id "
        "WHERE d.chat_id=? AND d.created_at >= ? AND d.created_at < ? AND d.winner_id IS NOT NULL "
        "GROUP BY d.winner_id ORDER BY wins DESC LIMIT 1",
        (chat_id, month_start, month_end),
    )
    if rows:
        awards.append({"type": "duel_master", "user_id": rows[0]["winner_id"],
                       "value": f"{rows[0]['wins']} \u043f\u043e\u0431\u0435\u0434",
                       "name": rows[0]["first_name"] or rows[0]["username"]})

    # 4. Lucky survivor - survived most roulettes
    rows = await db.execute_fetchall(
        "SELECT participants, loser_id FROM Roulette "
        "WHERE chat_id=? AND created_at >= ? AND created_at < ?",
        (chat_id, month_start, month_end),
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
            user_row = await db.execute_fetchall(
                "SELECT first_name, username FROM User WHERE user_id=? AND chat_id=?",
                (best_uid, chat_id),
            )
            name = user_row[0]["first_name"] if user_row else "?"
            awards.append({"type": "lucky_survivor", "user_id": best_uid,
                           "value": f"{survival_count[best_uid]} \u0440\u0430\u0437",
                           "name": name})

    # 5. Clown - most clown reactions received
    clown_top = await repo.get_clown_reactions_top(chat_id)
    if clown_top:
        awards.append({"type": "clown", "user_id": clown_top[0]["to_user_id"],
                       "value": f"{clown_top[0]['cnt']} \U0001f921",
                       "name": clown_top[0]["first_name"] or clown_top[0]["username"]})

    # 6. Beloved - most reactions received overall
    received_top = await repo.get_reactions_received_top(chat_id)
    if received_top:
        awards.append({"type": "beloved", "user_id": received_top[0]["to_user_id"],
                       "value": f"{received_top[0]['cnt']} \u0440\u0435\u0430\u043a\u0446\u0438\u0439",
                       "name": received_top[0]["first_name"] or received_top[0]["username"]})

    # 7. Quote star - most quoted person
    quote_counts = await repo.get_quote_counts(chat_id)
    if quote_counts:
        awards.append({"type": "quote_star", "user_id": quote_counts[0]["author_id"],
                       "value": f"{quote_counts[0]['cnt']} \u0446\u0438\u0442\u0430\u0442",
                       "name": quote_counts[0]["first_name"] or quote_counts[0]["username"]})

    # 8. Yasno master
    yasno_top = await repo.get_translator_top(chat_id)
    if yasno_top:
        awards.append({"type": "yasno_master", "user_id": yasno_top[0]["user_id"],
                       "value": f"{yasno_top[0]['cnt']} \u0440\u0430\u0437",
                       "name": yasno_top[0]["first_name"] or yasno_top[0]["username"]})

    return awards


async def publish_monthly_awards(bot: Bot, chat_id: int):
    """Calculate, save, and publish monthly awards."""
    now = datetime.utcnow()
    year, month = now.year, now.month

    awards = await calculate_monthly_awards(chat_id, year, month)
    if not awards:
        return

    # Save to DB
    for a in awards:
        await repo.save_award(chat_id, year, month, a["type"], a["user_id"], a["value"])

    # Format message
    lines = [f"\U0001f3c6 <b>\u041d\u0430\u0433\u0440\u0430\u0434\u044b \u043c\u0435\u0441\u044f\u0446\u0430 ({month:02d}.{year})</b>\n"]
    for a in awards:
        emoji_label = AWARD_TYPES.get(a["type"], a["type"])
        lines.append(f"{emoji_label} \u2014 <b>{a['name']}</b> ({a['value']})")

    lines.append("\n\U0001f389 \u041f\u043e\u0437\u0434\u0440\u0430\u0432\u043b\u044f\u0435\u043c \u043f\u043e\u0431\u0435\u0434\u0438\u0442\u0435\u043b\u0435\u0439!")

    try:
        await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
    except Exception:
        pass


def format_awards_list(awards: list[dict]) -> str:
    if not awards:
        return "\U0001f3c6 \u041d\u0435\u0442 \u043d\u0430\u0433\u0440\u0430\u0434."

    lines = []
    current_period = None
    for a in awards:
        period = f"{a['month']:02d}.{a['year']}"
        if period != current_period:
            current_period = period
            lines.append(f"\n<b>\U0001f4c5 {period}</b>")

        emoji_label = AWARD_TYPES.get(a["award_type"], a["award_type"])
        name = a.get("first_name") or a.get("username") or "?"
        lines.append(f"  {emoji_label} \u2014 {name} ({a.get('value', '')})")

    return "\n".join(lines)


@router.message(Command("awards"))
async def cmd_awards(message: Message):
    args = message.text.split()
    now = datetime.utcnow()

    if len(args) > 1:
        try:
            parts = args[1].split(".")
            month = int(parts[0])
            year = int(parts[1]) if len(parts) > 1 else now.year
        except (ValueError, IndexError):
            await message.answer("\u0424\u043e\u0440\u043c\u0430\u0442: /awards \u041c\u041c.\u0413\u0413\u0413\u0413 (\u043d\u0430\u043f\u0440: /awards 03.2026)")
            return
    else:
        year, month = now.year, now.month

    awards = await repo.get_awards(message.chat.id, year, month)
    if not awards:
        await message.answer(f"\U0001f3c6 \u041d\u0435\u0442 \u043d\u0430\u0433\u0440\u0430\u0434 \u0437\u0430 {month:02d}.{year}")
        return

    text = format_awards_list(awards)
    await message.answer(f"\U0001f3c6 <b>\u041d\u0430\u0433\u0440\u0430\u0434\u044b</b>\n{text}", parse_mode="HTML")


@router.message(Command("awards_all"))
async def cmd_awards_all(message: Message):
    awards = await repo.get_all_awards(message.chat.id)
    text = format_awards_list(awards)
    await message.answer(f"\U0001f3c6 <b>\u0412\u0441\u0435 \u043d\u0430\u0433\u0440\u0430\u0434\u044b</b>\n{text}", parse_mode="HTML")


@router.callback_query(F.data == "stats:awards")
async def cb_stats_awards(callback: CallbackQuery):
    now = datetime.utcnow()
    awards = await repo.get_awards(callback.message.chat.id, now.year, now.month)
    text = format_awards_list(awards)
    await callback.message.edit_text(
        f"\U0001f3c6 <b>\u041d\u0430\u0433\u0440\u0430\u0434\u044b</b>\n{text}",
        reply_markup=back_to_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()
