"""
Unified database layer: PostgreSQL (asyncpg) for production, SQLite (aiosqlite) for dev/tests.

All queries use $1, $2 style placeholders. For SQLite they are auto-converted to ?.
"""
import re
import logging

logger = logging.getLogger(__name__)

_db: "Database | None" = None


class Database:
    def __init__(self):
        self._pg_pool = None
        self._sqlite = None
        self._is_postgres = False

    @property
    def is_postgres(self) -> bool:
        return self._is_postgres

    async def connect(self, url: str):
        if url.startswith("postgresql") or url.startswith("postgres://"):
            import asyncpg
            self._pg_pool = await asyncpg.create_pool(url, min_size=2, max_size=10)
            self._is_postgres = True
            logger.info("Connected to PostgreSQL")
        else:
            import aiosqlite
            path = url.replace("sqlite:///", "")
            self._sqlite = await aiosqlite.connect(path)
            self._sqlite.row_factory = aiosqlite.Row
            await self._sqlite.execute("PRAGMA journal_mode=WAL")
            await self._sqlite.execute("PRAGMA foreign_keys=ON")
            logger.info(f"Connected to SQLite: {path}")

    async def close(self):
        if self._pg_pool:
            await self._pg_pool.close()
            self._pg_pool = None
        if self._sqlite:
            await self._sqlite.close()
            self._sqlite = None

    def _q(self, query: str, args: tuple = ()) -> tuple[str, tuple]:
        """Convert $1,$2 placeholders to ? for SQLite, expanding args for reused params."""
        if self._is_postgres:
            return query, args
        refs = re.findall(r'\$(\d+)', query)
        if not refs:
            return query, args
        new_args = tuple(args[int(ref) - 1] for ref in refs)
        new_query = re.sub(r'\$\d+', '?', query)
        return new_query, new_args

    async def fetch(self, query: str, *args) -> list[dict]:
        """Fetch multiple rows as list of dicts."""
        query, args = self._q(query, args)
        if self._is_postgres:
            async with self._pg_pool.acquire() as conn:
                rows = await conn.fetch(query, *args)
                return [dict(r) for r in rows]
        else:
            cursor = await self._sqlite.execute(query, args)
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(r) for r in rows]

    async def fetchrow(self, query: str, *args) -> dict | None:
        """Fetch single row as dict or None."""
        query, args = self._q(query, args)
        if self._is_postgres:
            async with self._pg_pool.acquire() as conn:
                row = await conn.fetchrow(query, *args)
                return dict(row) if row else None
        else:
            cursor = await self._sqlite.execute(query, args)
            row = await cursor.fetchone()
            await cursor.close()
            return dict(row) if row else None

    async def fetchval(self, query: str, *args):
        """Fetch single value from first column of first row."""
        query, args = self._q(query, args)
        if self._is_postgres:
            async with self._pg_pool.acquire() as conn:
                return await conn.fetchval(query, *args)
        else:
            cursor = await self._sqlite.execute(query, args)
            row = await cursor.fetchone()
            await cursor.close()
            return row[0] if row else None

    async def execute(self, query: str, *args) -> int | None:
        """Execute query. For INSERT RETURNING, returns the id."""
        query, args = self._q(query, args)
        if self._is_postgres:
            async with self._pg_pool.acquire() as conn:
                if "RETURNING" in query.upper():
                    return await conn.fetchval(query, *args)
                await conn.execute(query, *args)
                return None
        else:
            # Strip RETURNING clause for SQLite — use lastrowid instead
            if "RETURNING" in query.upper():
                query = re.sub(r'\s+RETURNING\s+\S+', '', query, flags=re.IGNORECASE)
            cursor = await self._sqlite.execute(query, args)
            await cursor.close()
            await self._sqlite.commit()
            return cursor.lastrowid

    async def execute_many(self, query: str, args_list: list):
        """Execute query multiple times with different args."""
        if self._is_postgres:
            async with self._pg_pool.acquire() as conn:
                await conn.executemany(query, args_list)
        else:
            converted_query, _ = self._q(query)
            refs = re.findall(r'\$(\d+)', query)
            if refs:
                new_args_list = [
                    tuple(row[int(ref) - 1] for ref in refs) for row in args_list
                ]
            else:
                new_args_list = args_list
            await self._sqlite.executemany(converted_query, new_args_list)
            await self._sqlite.commit()

    async def execute_script(self, script: str):
        """Execute raw DDL script (used only for init_db)."""
        if self._is_postgres:
            async with self._pg_pool.acquire() as conn:
                await conn.execute(script)
        else:
            await self._sqlite.executescript(script)
            await self._sqlite.commit()


async def get_db() -> Database:
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def init_db(url: str | None = None) -> None:
    global _db
    if _db is not None:
        return

    from app.config import settings as cfg
    db_url = url or cfg.DATABASE_URL

    _db = Database()
    await _db.connect(db_url)

    if _db.is_postgres:
        await _init_postgres(_db)
        await _run_migrations(_db)
    else:
        await _init_sqlite(_db)


async def _run_migrations(db: Database):
    """Add columns to existing tables (safe to run multiple times)."""
    migrations = [
        "ALTER TABLE MessageAuthor ADD COLUMN IF NOT EXISTS text TEXT",
        "ALTER TABLE MessageAuthor ADD COLUMN IF NOT EXISTS media_type VARCHAR(20)",
        "ALTER TABLE Quote ADD COLUMN IF NOT EXISTS category VARCHAR(10) NOT NULL DEFAULT '⭐'",
        "ALTER TABLE Quote ADD COLUMN IF NOT EXISTS media_type VARCHAR(20)",
        "ALTER TABLE Quote ALTER COLUMN text DROP NOT NULL",
        "ALTER TABLE GameCactus ADD COLUMN IF NOT EXISTS waters_today INTEGER DEFAULT 0",
        "ALTER TABLE GameCat ADD COLUMN IF NOT EXISTS affinity INTEGER DEFAULT 25",
        "ALTER TABLE GameCat ADD COLUMN IF NOT EXISTS last_feed_date TEXT",
        "ALTER TABLE GameCat ADD COLUMN IF NOT EXISTS last_pet_date TEXT",
        "ALTER TABLE GameCat ADD COLUMN IF NOT EXISTS last_played_date TEXT",
        "ALTER TABLE GameCat ADD COLUMN IF NOT EXISTS actions_today INTEGER DEFAULT 0",
    ]
    for sql in migrations:
        try:
            await db.execute(sql)
        except Exception:
            pass
    try:
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_quote_msg_cat ON Quote (chat_id, message_id, category)"
        )
    except Exception:
        pass
    # HomeActions table (added in v3)
    try:
        await db.execute_script("""
            CREATE TABLE IF NOT EXISTS HomeActions (
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                action TEXT NOT NULL,
                date TEXT NOT NULL,
                PRIMARY KEY (chat_id, user_id, action, date)
            );
        """)
    except Exception:
        pass

    # BlackjackProfile table (added in v2)
    try:
        await db.execute_script("""
            CREATE TABLE IF NOT EXISTS BlackjackProfile (
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                balance INTEGER NOT NULL DEFAULT 5000,
                total_games INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                draws INTEGER NOT NULL DEFAULT 0,
                max_balance INTEGER NOT NULL DEFAULT 5000,
                last_weekly TEXT,
                UNIQUE(chat_id, user_id)
            );
        """)
    except Exception:
        pass


async def _init_postgres(db: Database):
    await db.execute_script("""
    CREATE TABLE IF NOT EXISTS Chat (
        chat_id BIGINT PRIMARY KEY,
        title TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        is_banned BOOLEAN DEFAULT FALSE,
        owner_user_id BIGINT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS "User" (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        chat_id BIGINT NOT NULL,
        username TEXT,
        first_name TEXT,
        role TEXT DEFAULT 'user',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(user_id, chat_id),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS Settings (
        chat_id BIGINT PRIMARY KEY,
        weather_enabled BOOLEAN DEFAULT TRUE,
        weather_time TEXT DEFAULT '07:00',
        translator_enabled BOOLEAN DEFAULT TRUE,
        games_enabled BOOLEAN DEFAULT TRUE,
        birthdays_enabled BOOLEAN DEFAULT TRUE,
        quotes_enabled BOOLEAN DEFAULT TRUE,
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS WeatherCity (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        city_name TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(chat_id, city_name),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS Reminder (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        text TEXT NOT NULL,
        type TEXT DEFAULT 'once',
        run_at TEXT NOT NULL,
        rrule TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS Birthday (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        name TEXT NOT NULL,
        date TEXT NOT NULL,
        notified_year INTEGER DEFAULT 0,
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS GameCactus (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        height_cm INTEGER DEFAULT 0,
        last_play_date TEXT,
        total_plays INTEGER DEFAULT 0,
        waters_today INTEGER DEFAULT 0,
        UNIQUE(chat_id, user_id),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS GameCat (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        mood_score INTEGER DEFAULT 0,
        last_play_date TEXT,
        total_plays INTEGER DEFAULT 0,
        affinity INTEGER DEFAULT 25,
        last_feed_date TEXT,
        last_pet_date TEXT,
        last_played_date TEXT,
        actions_today INTEGER DEFAULT 0,
        UNIQUE(chat_id, user_id),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS HomeOrder (
        chat_id BIGINT PRIMARY KEY,
        order_score INTEGER DEFAULT 50,
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS HomeActions (
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        action TEXT NOT NULL,
        date TEXT NOT NULL,
        PRIMARY KEY (chat_id, user_id, action, date)
    );

    CREATE TABLE IF NOT EXISTS Duel (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        challenger_id BIGINT NOT NULL,
        opponent_id BIGINT NOT NULL,
        winner_id BIGINT,
        mute_minutes INTEGER DEFAULT 30,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS Roulette (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        participants TEXT,
        loser_id BIGINT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS Quote (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        author_id BIGINT NOT NULL,
        saved_by_id BIGINT NOT NULL,
        text TEXT,
        message_id BIGINT,
        category VARCHAR(10) NOT NULL DEFAULT '⭐',
        media_type VARCHAR(20),
        created_at TIMESTAMPTZ DEFAULT NOW(),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS TranslatorLog (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        trigger_word TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS MuteLog (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        reason TEXT,
        muted_until TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS MessageReaction (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        message_id BIGINT NOT NULL,
        from_user_id BIGINT NOT NULL,
        to_user_id BIGINT,
        emoji TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS MonthlyAward (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        award_type TEXT NOT NULL,
        user_id BIGINT NOT NULL,
        value TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS MessageAuthor (
        chat_id BIGINT NOT NULL,
        message_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        text TEXT,
        media_type VARCHAR(20),
        created_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (chat_id, message_id)
    );

    CREATE TABLE IF NOT EXISTS Feedback (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        chat_id BIGINT NOT NULL,
        username TEXT,
        category TEXT NOT NULL,
        text TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS BlackjackProfile (
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        balance INTEGER NOT NULL DEFAULT 5000,
        total_games INTEGER NOT NULL DEFAULT 0,
        wins INTEGER NOT NULL DEFAULT 0,
        losses INTEGER NOT NULL DEFAULT 0,
        draws INTEGER NOT NULL DEFAULT 0,
        max_balance INTEGER NOT NULL DEFAULT 5000,
        last_weekly TEXT,
        UNIQUE(chat_id, user_id)
    );
    """)


async def _init_sqlite(db: Database):
    await db.execute_script("""
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
        weather_time TEXT DEFAULT '07:00',
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
        waters_today INTEGER DEFAULT 0,
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
        affinity INTEGER DEFAULT 25,
        last_feed_date TEXT,
        last_pet_date TEXT,
        last_played_date TEXT,
        actions_today INTEGER DEFAULT 0,
        UNIQUE(chat_id, user_id),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS HomeOrder (
        chat_id INTEGER PRIMARY KEY,
        order_score INTEGER DEFAULT 50,
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id)
    );

    CREATE TABLE IF NOT EXISTS HomeActions (
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        date TEXT NOT NULL,
        PRIMARY KEY (chat_id, user_id, action, date)
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
        text TEXT,
        message_id INTEGER,
        category TEXT NOT NULL DEFAULT '⭐',
        media_type TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (chat_id) REFERENCES Chat(chat_id),
        UNIQUE(chat_id, message_id, category)
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

    CREATE TABLE IF NOT EXISTS MessageAuthor (
        chat_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        text TEXT,
        media_type TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (chat_id, message_id)
    );

    CREATE TABLE IF NOT EXISTS Feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        chat_id INTEGER NOT NULL,
        username TEXT,
        category TEXT NOT NULL,
        text TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS BlackjackProfile (
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        balance INTEGER NOT NULL DEFAULT 5000,
        total_games INTEGER NOT NULL DEFAULT 0,
        wins INTEGER NOT NULL DEFAULT 0,
        losses INTEGER NOT NULL DEFAULT 0,
        draws INTEGER NOT NULL DEFAULT 0,
        max_balance INTEGER NOT NULL DEFAULT 5000,
        last_weekly TEXT,
        UNIQUE(chat_id, user_id)
    );
    """)
