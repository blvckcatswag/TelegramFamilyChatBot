import asyncio
import logging
from datetime import datetime, date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from app.config import settings as cfg
from app.utils.helpers import KYIV_TZ, now_kyiv

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None
_bot = None


def get_scheduler() -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        db_url = cfg.DATABASE_URL
        if db_url.startswith("postgresql") or db_url.startswith("postgres://"):
            # APScheduler SQLAlchemy jobstore needs postgresql+psycopg2://
            sa_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
            if sa_url.startswith("postgresql://"):
                sa_url = sa_url.replace("postgresql://", "postgresql+psycopg2://", 1)
            jobstores = {"default": SQLAlchemyJobStore(url=sa_url)}
        else:
            jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{cfg.DB_PATH}")}
        scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=KYIV_TZ)
    return scheduler


def set_bot(bot):
    global _bot
    _bot = bot


def get_bot():
    return _bot


# ──────────────────── Reminder delivery ────────────────────

async def deliver_reminder(chat_id: int, reminder_id: int, text: str):
    from app.db import repositories as repo

    bot = get_bot()
    if not bot:
        return

    try:
        await bot.send_message(chat_id, f"🔔 <b>Напоминание!</b>\n\n{text}", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to deliver reminder {reminder_id}: {e}")

    await repo.deactivate_reminder(reminder_id)


async def schedule_reminder(reminder_id: int, chat_id: int, text: str, run_at: datetime):
    s = get_scheduler()
    s.add_job(
        deliver_reminder,
        "date",
        run_date=run_at,
        args=[chat_id, reminder_id, text],
        id=f"reminder_{reminder_id}",
        replace_existing=True,
    )


def remove_reminder_job(reminder_id: int):
    s = get_scheduler()
    try:
        s.remove_job(f"reminder_{reminder_id}")
    except Exception:
        pass


# ──────────────────── Weather broadcast ────────────────────

async def broadcast_weather():
    from app.db import repositories as repo
    from app.services.weather.handler import get_weather_for_chat

    bot = get_bot()
    if not bot:
        return

    chats = await repo.get_all_active_chats()
    for chat in chats:
        chat_id = chat["chat_id"]
        try:
            settings = await repo.get_settings(chat_id)
            if not settings.get("weather_enabled"):
                continue

            cities = await repo.get_weather_cities(chat_id)
            if not cities:
                continue

            # Timeout per chat: 30 sec max (even with 5 cities × 10 sec each)
            text = await asyncio.wait_for(get_weather_for_chat(chat_id), timeout=30)
            await bot.send_message(chat_id, f"🌅 <b>Доброе утро!</b>\n\n{text}", parse_mode="HTML")
        except asyncio.TimeoutError:
            logger.warning("Weather broadcast timed out for chat %s", chat_id)
        except Exception as e:
            logger.error("Weather broadcast failed for %s: %s", chat_id, e)


# ──────────────────── Birthday check ────────────────────

async def check_birthdays():
    from app.db import repositories as repo

    bot = get_bot()
    if not bot:
        return

    today = now_kyiv().date()
    tomorrow = today + timedelta(days=1)
    today_str = f"{today.month:02d}-{today.day:02d}"
    tomorrow_str = f"{tomorrow.month:02d}-{tomorrow.day:02d}"

    birthdays = await repo.get_all_birthdays()

    for b in birthdays:
        chat_id = b["chat_id"]
        settings = await repo.get_settings(chat_id)
        if not settings.get("birthdays_enabled"):
            continue

        if b["date"] == today_str and b.get("notified_year") != today.year:
            try:
                await bot.send_message(
                    chat_id,
                    f"🎂🎉 <b>С днём рождения, {b['name']}!</b>\n\n"
                    f"🥳 Поздравляем с праздником!",
                    parse_mode="HTML",
                )
                await repo.update_birthday_notified(b["id"], today.year)
            except Exception as e:
                logger.error(f"Birthday notification failed: {e}")

        elif b["date"] == tomorrow_str:
            try:
                await bot.send_message(
                    chat_id,
                    f"🔔 <b>Завтра день рождения у {b['name']}!</b>\n"
                    f"Не забудьте поздравить! 🎁",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Birthday reminder failed: {e}")


# ──────────────────── Monthly awards ────────────────────

async def monthly_awards_job():
    from app.db import repositories as repo
    from app.services.awards.handler import publish_monthly_awards

    bot = get_bot()
    if not bot:
        return

    chats = await repo.get_all_active_chats()
    for chat in chats:
        try:
            await publish_monthly_awards(bot, chat["chat_id"])
        except Exception as e:
            logger.error(f"Monthly awards failed for {chat['chat_id']}: {e}")


# ──────────────────── Quote of the day ────────────────────

async def quote_of_the_day():
    from app.db import repositories as repo

    bot = get_bot()
    if not bot:
        return

    chats = await repo.get_all_active_chats()
    for chat in chats:
        chat_id = chat["chat_id"]
        settings = await repo.get_settings(chat_id)
        if not settings.get("quotes_enabled"):
            continue

        quote = await repo.get_random_quote(chat_id)
        if not quote:
            continue

        author = quote.get("first_name") or quote.get("username") or "Неизвестный"
        try:
            await bot.send_message(
                chat_id,
                f"🌅 <b>Цитата дня</b>\n\n"
                f"<i>«{quote['text']}»</i>\n— {author}",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ──────────────────── Restore reminders on startup ────────────────────

async def restore_reminders():
    from app.db import repositories as repo

    reminders = await repo.get_all_active_reminders()
    restored = 0

    for r in reminders:
        run_at = datetime.fromisoformat(r["run_at"])
        # Ensure timezone awareness
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=KYIV_TZ)
        if run_at <= now_kyiv():
            # Overdue — deliver immediately
            await deliver_reminder(r["chat_id"], r["id"], r["text"])
        else:
            await schedule_reminder(r["id"], r["chat_id"], r["text"], run_at)
            restored += 1

    logger.info(f"Restored {restored} reminders")


# ──────────────────── Weekly stats broadcast ────────────────────

async def weekly_stats_job():
    from app.db import repositories as repo

    bot = get_bot()
    if not bot:
        return

    def fmt_list(items, val_key, unit):
        if not items:
            return "  — пока никого"
        lines = []
        for i, row in enumerate(items, 1):
            name = row.get("first_name") or row.get("username") or "?"
            val = row.get(val_key, 0)
            lines.append(f"  {i}. {name} — {val} {unit}")
        return "\n".join(lines)

    chats = await repo.get_all_active_chats()
    for chat in chats:
        chat_id = chat["chat_id"]
        try:
            cactus_top = await repo.get_cactus_top(chat_id, 5)
            cat_top = await repo.get_cat_top(chat_id, 5)
            duel_top = await repo.get_duel_top(chat_id, 5)

            text = (
                "📊 <b>Итоги недели</b>\n\n"
                f"<b>🌵 Кактус:</b>\n{fmt_list(cactus_top, 'height_cm', 'см')}\n\n"
                f"<b>🐈 Кот:</b>\n{fmt_list(cat_top, 'mood_score', 'очков')}\n\n"
                f"<b>⚔️ Дуэли:</b>\n{fmt_list(duel_top, 'wins', 'побед')}"
            )
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Weekly stats failed for {chat_id}: {e}")


# ──────────────────── Setup all cron jobs ────────────────────

async def cleanup_message_authors():
    from app.db import repositories as repo
    deleted = await repo.cleanup_old_message_authors()
    logger.info(f"MessageAuthor cleanup: removed {deleted} old records")


async def decay_cat_affinity_job():
    from app.db import repositories as repo
    count = await repo.decay_cat_affinity()
    logger.info(f"Cat affinity decay: affected {count} cats")


async def home_decay_job():
    """Nightly order decay: -20 to -60 points, runs Tue-Sun."""
    from app.db import repositories as repo
    await repo.decay_home_orders(min_decay=20, max_decay=60)
    logger.info("Home order: nightly decay applied")


async def home_weekly_reset_job():
    """Monday reset: set all home orders to 20 (weekend mess)."""
    from app.db import repositories as repo
    await repo.reset_home_orders(score=20)
    logger.info("Home order: weekly reset to 20")


# ──────────────────── Roulette timeouts ────────────────────

async def roulette_collect_timeout(chat_id: int):
    """Called by scheduler when collection phase expires."""
    from app.services.games.roulette import handle_collect_timeout
    bot = get_bot()
    if not bot:
        return
    await handle_collect_timeout(chat_id, bot)


async def roulette_turn_timeout(chat_id: int):
    """Called by scheduler when current player's turn expires."""
    from app.services.games.roulette import handle_turn_timeout
    bot = get_bot()
    if not bot:
        return
    await handle_turn_timeout(chat_id, bot)


def schedule_roulette_collect(chat_id: int, seconds: int = 60):
    s = get_scheduler()
    run_at = now_kyiv() + timedelta(seconds=seconds)
    s.add_job(
        roulette_collect_timeout,
        "date",
        run_date=run_at,
        args=[chat_id],
        id=f"roulette_collect_{chat_id}",
        replace_existing=True,
    )


def schedule_roulette_turn(chat_id: int, seconds: int = 60):
    s = get_scheduler()
    run_at = now_kyiv() + timedelta(seconds=seconds)
    s.add_job(
        roulette_turn_timeout,
        "date",
        run_date=run_at,
        args=[chat_id],
        id=f"roulette_turn_{chat_id}",
        replace_existing=True,
    )


def cancel_roulette_job(chat_id: int, kind: str = "collect"):
    s = get_scheduler()
    try:
        s.remove_job(f"roulette_{kind}_{chat_id}")
    except Exception:
        pass


async def restore_active_roulettes():
    """Restore roulette games after bot restart."""
    from app.db import repositories as repo
    from app.services.games.roulette import handle_collect_timeout, handle_turn_timeout

    bot = get_bot()
    if not bot:
        return

    games = await repo.get_all_active_roulettes()
    restored = 0

    for game in games:
        chat_id = game["chat_id"]
        phase = game["phase"]

        if phase == "collecting":
            created = game["created_at"]
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            if created.tzinfo is None:
                created = created.replace(tzinfo=KYIV_TZ)
            elapsed = (now_kyiv() - created).total_seconds()
            remaining = max(1, 60 - int(elapsed))
            if elapsed >= 60:
                await handle_collect_timeout(chat_id, bot)
            else:
                schedule_roulette_collect(chat_id, remaining)
                restored += 1
        elif phase == "playing":
            # Player had their chance during downtime — immediate timeout
            await handle_turn_timeout(chat_id, bot)
            restored += 1

    logger.info("Restored %d active roulette games", restored)


def setup_cron_jobs():
    s = get_scheduler()

    # Weather broadcast — every day at configured time (Kyiv time)
    h, m = map(int, cfg.DEFAULT_WEATHER_TIME.split(":"))
    s.add_job(broadcast_weather, "cron", hour=h, minute=m, id="weather_broadcast", replace_existing=True)

    # Birthday check — every day at 08:00 Kyiv
    s.add_job(check_birthdays, "cron", hour=8, minute=0, id="birthday_check", replace_existing=True)

    # Monthly awards — last day of month at 20:00 Kyiv
    s.add_job(monthly_awards_job, "cron", day="last", hour=20, minute=0,
              id="monthly_awards", replace_existing=True)

    # Quote of the day — every day at 09:00 Kyiv
    s.add_job(quote_of_the_day, "cron", hour=9, minute=0, id="quote_of_day", replace_existing=True)

    # Cleanup old MessageAuthor records (older than 30 days) — every 1st of month at 03:00 Kyiv
    s.add_job(cleanup_message_authors, "cron", day=1, hour=3, minute=0,
              id="cleanup_message_authors", replace_existing=True)

    # Cat affinity decay — every day at 00:05 Kyiv (decrease affinity for inactive cats)
    s.add_job(decay_cat_affinity_job, "cron", hour=0, minute=5,
              id="cat_affinity_decay", replace_existing=True)

    # Weekly stats — every Sunday at 23:55 Kyiv
    s.add_job(weekly_stats_job, "cron", day_of_week="sun", hour=23, minute=55,
              id="weekly_stats", replace_existing=True)

    # Home order: nightly decay Tue-Sun at 01:00 Kyiv
    s.add_job(home_decay_job, "cron", day_of_week="tue-sun", hour=1, minute=0,
              id="home_decay", replace_existing=True)

    # Home order: Monday reset at 00:05 Kyiv (weekend chaos = 20%)
    s.add_job(home_weekly_reset_job, "cron", day_of_week="mon", hour=0, minute=5,
              id="home_weekly_reset", replace_existing=True)
