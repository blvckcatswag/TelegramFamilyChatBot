import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeAllGroupChats

import sentry_sdk
from app.config.logging_config import setup_logging
from app.config import settings as cfg
from app.config.settings import BOT_TOKEN
from app.db.database import init_db, close_db
from app.bot.middleware import RegisterMiddleware, SentryContextMiddleware
from app.bot.error_handler import router as error_router
from app.bot.handlers_core import router as core_router
from app.services.games.cactus import router as cactus_router
from app.services.games.cat import router as cat_router
from app.services.games.duel import router as duel_router
from app.services.games.roulette import router as roulette_router
from app.services.games.blackjack import router as blackjack_router
from app.services.games.home import router as home_router
from app.services.reminders.handler import router as reminders_router
from app.services.weather.handler import router as weather_router
from app.services.quotes.handler import router as quotes_router
from app.services.translator.handler import router as translator_router
from app.services.birthdays.handler import router as birthdays_router
from app.services.reactions.handler import router as reactions_router
from app.services.awards.handler import router as awards_router
from app.services.admin.handler import router as admin_router
from app.services.feedback.handler import router as feedback_router
from app.services.feedback.export import router as feedback_export_router
from app.services.donate.handler import router as donate_router
from app.bot.handlers.reply_keyboards import router as reply_kb_router
from app.scheduler.jobs import get_scheduler, set_bot, setup_cron_jobs, restore_reminders

setup_logging()
logger = logging.getLogger(__name__)

if cfg.SENTRY_DSN:
    import re

    _token_re = re.compile(r"bot\d+:[A-Za-z0-9_-]+")

    def _scrub_token(event, hint):
        """Remove bot token from all URLs in the event before sending to Sentry."""
        raw = str(event)
        if "api.telegram.org" in raw:
            import json
            event_str = _token_re.sub("bot[REDACTED]", json.dumps(event))
            event = json.loads(event_str)
        return event

    sentry_sdk.init(
        dsn=cfg.SENTRY_DSN,
        traces_sample_rate=0,   # disable performance tracing — it logs HTTP URLs with token
        environment="production",
        before_send=_scrub_token,
        before_send_transaction=_scrub_token,
    )
    logger.info("Sentry initialized.")

BOT_COMMANDS = [
    BotCommand(command="menu", description="Главное меню"),
    BotCommand(command="help", description="Список команд"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
    BotCommand(command="cactus", description="Полить кактус"),
    BotCommand(command="cat", description="Покормить кота"),
    BotCommand(command="cat_pet", description="Погладить кота"),
    BotCommand(command="cat_play", description="Поиграть с котом"),
    BotCommand(command="home", description="Порядок дома"),
    BotCommand(command="duel", description="Вызвать на дуэль"),
    BotCommand(command="roulette", description="Русская рулетка"),
    BotCommand(command="blackjack", description="Блэкджек"),
    BotCommand(command="weekly", description="Недельные кредиты"),
    BotCommand(command="balance", description="Баланс кредитов"),
    BotCommand(command="top_blackjack", description="Топ игроков по кредитам"),
    BotCommand(command="remind", description="Создать напоминание"),
    BotCommand(command="reminders", description="Мои напоминания"),
    BotCommand(command="weather", description="Погода сейчас"),
    BotCommand(command="quote", description="Сохранить цитату (reply)"),
    BotCommand(command="quote_random", description="Случайная цитата"),
    BotCommand(command="mystats", description="Личная статистика"),
    BotCommand(command="top", description="Таблица лидеров"),
    BotCommand(command="birthdays", description="Дни рождения"),
    BotCommand(command="status", description="Диагностика бота"),
    BotCommand(command="feedback", description="Написать разработчику"),
    BotCommand(command="donate", description="Поддержать разработчика"),
]


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set! Check your .env file.")
        return

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Register middleware
    dp.message.middleware(SentryContextMiddleware())
    dp.callback_query.middleware(SentryContextMiddleware())
    dp.message.middleware(RegisterMiddleware())
    dp.callback_query.middleware(RegisterMiddleware())

    # Include routers (order matters — admin and core first, translator last)
    # reply_kb_router must come before all FSM routers so that pressing a nav
    # button while in any FSM state is intercepted here first (middleware clears
    # the state), and never falls through to a waiting FSM handler.
    dp.include_router(error_router)
    dp.include_router(admin_router)
    dp.include_router(core_router)
    dp.include_router(reply_kb_router)
    dp.include_router(cactus_router)
    dp.include_router(cat_router)
    dp.include_router(duel_router)
    dp.include_router(roulette_router)
    dp.include_router(blackjack_router)
    dp.include_router(home_router)
    dp.include_router(reminders_router)
    dp.include_router(weather_router)
    dp.include_router(quotes_router)
    dp.include_router(birthdays_router)
    dp.include_router(reactions_router)
    dp.include_router(awards_router)
    dp.include_router(feedback_router)
    dp.include_router(feedback_export_router)
    dp.include_router(donate_router)
    # Translator must be last — it catches all text messages
    dp.include_router(translator_router)

    # Init database
    await init_db()
    logger.info("Database initialized.")

    # Register bot commands for input bar menu
    await bot.set_my_commands(BOT_COMMANDS)
    await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeAllGroupChats())
    if cfg.SUPERADMIN_ID:
        superadmin_commands = BOT_COMMANDS + [
            BotCommand(command="backlog", description="Беклог обращений"),
            BotCommand(command="export_bugs", description="Экспорт фидбека в HTML"),
        ]
        await bot.set_my_commands(superadmin_commands, scope=BotCommandScopeChat(chat_id=cfg.SUPERADMIN_ID))
    logger.info("Bot commands registered.")

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
