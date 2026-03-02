import logging
from datetime import datetime, date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from app.config import settings as cfg

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None
_bot = None


def get_scheduler() -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        jobstores = {
            "default": SQLAlchemyJobStore(url=f"sqlite:///{cfg.DB_PATH}")
        }
        scheduler = AsyncIOScheduler(jobstores=jobstores)
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
        await bot.send_message(chat_id, f"\U0001f514 <b>\u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435!</b>\n\n{text}", parse_mode="HTML")
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
        settings = await repo.get_settings(chat_id)
        if not settings.get("weather_enabled"):
            continue

        cities = await repo.get_weather_cities(chat_id)
        if not cities:
            continue

        text = await get_weather_for_chat(chat_id)
        try:
            await bot.send_message(chat_id, f"\U0001f305 <b>\u0414\u043e\u0431\u0440\u043e\u0435 \u0443\u0442\u0440\u043e!</b>\n\n{text}", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Weather broadcast failed for {chat_id}: {e}")


# ──────────────────── Birthday check ────────────────────

async def check_birthdays():
    from app.db import repositories as repo

    bot = get_bot()
    if not bot:
        return

    today = date.today()
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
                    f"\U0001f382\U0001f389 <b>\u0421 \u0434\u043d\u0451\u043c \u0440\u043e\u0436\u0434\u0435\u043d\u0438\u044f, {b['name']}!</b>\n\n"
                    f"\U0001f973 \u041f\u043e\u0437\u0434\u0440\u0430\u0432\u043b\u044f\u0435\u043c \u0441 \u043f\u0440\u0430\u0437\u0434\u043d\u0438\u043a\u043e\u043c!",
                    parse_mode="HTML",
                )
                await repo.update_birthday_notified(b["id"], today.year)
            except Exception as e:
                logger.error(f"Birthday notification failed: {e}")

        elif b["date"] == tomorrow_str:
            try:
                await bot.send_message(
                    chat_id,
                    f"\U0001f514 <b>\u0417\u0430\u0432\u0442\u0440\u0430 \u0434\u0435\u043d\u044c \u0440\u043e\u0436\u0434\u0435\u043d\u0438\u044f \u0443 {b['name']}!</b>\n"
                    f"\u041d\u0435 \u0437\u0430\u0431\u0443\u0434\u044c\u0442\u0435 \u043f\u043e\u0437\u0434\u0440\u0430\u0432\u0438\u0442\u044c! \U0001f381",
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

        author = quote.get("first_name") or quote.get("username") or "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439"
        try:
            await bot.send_message(
                chat_id,
                f"\U0001f305 <b>\u0426\u0438\u0442\u0430\u0442\u0430 \u0434\u043d\u044f</b>\n\n"
                f"<i>\u00ab{quote['text']}\u00bb</i>\n\u2014 {author}",
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
        if run_at <= datetime.utcnow():
            # Overdue — deliver immediately
            await deliver_reminder(r["chat_id"], r["id"], r["text"])
        else:
            await schedule_reminder(r["id"], r["chat_id"], r["text"], run_at)
            restored += 1

    logger.info(f"Restored {restored} reminders")


# ──────────────────── Setup all cron jobs ────────────────────

def setup_cron_jobs():
    s = get_scheduler()

    # Weather broadcast — every day at configured time
    h, m = map(int, cfg.DEFAULT_WEATHER_TIME.split(":"))
    s.add_job(broadcast_weather, "cron", hour=h, minute=m, id="weather_broadcast", replace_existing=True)

    # Birthday check — every day at 08:00
    s.add_job(check_birthdays, "cron", hour=8, minute=0, id="birthday_check", replace_existing=True)

    # Monthly awards — last day of month at 20:00
    s.add_job(monthly_awards_job, "cron", day="last", hour=20, minute=0,
              id="monthly_awards", replace_existing=True)

    # Quote of the day — every day at 09:00
    s.add_job(quote_of_the_day, "cron", hour=9, minute=0, id="quote_of_day", replace_existing=True)
