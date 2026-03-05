"""
All database queries. Uses $1,$2 placeholders (auto-converted to ? for SQLite).
"""
from datetime import datetime, date
from app.db.database import get_db
from app.utils.helpers import now_kyiv


# ──────────────────── Chat ────────────────────

async def get_or_create_chat(
    chat_id: int,
    title: str | None = None,
    owner_user_id: int | None = None,
) -> dict:
    db = await get_db()

    await db.execute(
        """
        INSERT INTO Chat (chat_id, title, owner_user_id)
        VALUES ($1, $2, $3)
        ON CONFLICT(chat_id) DO UPDATE SET
            title = COALESCE(EXCLUDED.title, Chat.title),
            owner_user_id = COALESCE(EXCLUDED.owner_user_id, Chat.owner_user_id)
        """,
        chat_id, title, owner_user_id,
    )

    await db.execute(
        "INSERT INTO Settings (chat_id) VALUES ($1) ON CONFLICT (chat_id) DO NOTHING",
        chat_id,
    )
    await db.execute(
        "INSERT INTO HomeOrder (chat_id) VALUES ($1) ON CONFLICT (chat_id) DO NOTHING",
        chat_id,
    )

    row = await db.fetchrow("SELECT * FROM Chat WHERE chat_id=$1", chat_id)
    return row


async def set_chat_active(chat_id: int, active: bool) -> None:
    db = await get_db()
    await db.execute("UPDATE Chat SET is_active=$1 WHERE chat_id=$2", active, chat_id)


async def set_chat_banned(chat_id: int, banned: bool) -> None:
    db = await get_db()
    await db.execute("UPDATE Chat SET is_banned=$1 WHERE chat_id=$2", banned, chat_id)


async def is_chat_banned(chat_id: int) -> bool:
    db = await get_db()
    row = await db.fetchrow("SELECT is_banned FROM Chat WHERE chat_id=$1", chat_id)
    return bool(row and row["is_banned"])


async def get_all_active_chats() -> list[dict]:
    db = await get_db()
    return await db.fetch("SELECT * FROM Chat WHERE is_active=$1 AND is_banned=$2", True, False)


async def get_chat_count() -> dict:
    db = await get_db()
    total = await db.fetchval("SELECT COUNT(*) FROM Chat")
    active = await db.fetchval("SELECT COUNT(*) FROM Chat WHERE is_active=$1", True)
    return {"total": total, "active": active}


# ──────────────────── User ────────────────────

async def get_or_create_user(user_id: int, chat_id: int, username: str | None = None,
                             first_name: str | None = None, role: str = "user") -> dict:
    db = await get_db()
    row = await db.fetchrow(
        'SELECT * FROM "User" WHERE user_id=$1 AND chat_id=$2', user_id, chat_id
    )
    if row:
        if username or first_name:
            await db.execute(
                'UPDATE "User" SET username=COALESCE($1,username), first_name=COALESCE($2,first_name) WHERE user_id=$3 AND chat_id=$4',
                username, first_name, user_id, chat_id,
            )
        return dict(row)
    await db.execute(
        'INSERT INTO "User" (user_id, chat_id, username, first_name, role) VALUES ($1, $2, $3, $4, $5)',
        user_id, chat_id, username, first_name, role,
    )
    row = await db.fetchrow('SELECT * FROM "User" WHERE user_id=$1 AND chat_id=$2', user_id, chat_id)
    return dict(row)


async def get_user_by_username(chat_id: int, username: str) -> dict | None:
    db = await get_db()
    return await db.fetchrow(
        'SELECT * FROM "User" WHERE chat_id=$1 AND LOWER(username)=LOWER($2)',
        chat_id, username,
    )


async def get_user_role(user_id: int, chat_id: int) -> str:
    db = await get_db()
    row = await db.fetchrow('SELECT role FROM "User" WHERE user_id=$1 AND chat_id=$2', user_id, chat_id)
    return row["role"] if row else "user"


async def set_user_role(user_id: int, chat_id: int, role: str) -> None:
    db = await get_db()
    await db.execute('UPDATE "User" SET role=$1 WHERE user_id=$2 AND chat_id=$3', role, user_id, chat_id)


async def get_user_count() -> int:
    db = await get_db()
    return await db.fetchval('SELECT COUNT(DISTINCT user_id) FROM "User"')


# ──────────────────── Settings ────────────────────

async def get_settings(chat_id: int) -> dict:
    db = await get_db()
    row = await db.fetchrow("SELECT * FROM Settings WHERE chat_id=$1", chat_id)
    if row:
        return dict(row)
    await db.execute("INSERT INTO Settings (chat_id) VALUES ($1) ON CONFLICT (chat_id) DO NOTHING", chat_id)
    row = await db.fetchrow("SELECT * FROM Settings WHERE chat_id=$1", chat_id)
    return dict(row)


async def update_setting(chat_id: int, key: str, value) -> None:
    db = await get_db()
    allowed = {"weather_enabled", "weather_time", "translator_enabled", "games_enabled",
               "birthdays_enabled", "quotes_enabled"}
    if key not in allowed:
        return
    # Dynamic column name is safe — validated against allowlist
    await db.execute(f"UPDATE Settings SET {key}=$1 WHERE chat_id=$2", value, chat_id)


# ──────────────────── Weather Cities ────────────────────

async def add_weather_city(chat_id: int, city_name: str) -> bool:
    db = await get_db()
    count = await db.fetchval("SELECT COUNT(*) FROM WeatherCity WHERE chat_id=$1", chat_id)
    from app.config.settings import MAX_WEATHER_CITIES_PER_CHAT
    if count >= MAX_WEATHER_CITIES_PER_CHAT:
        return False
    await db.execute(
        "INSERT INTO WeatherCity (chat_id, city_name) VALUES ($1, $2) ON CONFLICT (chat_id, city_name) DO NOTHING",
        chat_id, city_name,
    )
    return True


async def remove_weather_city(chat_id: int, city_name: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM WeatherCity WHERE chat_id=$1 AND city_name=$2", chat_id, city_name)


async def get_weather_cities(chat_id: int) -> list[str]:
    db = await get_db()
    rows = await db.fetch("SELECT city_name FROM WeatherCity WHERE chat_id=$1", chat_id)
    return [r["city_name"] for r in rows]


# ──────────────────── Reminders ────────────────────

async def create_reminder(chat_id: int, user_id: int, text: str, run_at: str,
                          rtype: str = "once", rrule: str | None = None) -> int | None:
    db = await get_db()
    from app.config.settings import MAX_REMINDERS_PER_CHAT
    count = await db.fetchval(
        "SELECT COUNT(*) FROM Reminder WHERE chat_id=$1 AND is_active=$2", chat_id, True,
    )
    if count >= MAX_REMINDERS_PER_CHAT:
        return None
    rid = await db.execute(
        "INSERT INTO Reminder (chat_id, user_id, text, type, run_at, rrule) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
        chat_id, user_id, text, rtype, run_at, rrule,
    )
    return rid


async def get_active_reminders(chat_id: int) -> list[dict]:
    db = await get_db()
    return await db.fetch(
        "SELECT * FROM Reminder WHERE chat_id=$1 AND is_active=$2 ORDER BY run_at", chat_id, True,
    )


async def get_all_active_reminders() -> list[dict]:
    db = await get_db()
    return await db.fetch("SELECT * FROM Reminder WHERE is_active=$1 ORDER BY run_at", True)


async def deactivate_reminder(reminder_id: int) -> None:
    db = await get_db()
    await db.execute("UPDATE Reminder SET is_active=$1 WHERE id=$2", False, reminder_id)


async def delete_reminder(reminder_id: int, chat_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM Reminder WHERE id=$1 AND chat_id=$2", reminder_id, chat_id)


# ──────────────────── Birthdays ────────────────────

async def add_birthday(chat_id: int, name: str, bdate: str) -> None:
    db = await get_db()
    await db.execute("INSERT INTO Birthday (chat_id, name, date) VALUES ($1, $2, $3)", chat_id, name, bdate)


async def get_birthdays(chat_id: int) -> list[dict]:
    db = await get_db()
    return await db.fetch("SELECT * FROM Birthday WHERE chat_id=$1 ORDER BY date", chat_id)


async def get_all_birthdays() -> list[dict]:
    db = await get_db()
    return await db.fetch("SELECT * FROM Birthday")


async def update_birthday_notified(birthday_id: int, year: int) -> None:
    db = await get_db()
    await db.execute("UPDATE Birthday SET notified_year=$1 WHERE id=$2", year, birthday_id)


# ──────────────────── Game: Cactus ────────────────────

async def get_cactus(chat_id: int, user_id: int) -> dict:
    db = await get_db()
    row = await db.fetchrow(
        "SELECT * FROM GameCactus WHERE chat_id=$1 AND user_id=$2", chat_id, user_id,
    )
    if row:
        return dict(row)
    await db.execute(
        "INSERT INTO GameCactus (chat_id, user_id) VALUES ($1, $2) ON CONFLICT (chat_id, user_id) DO NOTHING",
        chat_id, user_id,
    )
    row = await db.fetchrow("SELECT * FROM GameCactus WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)
    return dict(row)


async def update_cactus(chat_id: int, user_id: int, height_cm: int, today: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE GameCactus SET height_cm=$1, last_play_date=$2, total_plays=total_plays+1 WHERE chat_id=$3 AND user_id=$4",
        height_cm, today, chat_id, user_id,
    )


async def get_cactus_top(chat_id: int, limit: int = 10) -> list[dict]:
    db = await get_db()
    return await db.fetch(
        'SELECT gc.*, u.first_name, u.username FROM GameCactus gc '
        'JOIN "User" u ON gc.user_id=u.user_id AND gc.chat_id=u.chat_id '
        'WHERE gc.chat_id=$1 ORDER BY gc.height_cm DESC LIMIT $2',
        chat_id, limit,
    )


# ──────────────────── Game: Cat ────────────────────

async def get_cat(chat_id: int, user_id: int) -> dict:
    db = await get_db()
    row = await db.fetchrow("SELECT * FROM GameCat WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)
    if row:
        return dict(row)
    await db.execute(
        "INSERT INTO GameCat (chat_id, user_id) VALUES ($1, $2) ON CONFLICT (chat_id, user_id) DO NOTHING",
        chat_id, user_id,
    )
    row = await db.fetchrow("SELECT * FROM GameCat WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)
    return dict(row)


async def update_cat(chat_id: int, user_id: int, mood_score: int, today: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE GameCat SET mood_score=$1, last_play_date=$2, total_plays=total_plays+1 WHERE chat_id=$3 AND user_id=$4",
        mood_score, today, chat_id, user_id,
    )


async def get_cat_top(chat_id: int, limit: int = 10) -> list[dict]:
    db = await get_db()
    return await db.fetch(
        'SELECT gc.*, u.first_name, u.username FROM GameCat gc '
        'JOIN "User" u ON gc.user_id=u.user_id AND gc.chat_id=u.chat_id '
        'WHERE gc.chat_id=$1 ORDER BY gc.mood_score DESC LIMIT $2',
        chat_id, limit,
    )


# ──────────────────── Home Order ────────────────────

async def get_home_order(chat_id: int) -> int:
    db = await get_db()
    val = await db.fetchval("SELECT order_score FROM HomeOrder WHERE chat_id=$1", chat_id)
    if val is not None:
        return val
    await db.execute("INSERT INTO HomeOrder (chat_id) VALUES ($1) ON CONFLICT (chat_id) DO NOTHING", chat_id)
    return 50


async def update_home_order(chat_id: int, delta: int) -> int:
    from app.config.settings import HOME_ORDER_MAX, HOME_ORDER_MIN
    current = await get_home_order(chat_id)
    new_val = max(HOME_ORDER_MIN, min(HOME_ORDER_MAX, current + delta))
    db = await get_db()
    await db.execute(
        "UPDATE HomeOrder SET order_score=$1 WHERE chat_id=$2",
        new_val, chat_id,
    )
    return new_val


# ──────────────────── Duel ────────────────────

async def create_duel(chat_id: int, challenger_id: int, opponent_id: int,
                      winner_id: int, mute_minutes: int) -> int:
    db = await get_db()
    rid = await db.execute(
        "INSERT INTO Duel (chat_id, challenger_id, opponent_id, winner_id, mute_minutes) VALUES ($1, $2, $3, $4, $5) RETURNING id",
        chat_id, challenger_id, opponent_id, winner_id, mute_minutes,
    )
    return rid


async def get_last_duel_time(chat_id: int, user_id: int) -> str | None:
    db = await get_db()
    row = await db.fetchrow(
        "SELECT created_at FROM Duel WHERE chat_id=$1 AND (challenger_id=$2 OR opponent_id=$2) ORDER BY created_at DESC LIMIT 1",
        chat_id, user_id,
    )
    if not row:
        return None
    val = row["created_at"]
    return val.isoformat() if hasattr(val, 'isoformat') else str(val)


async def get_duel_stats(chat_id: int, user_id: int) -> dict:
    db = await get_db()
    total = await db.fetchval(
        "SELECT COUNT(*) FROM Duel WHERE chat_id=$1 AND (challenger_id=$2 OR opponent_id=$2)",
        chat_id, user_id,
    )
    wins = await db.fetchval(
        "SELECT COUNT(*) FROM Duel WHERE chat_id=$1 AND winner_id=$2",
        chat_id, user_id,
    )
    return {"total": total or 0, "wins": wins or 0}


async def get_duel_top(chat_id: int, limit: int = 10) -> list[dict]:
    db = await get_db()
    return await db.fetch(
        'SELECT d.winner_id, COUNT(*) as wins, u.first_name, u.username '
        'FROM Duel d JOIN "User" u ON d.winner_id=u.user_id AND d.chat_id=u.chat_id '
        'WHERE d.chat_id=$1 AND d.winner_id IS NOT NULL '
        'GROUP BY d.winner_id, u.first_name, u.username ORDER BY wins DESC LIMIT $2',
        chat_id, limit,
    )


# ──────────────────── Roulette ────────────────────

async def create_roulette(chat_id: int, participants: str, loser_id: int) -> int:
    db = await get_db()
    rid = await db.execute(
        "INSERT INTO Roulette (chat_id, participants, loser_id) VALUES ($1, $2, $3) RETURNING id",
        chat_id, participants, loser_id,
    )
    return rid


async def get_roulette_survival_count(chat_id: int, user_id: int) -> int:
    db = await get_db()
    rows = await db.fetch(
        "SELECT participants, loser_id FROM Roulette WHERE chat_id=$1", chat_id,
    )
    import json
    survived = 0
    for r in rows:
        try:
            participants = json.loads(r["participants"])
        except (json.JSONDecodeError, TypeError):
            continue
        if user_id in participants and r["loser_id"] != user_id:
            survived += 1
    return survived


async def get_last_roulette_time(chat_id: int, user_id: int) -> str | None:
    db = await get_db()
    rows = await db.fetch(
        "SELECT created_at, participants FROM Roulette WHERE chat_id=$1 ORDER BY created_at DESC",
        chat_id,
    )
    import json
    for r in rows:
        try:
            participants = json.loads(r["participants"])
        except (json.JSONDecodeError, TypeError):
            continue
        if user_id in participants:
            val = r["created_at"]
            return val.isoformat() if hasattr(val, 'isoformat') else str(val)
    return None


# ──────────────────── Quotes ────────────────────

async def save_quote(chat_id: int, author_id: int, saved_by_id: int,
                     text: str, message_id: int | None = None) -> int | None:
    db = await get_db()
    from app.config.settings import MAX_QUOTES_PER_CHAT
    count = await db.fetchval("SELECT COUNT(*) FROM Quote WHERE chat_id=$1", chat_id)
    if count >= MAX_QUOTES_PER_CHAT:
        return None
    rid = await db.execute(
        "INSERT INTO Quote (chat_id, author_id, saved_by_id, text, message_id) VALUES ($1, $2, $3, $4, $5) RETURNING id",
        chat_id, author_id, saved_by_id, text, message_id,
    )
    return rid


async def get_random_quote(chat_id: int) -> dict | None:
    db = await get_db()
    return await db.fetchrow(
        'SELECT q.*, u.first_name, u.username FROM Quote q '
        'LEFT JOIN "User" u ON q.author_id=u.user_id AND q.chat_id=u.chat_id '
        'WHERE q.chat_id=$1 ORDER BY RANDOM() LIMIT 1',
        chat_id,
    )


async def get_last_quotes(chat_id: int, limit: int = 5) -> list[dict]:
    db = await get_db()
    return await db.fetch(
        'SELECT q.*, u.first_name, u.username FROM Quote q '
        'LEFT JOIN "User" u ON q.author_id=u.user_id AND q.chat_id=u.chat_id '
        'WHERE q.chat_id=$1 ORDER BY q.created_at DESC LIMIT $2',
        chat_id, limit,
    )


async def get_quote_counts(chat_id: int) -> list[dict]:
    db = await get_db()
    return await db.fetch(
        'SELECT q.author_id, COUNT(*) as cnt, u.first_name, u.username '
        'FROM Quote q JOIN "User" u ON q.author_id=u.user_id AND q.chat_id=u.chat_id '
        'WHERE q.chat_id=$1 GROUP BY q.author_id, u.first_name, u.username ORDER BY cnt DESC',
        chat_id,
    )


# ──────────────────── Translator Log ────────────────────

async def log_translator(chat_id: int, user_id: int, trigger_word: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO TranslatorLog (chat_id, user_id, trigger_word) VALUES ($1, $2, $3)",
        chat_id, user_id, trigger_word,
    )


async def get_translator_top(chat_id: int) -> list[dict]:
    db = await get_db()
    return await db.fetch(
        'SELECT t.user_id, COUNT(*) as cnt, u.first_name, u.username '
        'FROM TranslatorLog t JOIN "User" u ON t.user_id=u.user_id AND t.chat_id=u.chat_id '
        'WHERE t.chat_id=$1 GROUP BY t.user_id, u.first_name, u.username ORDER BY cnt DESC',
        chat_id,
    )


# ──────────────────── Mute Log ────────────────────

async def log_mute(chat_id: int, user_id: int, reason: str, muted_until: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO MuteLog (chat_id, user_id, reason, muted_until) VALUES ($1, $2, $3, $4)",
        chat_id, user_id, reason, muted_until,
    )


async def is_user_muted(chat_id: int, user_id: int) -> bool:
    return await get_active_mute_until(chat_id, user_id) is not None


async def get_active_mute_until(chat_id: int, user_id: int):
    """Returns the active mute expiry datetime, or None if not muted."""
    db = await get_db()
    row = await db.fetchrow(
        "SELECT muted_until FROM MuteLog WHERE chat_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 1",
        chat_id, user_id,
    )
    if not row:
        return None
    muted_until = datetime.fromisoformat(str(row["muted_until"]))
    if muted_until.tzinfo is None:
        from app.utils.helpers import KYIV_TZ
        muted_until = muted_until.replace(tzinfo=KYIV_TZ)
    return muted_until if now_kyiv() < muted_until else None


# ──────────────────── Message Author ────────────────────

async def save_message_author(chat_id: int, message_id: int, user_id: int) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO MessageAuthor (chat_id, message_id, user_id) VALUES ($1, $2, $3) ON CONFLICT (chat_id, message_id) DO NOTHING",
        chat_id, message_id, user_id,
    )


async def get_message_author(chat_id: int, message_id: int) -> int | None:
    db = await get_db()
    return await db.fetchval(
        "SELECT user_id FROM MessageAuthor WHERE chat_id=$1 AND message_id=$2",
        chat_id, message_id,
    )


async def cleanup_old_message_authors() -> int:
    """Delete MessageAuthor records older than 30 days. Returns deleted count."""
    db = await get_db()
    if db.is_postgres:
        result = await db.fetchval(
            "WITH deleted AS (DELETE FROM MessageAuthor WHERE created_at < NOW() - INTERVAL '30 days' RETURNING 1) SELECT COUNT(*) FROM deleted"
        )
    else:
        count = await db.fetchval(
            "SELECT COUNT(*) FROM MessageAuthor WHERE created_at < datetime('now', '-30 days')"
        )
        await db.execute(
            "DELETE FROM MessageAuthor WHERE created_at < datetime('now', '-30 days')"
        )
        result = count
    return result or 0


# ──────────────────── Reactions ────────────────────

async def save_reaction(chat_id: int, message_id: int, from_user_id: int,
                        emoji: str, to_user_id: int | None = None) -> None:
    db = await get_db()
    await db.execute(
        "DELETE FROM MessageReaction WHERE chat_id=$1 AND message_id=$2 AND from_user_id=$3",
        chat_id, message_id, from_user_id,
    )
    await db.execute(
        "INSERT INTO MessageReaction (chat_id, message_id, from_user_id, to_user_id, emoji) VALUES ($1, $2, $3, $4, $5)",
        chat_id, message_id, from_user_id, to_user_id, emoji,
    )


async def _month_start_condition(db) -> str:
    """Return SQL for 'start of current month' depending on DB engine."""
    if db.is_postgres:
        return "date_trunc('month', NOW())"
    return "date('now', 'start of month')"


async def get_top_reactions(chat_id: int, limit: int = 5) -> list[dict]:
    db = await get_db()
    month_start = await _month_start_condition(db)
    return await db.fetch(
        f"SELECT emoji, COUNT(*) as cnt FROM MessageReaction "
        f"WHERE chat_id=$1 AND created_at >= {month_start} "
        f"GROUP BY emoji ORDER BY cnt DESC LIMIT $2",
        chat_id, limit,
    )


async def get_my_reactions_count(chat_id: int, user_id: int) -> int:
    db = await get_db()
    val = await db.fetchval(
        "SELECT COUNT(*) FROM MessageReaction WHERE chat_id=$1 AND to_user_id=$2",
        chat_id, user_id,
    )
    return val or 0


async def get_reactions_received_top(chat_id: int) -> list[dict]:
    db = await get_db()
    month_start = await _month_start_condition(db)
    return await db.fetch(
        f'SELECT to_user_id, COUNT(*) as cnt, u.first_name, u.username '
        f'FROM MessageReaction mr JOIN "User" u ON mr.to_user_id=u.user_id AND mr.chat_id=u.chat_id '
        f'WHERE mr.chat_id=$1 AND mr.created_at >= {month_start} AND mr.to_user_id IS NOT NULL '
        f'GROUP BY mr.to_user_id, u.first_name, u.username ORDER BY cnt DESC',
        chat_id,
    )


async def get_clown_reactions_top(chat_id: int) -> list[dict]:
    db = await get_db()
    month_start = await _month_start_condition(db)
    return await db.fetch(
        f'SELECT to_user_id, COUNT(*) as cnt, u.first_name, u.username '
        f'FROM MessageReaction mr JOIN "User" u ON mr.to_user_id=u.user_id AND mr.chat_id=u.chat_id '
        f'WHERE mr.chat_id=$1 AND mr.emoji=$2 AND mr.created_at >= {month_start} AND mr.to_user_id IS NOT NULL '
        f'GROUP BY mr.to_user_id, u.first_name, u.username ORDER BY cnt DESC',
        chat_id, "🤡",
    )


# ──────────────────── Monthly Awards ────────────────────

async def save_award(chat_id: int, year: int, month: int, award_type: str,
                     user_id: int, value: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO MonthlyAward (chat_id, year, month, award_type, user_id, value) VALUES ($1, $2, $3, $4, $5, $6)",
        chat_id, year, month, award_type, user_id, value,
    )


async def get_awards(chat_id: int, year: int, month: int) -> list[dict]:
    db = await get_db()
    return await db.fetch(
        'SELECT ma.*, u.first_name, u.username FROM MonthlyAward ma '
        'LEFT JOIN "User" u ON ma.user_id=u.user_id AND ma.chat_id=u.chat_id '
        'WHERE ma.chat_id=$1 AND ma.year=$2 AND ma.month=$3',
        chat_id, year, month,
    )


async def get_all_awards(chat_id: int) -> list[dict]:
    db = await get_db()
    return await db.fetch(
        'SELECT ma.*, u.first_name, u.username FROM MonthlyAward ma '
        'LEFT JOIN "User" u ON ma.user_id=u.user_id AND ma.chat_id=u.chat_id '
        'WHERE ma.chat_id=$1 ORDER BY ma.year DESC, ma.month DESC',
        chat_id,
    )
