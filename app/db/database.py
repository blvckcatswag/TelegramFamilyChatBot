import aiosqlite
from app.config import settings as cfg

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(cfg.DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def init_db() -> None:
    db = await get_db()

    await db.executescript("""
    CREATE TABLE IF NOT EXISTS Chat (
        chat_id INTEGER PRIMARY KEY,
        title TEXT,
        is_active INTEGER DEFAULT 1,
        is_banned INTEGER DEFAULT 0,
        owner_user_id INTEGER,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS User (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        chat_id INTEGER NOT NULL,
        username TEXT,
        first_name TEXT,
        role TEXT DEFAULT 'user',
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, chat_id),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS Settings (
        chat_id INTEGER PRIMARY KEY,
        weather_enabled INTEGER DEFAULT 1,
        weather_time TEXT DEFAULT '08:00',
        translator_enabled INTEGER DEFAULT 1,
        games_enabled INTEGER DEFAULT 1,
        birthdays_enabled INTEGER DEFAULT 1,
        quotes_enabled INTEGER DEFAULT 1,
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS WeatherCity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        city_name TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(chat_id, city_name),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS Reminder (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        type TEXT DEFAULT 'once',
        run_at TEXT NOT NULL,
        rrule TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS Birthday (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        date TEXT NOT NULL,
        notified_year INTEGER DEFAULT 0,
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS GameCactus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        height_cm INTEGER DEFAULT 0,
        last_play_date TEXT,
        total_plays INTEGER DEFAULT 0,
        UNIQUE(chat_id, user_id),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS GameCat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        mood_score INTEGER DEFAULT 0,
        last_play_date TEXT,
        total_plays INTEGER DEFAULT 0,
        UNIQUE(chat_id, user_id),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS HomeOrder (
        chat_id INTEGER PRIMARY KEY,
        order_score INTEGER DEFAULT 50,
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS Duel (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        challenger_id INTEGER NOT NULL,
        opponent_id INTEGER NOT NULL,
        winner_id INTEGER,
        mute_minutes INTEGER DEFAULT 30,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS Roulette (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        participants TEXT,
        loser_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS Quote (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        author_id INTEGER NOT NULL,
        saved_by_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        message_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS TranslatorLog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        trigger_word TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS MuteLog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        reason TEXT,
        muted_until TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS MessageReaction (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        from_user_id INTEGER NOT NULL,
        to_user_id INTEGER,
        emoji TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS MonthlyAward (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        award_type TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        value TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );
    """)

    await db.commit()
