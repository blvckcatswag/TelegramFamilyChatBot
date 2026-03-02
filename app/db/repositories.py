from datetime import datetime, date
from app.db.database import get_db


# ──────────────────── Chat ────────────────────

async def get_or_create_chat(
    chat_id: int,
    title: str | None = None,
    owner_user_id: int | None = None,
) -> dict:
    db = await get_db()

    # 1) Создать чат, если его нет. Если есть — не падать.
    #    Обновляем title/owner только если пришли непустые значения.
    await db.execute(
        """
        INSERT INTO Chat (chat_id, title, owner_user_id)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            title = COALESCE(excluded.title, Chat.title),
            owner_user_id = COALESCE(excluded.owner_user_id, Chat.owner_user_id)
        """,
        (chat_id, title, owner_user_id),
    )

    # 2) Связанные таблицы тоже создаём безопасно
    await db.execute("INSERT OR IGNORE INTO Settings (chat_id) VALUES (?)", (chat_id,))
    await db.execute("INSERT OR IGNORE INTO HomeOrder (chat_id) VALUES (?)", (chat_id,))

    await db.commit()

    # 3) Возвращаем актуальную запись
    row = await db.execute_fetchall("SELECT * FROM Chat WHERE chat_id=?", (chat_id,))
    return dict(row[0])


async def set_chat_active(chat_id: int, active: bool) -> None:
    db = await get_db()
    await db.execute("UPDATE Chat SET is_active=? WHERE chat_id=?", (int(active), chat_id))
    await db.commit()


async def set_chat_banned(chat_id: int, banned: bool) -> None:
    db = await get_db()
    await db.execute("UPDATE Chat SET is_banned=? WHERE chat_id=?", (int(banned), chat_id))
    await db.commit()


async def is_chat_banned(chat_id: int) -> bool:
    db = await get_db()
    row = await db.execute_fetchall("SELECT is_banned FROM Chat WHERE chat_id=?", (chat_id,))
    return bool(row and row[0]["is_banned"])


async def get_all_active_chats() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM Chat WHERE is_active=1 AND is_banned=0")
    return [dict(r) for r in rows]


async def get_chat_count() -> dict:
    db = await get_db()
    total = await db.execute_fetchall("SELECT COUNT(*) as c FROM Chat")
    active = await db.execute_fetchall("SELECT COUNT(*) as c FROM Chat WHERE is_active=1")
    return {"total": total[0]["c"], "active": active[0]["c"]}


# ──────────────────── User ────────────────────

async def get_or_create_user(user_id: int, chat_id: int, username: str | None = None,
                             first_name: str | None = None, role: str = "user") -> dict:
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT * FROM User WHERE user_id=? AND chat_id=?", (user_id, chat_id)
    )
    if row:
        if username or first_name:
            await db.execute(
                "UPDATE User SET username=COALESCE(?,username), first_name=COALESCE(?,first_name) WHERE user_id=? AND chat_id=?",
                (username, first_name, user_id, chat_id),
            )
            await db.commit()
        return dict(row[0])
    await db.execute(
        "INSERT INTO User (user_id, chat_id, username, first_name, role) VALUES (?, ?, ?, ?, ?)",
        (user_id, chat_id, username, first_name, role),
    )
    await db.commit()
    row = await db.execute_fetchall("SELECT * FROM User WHERE user_id=? AND chat_id=?", (user_id, chat_id))
    return dict(row[0])


async def get_user_role(user_id: int, chat_id: int) -> str:
    db = await get_db()
    row = await db.execute_fetchall("SELECT role FROM User WHERE user_id=? AND chat_id=?", (user_id, chat_id))
    return row[0]["role"] if row else "user"


async def set_user_role(user_id: int, chat_id: int, role: str) -> None:
    db = await get_db()
    await db.execute("UPDATE User SET role=? WHERE user_id=? AND chat_id=?", (role, user_id, chat_id))
    await db.commit()


async def get_user_count() -> int:
    db = await get_db()
    row = await db.execute_fetchall("SELECT COUNT(DISTINCT user_id) as c FROM User")
    return row[0]["c"]


# ──────────────────── Settings ────────────────────

async def get_settings(chat_id: int) -> dict:
    db = await get_db()
    row = await db.execute_fetchall("SELECT * FROM Settings WHERE chat_id=?", (chat_id,))
    if row:
        return dict(row[0])
    await db.execute("INSERT OR IGNORE INTO Settings (chat_id) VALUES (?)", (chat_id,))
    await db.commit()
    row = await db.execute_fetchall("SELECT * FROM Settings WHERE chat_id=?", (chat_id,))
    return dict(row[0])


async def update_setting(chat_id: int, key: str, value) -> None:
    db = await get_db()
    allowed = {"weather_enabled", "weather_time", "translator_enabled", "games_enabled",
               "birthdays_enabled", "quotes_enabled"}
    if key not in allowed:
        return
    await db.execute(f"UPDATE Settings SET {key}=? WHERE chat_id=?", (value, chat_id))
    await db.commit()


# ──────────────────── Weather Cities ────────────────────

async def add_weather_city(chat_id: int, city_name: str) -> bool:
    db = await get_db()
    count = await db.execute_fetchall("SELECT COUNT(*) as c FROM WeatherCity WHERE chat_id=?", (chat_id,))
    from app.config.settings import MAX_WEATHER_CITIES_PER_CHAT
    if count[0]["c"] >= MAX_WEATHER_CITIES_PER_CHAT:
        return False
    await db.execute("INSERT OR IGNORE INTO WeatherCity (chat_id, city_name) VALUES (?, ?)", (chat_id, city_name))
    await db.commit()
    return True


async def remove_weather_city(chat_id: int, city_name: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM WeatherCity WHERE chat_id=? AND city_name=?", (chat_id, city_name))
    await db.commit()


async def get_weather_cities(chat_id: int) -> list[str]:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT city_name FROM WeatherCity WHERE chat_id=?", (chat_id,))
    return [r["city_name"] for r in rows]


# ──────────────────── Reminders ────────────────────

async def create_reminder(chat_id: int, user_id: int, text: str, run_at: str,
                          rtype: str = "once", rrule: str | None = None) -> int | None:
    db = await get_db()
    from app.config.settings import MAX_REMINDERS_PER_CHAT
    count = await db.execute_fetchall(
        "SELECT COUNT(*) as c FROM Reminder WHERE chat_id=? AND is_active=1", (chat_id,)
    )
    if count[0]["c"] >= MAX_REMINDERS_PER_CHAT:
        return None
    cursor = await db.execute(
        "INSERT INTO Reminder (chat_id, user_id, text, type, run_at, rrule) VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, user_id, text, rtype, run_at, rrule),
    )
    await db.commit()
    return cursor.lastrowid


async def get_active_reminders(chat_id: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM Reminder WHERE chat_id=? AND is_active=1 ORDER BY run_at", (chat_id,)
    )
    return [dict(r) for r in rows]


async def get_all_active_reminders() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM Reminder WHERE is_active=1 ORDER BY run_at")
    return [dict(r) for r in rows]


async def deactivate_reminder(reminder_id: int) -> None:
    db = await get_db()
    await db.execute("UPDATE Reminder SET is_active=0 WHERE id=?", (reminder_id,))
    await db.commit()


async def delete_reminder(reminder_id: int, chat_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM Reminder WHERE id=? AND chat_id=?", (reminder_id, chat_id))
    await db.commit()


# ──────────────────── Birthdays ────────────────────

async def add_birthday(chat_id: int, name: str, bdate: str) -> None:
    db = await get_db()
    await db.execute("INSERT INTO Birthday (chat_id, name, date) VALUES (?, ?, ?)", (chat_id, name, bdate))
    await db.commit()


async def get_birthdays(chat_id: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM Birthday WHERE chat_id=? ORDER BY date", (chat_id,))
    return [dict(r) for r in rows]


async def get_all_birthdays() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM Birthday")
    return [dict(r) for r in rows]


async def update_birthday_notified(birthday_id: int, year: int) -> None:
    db = await get_db()
    await db.execute("UPDATE Birthday SET notified_year=? WHERE id=?", (year, birthday_id))
    await db.commit()


# ──────────────────── Game: Cactus ────────────────────

async def get_cactus(chat_id: int, user_id: int) -> dict:
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT * FROM GameCactus WHERE chat_id=? AND user_id=?", (chat_id, user_id)
    )
    if row:
        return dict(row[0])
    await db.execute(
        "INSERT INTO GameCactus (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id)
    )
    await db.commit()
    row = await db.execute_fetchall("SELECT * FROM GameCactus WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    return dict(row[0])


async def update_cactus(chat_id: int, user_id: int, height_cm: int, today: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE GameCactus SET height_cm=?, last_play_date=?, total_plays=total_plays+1 WHERE chat_id=? AND user_id=?",
        (height_cm, today, chat_id, user_id),
    )
    await db.commit()


async def get_cactus_top(chat_id: int, limit: int = 10) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT gc.*, u.first_name, u.username FROM GameCactus gc "
        "JOIN User u ON gc.user_id=u.user_id AND gc.chat_id=u.chat_id "
        "WHERE gc.chat_id=? ORDER BY gc.height_cm DESC LIMIT ?",
        (chat_id, limit),
    )
    return [dict(r) for r in rows]


# ──────────────────── Game: Cat ────────────────────

async def get_cat(chat_id: int, user_id: int) -> dict:
    db = await get_db()
    row = await db.execute_fetchall("SELECT * FROM GameCat WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    if row:
        return dict(row[0])
    await db.execute("INSERT INTO GameCat (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))
    await db.commit()
    row = await db.execute_fetchall("SELECT * FROM GameCat WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    return dict(row[0])


async def update_cat(chat_id: int, user_id: int, mood_score: int, today: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE GameCat SET mood_score=?, last_play_date=?, total_plays=total_plays+1 WHERE chat_id=? AND user_id=?",
        (mood_score, today, chat_id, user_id),
    )
    await db.commit()


async def get_cat_top(chat_id: int, limit: int = 10) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT gc.*, u.first_name, u.username FROM GameCat gc "
        "JOIN User u ON gc.user_id=u.user_id AND gc.chat_id=u.chat_id "
        "WHERE gc.chat_id=? ORDER BY gc.mood_score DESC LIMIT ?",
        (chat_id, limit),
    )
    return [dict(r) for r in rows]


# ──────────────────── Home Order ────────────────────

async def get_home_order(chat_id: int) -> int:
    db = await get_db()
    row = await db.execute_fetchall("SELECT order_score FROM HomeOrder WHERE chat_id=?", (chat_id,))
    if row:
        return row[0]["order_score"]
    await db.execute("INSERT OR IGNORE INTO HomeOrder (chat_id) VALUES (?)", (chat_id,))
    await db.commit()
    return 50


async def update_home_order(chat_id: int, delta: int) -> int:
    from app.config.settings import HOME_ORDER_MAX, HOME_ORDER_MIN
    current = await get_home_order(chat_id)
    new_val = max(HOME_ORDER_MIN, min(HOME_ORDER_MAX, current + delta))
    db = await get_db()
    await db.execute(
        "UPDATE HomeOrder SET order_score=?, updated_at=datetime('now') WHERE chat_id=?",
        (new_val, chat_id),
    )
    await db.commit()
    return new_val


# ──────────────────── Duel ────────────────────

async def create_duel(chat_id: int, challenger_id: int, opponent_id: int,
                      winner_id: int, mute_minutes: int) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO Duel (chat_id, challenger_id, opponent_id, winner_id, mute_minutes) VALUES (?, ?, ?, ?, ?)",
        (chat_id, challenger_id, opponent_id, winner_id, mute_minutes),
    )
    await db.commit()
    return cursor.lastrowid


async def get_last_duel_time(chat_id: int, user_id: int) -> str | None:
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT created_at FROM Duel WHERE chat_id=? AND (challenger_id=? OR opponent_id=?) ORDER BY created_at DESC LIMIT 1",
        (chat_id, user_id, user_id),
    )
    return row[0]["created_at"] if row else None


async def get_duel_stats(chat_id: int, user_id: int) -> dict:
    db = await get_db()
    total = await db.execute_fetchall(
        "SELECT COUNT(*) as c FROM Duel WHERE chat_id=? AND (challenger_id=? OR opponent_id=?)",
        (chat_id, user_id, user_id),
    )
    wins = await db.execute_fetchall(
        "SELECT COUNT(*) as c FROM Duel WHERE chat_id=? AND winner_id=?",
        (chat_id, user_id),
    )
    return {"total": total[0]["c"], "wins": wins[0]["c"]}


async def get_duel_top(chat_id: int, limit: int = 10) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT d.winner_id, COUNT(*) as wins, u.first_name, u.username "
        "FROM Duel d JOIN User u ON d.winner_id=u.user_id AND d.chat_id=u.chat_id "
        "WHERE d.chat_id=? AND d.winner_id IS NOT NULL "
        "GROUP BY d.winner_id ORDER BY wins DESC LIMIT ?",
        (chat_id, limit),
    )
    return [dict(r) for r in rows]


# ──────────────────── Roulette ────────────────────

async def create_roulette(chat_id: int, participants: str, loser_id: int) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO Roulette (chat_id, participants, loser_id) VALUES (?, ?, ?)",
        (chat_id, participants, loser_id),
    )
    await db.commit()
    return cursor.lastrowid


async def get_roulette_survival_count(chat_id: int, user_id: int) -> int:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT participants, loser_id FROM Roulette WHERE chat_id=?", (chat_id,)
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
    rows = await db.execute_fetchall(
        "SELECT created_at, participants FROM Roulette WHERE chat_id=? ORDER BY created_at DESC",
        (chat_id,),
    )
    import json
    for r in rows:
        try:
            participants = json.loads(r["participants"])
        except (json.JSONDecodeError, TypeError):
            continue
        if user_id in participants:
            return r["created_at"]
    return None


# ──────────────────── Quotes ────────────────────

async def save_quote(chat_id: int, author_id: int, saved_by_id: int,
                     text: str, message_id: int | None = None) -> int | None:
    db = await get_db()
    from app.config.settings import MAX_QUOTES_PER_CHAT
    count = await db.execute_fetchall("SELECT COUNT(*) as c FROM Quote WHERE chat_id=?", (chat_id,))
    if count[0]["c"] >= MAX_QUOTES_PER_CHAT:
        return None
    cursor = await db.execute(
        "INSERT INTO Quote (chat_id, author_id, saved_by_id, text, message_id) VALUES (?, ?, ?, ?, ?)",
        (chat_id, author_id, saved_by_id, text, message_id),
    )
    await db.commit()
    return cursor.lastrowid


async def get_random_quote(chat_id: int) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT q.*, u.first_name, u.username FROM Quote q "
        "LEFT JOIN User u ON q.author_id=u.user_id AND q.chat_id=u.chat_id "
        "WHERE q.chat_id=? ORDER BY RANDOM() LIMIT 1",
        (chat_id,),
    )
    return dict(rows[0]) if rows else None


async def get_last_quotes(chat_id: int, limit: int = 5) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT q.*, u.first_name, u.username FROM Quote q "
        "LEFT JOIN User u ON q.author_id=u.user_id AND q.chat_id=u.chat_id "
        "WHERE q.chat_id=? ORDER BY q.created_at DESC LIMIT ?",
        (chat_id, limit),
    )
    return [dict(r) for r in rows]


async def get_quote_counts(chat_id: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT q.author_id, COUNT(*) as cnt, u.first_name, u.username "
        "FROM Quote q JOIN User u ON q.author_id=u.user_id AND q.chat_id=u.chat_id "
        "WHERE q.chat_id=? GROUP BY q.author_id ORDER BY cnt DESC",
        (chat_id,),
    )
    return [dict(r) for r in rows]


# ──────────────────── Translator Log ────────────────────

async def log_translator(chat_id: int, user_id: int, trigger_word: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO TranslatorLog (chat_id, user_id, trigger_word) VALUES (?, ?, ?)",
        (chat_id, user_id, trigger_word),
    )
    await db.commit()


async def get_translator_top(chat_id: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT t.user_id, COUNT(*) as cnt, u.first_name, u.username "
        "FROM TranslatorLog t JOIN User u ON t.user_id=u.user_id AND t.chat_id=u.chat_id "
        "WHERE t.chat_id=? GROUP BY t.user_id ORDER BY cnt DESC",
        (chat_id,),
    )
    return [dict(r) for r in rows]


# ──────────────────── Mute Log ────────────────────

async def log_mute(chat_id: int, user_id: int, reason: str, muted_until: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO MuteLog (chat_id, user_id, reason, muted_until) VALUES (?, ?, ?, ?)",
        (chat_id, user_id, reason, muted_until),
    )
    await db.commit()


async def is_user_muted(chat_id: int, user_id: int) -> bool:
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT muted_until FROM MuteLog WHERE chat_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1",
        (chat_id, user_id),
    )
    if not row:
        return False
    muted_until = datetime.fromisoformat(row[0]["muted_until"])
    return datetime.utcnow() < muted_until


# ──────────────────── Reactions ────────────────────

async def save_reaction(chat_id: int, message_id: int, from_user_id: int,
                        emoji: str, to_user_id: int | None = None) -> None:
    db = await get_db()
    await db.execute(
        "DELETE FROM MessageReaction WHERE chat_id=? AND message_id=? AND from_user_id=?",
        (chat_id, message_id, from_user_id),
    )
    await db.execute(
        "INSERT INTO MessageReaction (chat_id, message_id, from_user_id, to_user_id, emoji) VALUES (?, ?, ?, ?, ?)",
        (chat_id, message_id, from_user_id, to_user_id, emoji),
    )
    await db.commit()


async def get_top_reactions(chat_id: int, limit: int = 5) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT emoji, COUNT(*) as cnt FROM MessageReaction "
        "WHERE chat_id=? AND created_at >= date('now', 'start of month') "
        "GROUP BY emoji ORDER BY cnt DESC LIMIT ?",
        (chat_id, limit),
    )
    return [dict(r) for r in rows]


async def get_my_reactions_count(chat_id: int, user_id: int) -> int:
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT COUNT(*) as c FROM MessageReaction WHERE chat_id=? AND to_user_id=?",
        (chat_id, user_id),
    )
    return row[0]["c"]


async def get_reactions_received_top(chat_id: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT to_user_id, COUNT(*) as cnt, u.first_name, u.username "
        "FROM MessageReaction mr JOIN User u ON mr.to_user_id=u.user_id AND mr.chat_id=u.chat_id "
        "WHERE mr.chat_id=? AND mr.created_at >= date('now', 'start of month') AND mr.to_user_id IS NOT NULL "
        "GROUP BY mr.to_user_id ORDER BY cnt DESC",
        (chat_id,),
    )
    return [dict(r) for r in rows]


async def get_clown_reactions_top(chat_id: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT to_user_id, COUNT(*) as cnt, u.first_name, u.username "
        "FROM MessageReaction mr JOIN User u ON mr.to_user_id=u.user_id AND mr.chat_id=u.chat_id "
        "WHERE mr.chat_id=? AND mr.emoji=? AND mr.created_at >= date('now', 'start of month') AND mr.to_user_id IS NOT NULL "
        "GROUP BY mr.to_user_id ORDER BY cnt DESC",
        (chat_id, "\U0001f921"),
    )
    return [dict(r) for r in rows]


# ──────────────────── Monthly Awards ────────────────────

async def save_award(chat_id: int, year: int, month: int, award_type: str,
                     user_id: int, value: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO MonthlyAward (chat_id, year, month, award_type, user_id, value) VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, year, month, award_type, user_id, value),
    )
    await db.commit()


async def get_awards(chat_id: int, year: int, month: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT ma.*, u.first_name, u.username FROM MonthlyAward ma "
        "LEFT JOIN User u ON ma.user_id=u.user_id AND ma.chat_id=u.chat_id "
        "WHERE ma.chat_id=? AND ma.year=? AND ma.month=?",
        (chat_id, year, month),
    )
    return [dict(r) for r in rows]


async def get_all_awards(chat_id: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT ma.*, u.first_name, u.username FROM MonthlyAward ma "
        "LEFT JOIN User u ON ma.user_id=u.user_id AND ma.chat_id=u.chat_id "
        "WHERE ma.chat_id=? ORDER BY ma.year DESC, ma.month DESC",
        (chat_id,),
    )
    return [dict(r) for r in rows]
