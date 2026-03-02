import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from app.config.settings import BOT_TOKEN
from app.db.database import init_db, close_db
from app.bot.middleware import RegisterMiddleware
from app.bot.handlers_core import router as core_router
from app.services.games.cactus import router as cactus_router
from app.services.games.cat import router as cat_router
from app.services.games.duel import router as duel_router
from app.services.games.roulette import router as roulette_router
from app.services.reminders.handler import router as reminders_router
from app.services.weather.handler import router as weather_router
from app.services.quotes.handler import router as quotes_router
from app.services.translator.handler import router as translator_router
from app.services.birthdays.handler import router as birthdays_router
from app.services.reactions.handler import router as reactions_router
from app.services.awards.handler import router as awards_router
from app.services.admin.handler import router as admin_router
from app.scheduler.jobs import get_scheduler, set_bot, setup_cron_jobs, restore_reminders

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set! Check your .env file.")
        return

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Register middleware
    dp.message.middleware(RegisterMiddleware())
    dp.callback_query.middleware(RegisterMiddleware())

    # Include routers (order matters — admin and core first, translator last)
    dp.include_router(admin_router)
    dp.include_router(core_router)
    dp.include_router(cactus_router)
    dp.include_router(cat_router)
    dp.include_router(duel_router)
    dp.include_router(roulette_router)
    dp.include_router(reminders_router)
    dp.include_router(weather_router)
    dp.include_router(quotes_router)
    dp.include_router(birthdays_router)
    dp.include_router(reactions_router)
    dp.include_router(awards_router)
    # Translator must be last — it catches all text messages
    dp.include_router(translator_router)

    # Init database
    await init_db()
    logger.info("Database initialized.")

    # Setup scheduler
    set_bot(bot)
    scheduler = get_scheduler()
    setup_cron_jobs()
    await restore_reminders()
    scheduler.start()
    logger.info("Scheduler started.")

    # Start polling
    logger.info("Bot is starting...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await close_db()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
