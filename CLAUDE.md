# Claude Code — Project Rules

## Git Workflow
- **NEVER commit directly to `main`**. Always create a feature branch.
- Branch naming: `branch{N}_{context}` (e.g., `branch1_fixes`, `branch2_feature_weather`).
- Merge to `main` only after user approval.
- Write clear commit messages in English.

## Code Style
- **Python 3.11+ compatibility** — do NOT use features exclusive to 3.12+.
- **UTF-8 strings only** — never use `\uXXXX` unicode escape sequences for Cyrillic or emoji. Write readable text: `"Привет"`, not `"\u041f\u0440\u0438\u0432\u0435\u0442"`.
- Use f-strings for formatting. No backslashes inside f-string expressions (Python 3.11 restriction).
- Type hints: use `X | None` syntax (PEP 604), which works in 3.11.

## Timezone
- **All times are in Europe/Kiev** (Kyiv timezone).
- Use `now_kyiv()` from `app.utils.helpers` instead of `datetime.utcnow()`.
- APScheduler is configured with `timezone=KYIV_TZ`.
- When storing/reading datetimes, handle naive datetimes from old DB records gracefully.

## Attribution
- **NEVER** add `Co-Authored-By`, `Generated with Claude`, or any other Claude/AI mentions to commits, PRs, or code.
- No watermarks, credits, or attribution lines of any kind.

## Architecture
- Entry point: `main.py`.
- Config: `app/config/settings.py` (loads `.env`).
- DB: PostgreSQL (prod) via asyncpg, SQLite (dev/tests) via aiosqlite. Dual-mode `Database` class in `app/db/database.py`. Singleton `get_db()`. CRUD in `app/db/repositories.py`.
- All SQL uses `$1, $2` placeholders (auto-converted to `?` for SQLite).
- Scheduler: APScheduler with SQLAlchemy jobstore. Jobs in `app/scheduler/jobs.py`.
- Translator handler must be registered **LAST** (catches all text messages).

## Deployment
- Deployed on **Railway** with **Python 3.11**.
- Environment variables via Railway dashboard / `.env` locally.
- Production DB: PostgreSQL on Railway (`DATABASE_URL` env var).
- Local dev: SQLite `bot.db` (in `.gitignore`).

## Game Muting
- Before muting any user, check if they are a chat creator or admin using `can_mute_user()`.
- If the user can't be muted, show an informational message instead of failing silently.

## Testing
- Tests in `tests/test_bot.py`. Run with `pytest`.
- Tests use SQLite. Fixture overrides `cfg.DATABASE_URL` for isolation.
