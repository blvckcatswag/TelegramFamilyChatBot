import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message


class _DeleteTriggerMiddleware(BaseMiddleware):
    """Удаляет сообщение с кнопкой после обработки и сбрасывает активный FSM-флоу.

    Сброс состояния нужен чтобы нажатие любой кнопки навигации прерывало
    текущий ввод (напоминание, фидбек, донат, дни рождения и тд).
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        state: FSMContext = data.get("state")
        if state and await state.get_state() is not None:
            await state.clear()

        result = await handler(event, data)
        try:
            await event.delete()
        except Exception:
            pass
        return result


from app.bot.keyboards import settings_kb, weather_cities_delete_kb
from app.config.settings import SUPERADMIN_ID
from app.db import repositories as repo
from app.services.games.cactus import play_cactus
from app.services.games.cat import play_cat, cmd_home
from app.services.games.roulette import cmd_roulette
from app.services.reminders.handler import cmd_remind, cmd_reminders
from app.services.weather.handler import get_weather_for_chat, WeatherAddCity
from app.services.awards.handler import cmd_awards
from app.services.feedback.handler import cmd_feedback
from app.services.donate.handler import cmd_donate
from app.utils.reply_keyboards import (
    kb_start, kb_menu, kb_games, kb_reminders,
    kb_weather, kb_quotes, kb_stats, kb_help,
)

router = Router()
router.message.middleware(_DeleteTriggerMiddleware())
logger = logging.getLogger(__name__)

# ── Navigation ──────────────────────────────────────────────────────


@router.message(F.text == "📋 Меню")
async def handle_menu(message: Message):
    logger.info("Reply KB: 📋 Меню — user=%s", message.from_user.id)
    await message.answer(
        "📋 <b>Главное меню</b>\n\nВыбери раздел:",
        reply_markup=kb_menu(), parse_mode="HTML",
    )


@router.message(F.text == "◀️ На главную")
async def handle_back_to_start(message: Message):
    logger.info("Reply KB: ◀️ На главную — user=%s", message.from_user.id)
    await message.answer(
        "🤖 <b>Главный экран</b>\n\nВыбери что делать:",
        reply_markup=kb_start(), parse_mode="HTML",
    )


@router.message(F.text == "◀️ Назад")
async def handle_back_to_menu(message: Message):
    logger.info("Reply KB: ◀️ Назад — user=%s", message.from_user.id)
    await message.answer(
        "📋 <b>Главное меню</b>\n\nВыбери раздел:",
        reply_markup=kb_menu(), parse_mode="HTML",
    )


# ── Level 1 → Level 2 navigation ───────────────────────────────────


@router.message(F.text == "🎮 Игры")
async def handle_games(message: Message):
    logger.info("Reply KB: 🎮 Игры — user=%s", message.from_user.id)
    await message.answer(
        "🎮 <b>Игры</b>\n\nВыбери игру:",
        reply_markup=kb_games(), parse_mode="HTML",
    )


@router.message(F.text == "📅 Напоминания")
async def handle_reminders_menu(message: Message):
    logger.info("Reply KB: 📅 Напоминания — user=%s", message.from_user.id)
    await message.answer(
        "📅 <b>Напоминания</b>\n\nУправление напоминаниями:",
        reply_markup=kb_reminders(), parse_mode="HTML",
    )


@router.message(F.text == "🌤️ Погода")
async def handle_weather_menu(message: Message):
    logger.info("Reply KB: 🌤️ Погода — user=%s", message.from_user.id)
    await message.answer(
        "🌤️ <b>Погода</b>\n\nУправление погодой:",
        reply_markup=kb_weather(), parse_mode="HTML",
    )


@router.message(F.text == "💬 Цитаты")
async def handle_quotes_menu(message: Message):
    logger.info("Reply KB: 💬 Цитаты — user=%s", message.from_user.id)
    await message.answer(
        "💬 <b>Цитатник</b>\n\nВыбери раздел:",
        reply_markup=kb_quotes(), parse_mode="HTML",
    )


@router.message(F.text == "📊 Статистика")
async def handle_stats_menu(message: Message):
    logger.info("Reply KB: 📊 Статистика — user=%s", message.from_user.id)
    await message.answer(
        "📊 <b>Статистика</b>\n\nВыбери что смотреть:",
        reply_markup=kb_stats(), parse_mode="HTML",
    )


@router.message(F.text == "ℹ️ Справка")
async def handle_help_menu(message: Message):
    logger.info("Reply KB: ℹ️ Справка — user=%s", message.from_user.id)
    await message.answer(
        "ℹ️ <b>Справка</b>\n\nВыбери раздел:",
        reply_markup=kb_help(), parse_mode="HTML",
    )


@router.message(F.text == "📣 Фидбек")
async def handle_feedback(message: Message, state: FSMContext):
    logger.info("Reply KB: 📣 Фидбек — user=%s", message.from_user.id)
    await cmd_feedback(message, state)


@router.message(F.text == "💝 Поддержать")
async def handle_donate(message: Message):
    logger.info("Reply KB: 💝 Поддержать — user=%s", message.from_user.id)
    await cmd_donate(message)


@router.message(F.text == "⚙️ Настройки")
async def handle_settings(message: Message):
    logger.info("Reply KB: ⚙️ Настройки — user=%s", message.from_user.id)
    chat_id = message.chat.id
    user_id = message.from_user.id
    role = await repo.get_user_role(user_id, chat_id)
    if role != "owner" and user_id != SUPERADMIN_ID:
        await message.answer(
            "❌ Настройки доступны только владельцу чата.",
            reply_markup=kb_menu(),
        )
        return
    settings = await repo.get_settings(chat_id)
    await message.answer(
        "⚙️ <b>Настройки чата</b>\n\nНажми кнопку для переключения модуля:",
        reply_markup=settings_kb(settings), parse_mode="HTML",
    )


# ── Games ───────────────────────────────────────────────────────────


@router.message(F.text == "🌵 Кактус")
async def handle_cactus(message: Message, bot: Bot):
    logger.info("Reply KB: 🌵 Кактус — user=%s", message.from_user.id)
    await play_cactus(message, bot)


@router.message(F.text == "🐈 Кот")
async def handle_cat(message: Message, bot: Bot):
    logger.info("Reply KB: 🐈 Кот — user=%s", message.from_user.id)
    await play_cat(message, bot)


@router.message(F.text == "⚔️ Дуэль")
async def handle_duel(message: Message):
    logger.info("Reply KB: ⚔️ Дуэль — user=%s", message.from_user.id)
    await message.answer(
        "⚔️ <b>Дуэль</b>\n\n"
        "Чтобы вызвать кого-то на дуэль, напиши команду:\n"
        "<code>/duel @username [минуты]</code>\n\n"
        "Пример: <code>/duel @Masha 5</code>",
        reply_markup=kb_games(), parse_mode="HTML",
    )


@router.message(F.text == "🔫 Рулетка")
async def handle_roulette(message: Message, bot: Bot):
    logger.info("Reply KB: 🔫 Рулетка — user=%s", message.from_user.id)
    await cmd_roulette(message, bot)


@router.message(F.text == "🧹 Порядок")
async def handle_home(message: Message):
    logger.info("Reply KB: 🧹 Порядок — user=%s", message.from_user.id)
    await cmd_home(message)


@router.message(F.text == "🏆 Топ")
async def handle_top_games(message: Message):
    logger.info("Reply KB: 🏆 Топ — user=%s", message.from_user.id)
    chat_id = message.chat.id
    cactus_top = await repo.get_cactus_top(chat_id, 5)
    cat_top = await repo.get_cat_top(chat_id, 5)
    duel_top = await repo.get_duel_top(chat_id, 5)

    def fmt_list(items, val_key, unit):
        if not items:
            return "  Пока никого"
        return "\n".join(
            f"  {i}. {it.get('first_name') or it.get('username') or '?'} — {it[val_key]} {unit}"
            for i, it in enumerate(items, 1)
        )

    text = (
        "🏆 <b>Таблица лидеров</b>\n\n"
        f"<b>🌵 Кактус:</b>\n{fmt_list(cactus_top, 'height_cm', 'см')}\n\n"
        f"<b>🐈 Кот:</b>\n{fmt_list(cat_top, 'mood_score', 'очков')}\n\n"
        f"<b>⚔️ Дуэли:</b>\n{fmt_list(duel_top, 'wins', 'побед')}"
    )
    await message.answer(text, reply_markup=kb_games(), parse_mode="HTML")


# ── Reminders ───────────────────────────────────────────────────────


@router.message(F.text == "➕ Создать напоминание")
async def handle_create_reminder(message: Message, state: FSMContext):
    logger.info("Reply KB: ➕ Создать напоминание — user=%s", message.from_user.id)
    await cmd_remind(message, state)


@router.message(F.text == "📋 Мои напоминания")
async def handle_my_reminders(message: Message):
    logger.info("Reply KB: 📋 Мои напоминания — user=%s", message.from_user.id)
    await cmd_reminders(message)


# ── Weather ─────────────────────────────────────────────────────────


@router.message(F.text == "🌡️ Текущая погода")
async def handle_weather_now(message: Message):
    logger.info("Reply KB: 🌡️ Текущая погода — user=%s", message.from_user.id)
    text = await get_weather_for_chat(message.chat.id)
    await message.answer(text, reply_markup=kb_weather(), parse_mode="HTML")


@router.message(F.text == "➕ Добавить город")
async def handle_add_city(message: Message, state: FSMContext):
    logger.info("Reply KB: ➕ Добавить город — user=%s", message.from_user.id)
    await state.set_state(WeatherAddCity.waiting_city)
    await message.answer("🏙️ Напиши название города:")


@router.message(F.text == "➖ Удалить город")
async def handle_del_city(message: Message):
    logger.info("Reply KB: ➖ Удалить город — user=%s", message.from_user.id)
    cities = await repo.get_weather_cities(message.chat.id)
    if not cities:
        await message.answer("Нет добавленных городов.", reply_markup=kb_weather())
        return
    await message.answer(
        "🏙️ Выбери город для удаления:",
        reply_markup=weather_cities_delete_kb(cities),
    )


# ── Quotes ──────────────────────────────────────────────────────────

_QUOTE_CATEGORY_MAP = {
    "👑 Золотой фонд": "⭐",
    "🌚 Тёмная лошадка": "🌚",
    "🤔 Со смыслом": "🤔",
    "🗿 А чо а всмысле": "🗿",
    "🤡 Юрий Гальцев": "🤡",
}

_MEDIA_LABELS = {
    "photo": "[Фото]",
    "voice": "[Голосовое]",
    "video_note": "[Кружочек]",
    "video": "[Видео]",
    "sticker": "[Стикер]",
    "audio": "[Аудио]",
    "document": "[Документ]",
}


@router.message(F.text.in_(set(_QUOTE_CATEGORY_MAP.keys())))
async def handle_quote_category(message: Message):
    logger.info("Reply KB: quote category '%s' — user=%s", message.text, message.from_user.id)
    category = _QUOTE_CATEGORY_MAP[message.text]
    quote = await repo.get_random_quote(message.chat.id, category=category)
    if not quote:
        await message.answer(f"💬 Нет цитат в разделе «{message.text}».", reply_markup=kb_quotes())
        return
    text = quote.get("text")
    media_type = quote.get("media_type")
    if not text and media_type:
        text = _MEDIA_LABELS.get(media_type, "[Медиа]")
    elif not text:
        text = "..."
    author = quote.get("first_name") or quote.get("username") or "Неизвестный"
    await message.answer(
        f"💬 <i>«{text}»</i>\n— {author}",
        reply_markup=kb_quotes(), parse_mode="HTML",
    )


@router.message(F.text == "📊 Топ авторов")
async def handle_quote_top_authors(message: Message):
    logger.info("Reply KB: 📊 Топ авторов — user=%s", message.from_user.id)
    counts = await repo.get_quote_counts(message.chat.id)
    if not counts:
        await message.answer("💬 Нет сохранённых цитат.", reply_markup=kb_quotes())
        return
    lines = ["📊 <b>Топ авторов цитат</b>\n"]
    for i, c in enumerate(counts, 1):
        name = c.get("first_name") or c.get("username") or "?"
        lines.append(f"{i}. {name} — {c['cnt']} цитат")
    await message.answer("\n".join(lines), reply_markup=kb_quotes(), parse_mode="HTML")


# ── Stats ───────────────────────────────────────────────────────────


@router.message(F.text == "👤 Мой профиль")
async def handle_my_profile(message: Message):
    logger.info("Reply KB: 👤 Мой профиль — user=%s", message.from_user.id)
    chat_id = message.chat.id
    user_id = message.from_user.id
    cactus = await repo.get_cactus(chat_id, user_id)
    cat = await repo.get_cat(chat_id, user_id)
    duel_stats = await repo.get_duel_stats(chat_id, user_id)
    roulette_survived = await repo.get_roulette_survival_count(chat_id, user_id)
    reactions_received = await repo.get_my_reactions_count(chat_id, user_id)
    text = (
        f"👤 <b>Статистика {message.from_user.first_name}</b>\n\n"
        f"🌵 Кактус: {cactus['height_cm']} см ({cactus['total_plays']} поливов)\n"
        f"🐈 Кот: {cat['mood_score']} очков ({cat['total_plays']} кормлений)\n"
        f"⚔️ Дуэли: {duel_stats['wins']}/{duel_stats['total']} побед\n"
        f"🔫 Рулетка: выжил {roulette_survived} раз\n"
        f"👍 Реакций получено: {reactions_received}"
    )
    await message.answer(text, reply_markup=kb_stats(), parse_mode="HTML")


@router.message(F.text == "🏆 Таблица лидеров")
async def handle_leaderboard(message: Message):
    logger.info("Reply KB: 🏆 Таблица лидеров — user=%s", message.from_user.id)
    chat_id = message.chat.id
    cactus_top = await repo.get_cactus_top(chat_id, 5)
    cat_top = await repo.get_cat_top(chat_id, 5)
    duel_top = await repo.get_duel_top(chat_id, 5)

    def fmt_list(items, val_key, unit):
        if not items:
            return "  Пока никого"
        return "\n".join(
            f"  {i}. {it.get('first_name') or it.get('username') or '?'} — {it[val_key]} {unit}"
            for i, it in enumerate(items, 1)
        )

    text = (
        "🏆 <b>Таблица лидеров</b>\n\n"
        f"<b>🌵 Кактус:</b>\n{fmt_list(cactus_top, 'height_cm', 'см')}\n\n"
        f"<b>🐈 Кот:</b>\n{fmt_list(cat_top, 'mood_score', 'очков')}\n\n"
        f"<b>⚔️ Дуэли:</b>\n{fmt_list(duel_top, 'wins', 'побед')}"
    )
    await message.answer(text, reply_markup=kb_stats(), parse_mode="HTML")


@router.message(F.text == "🎖️ Мои награды")
async def handle_my_awards(message: Message):
    logger.info("Reply KB: 🎖️ Мои награды — user=%s", message.from_user.id)
    await cmd_awards(message)


# ── Help ────────────────────────────────────────────────────────────

_HELP_FULL = (
    "📖 <b>Список команд</b>\n\n"
    "<b>📌 Общие:</b>\n"
    "/start — Приветствие\n"
    "/menu — Главное меню\n"
    "/help — Этот список\n"
    "/status — Диагностика бота\n"
    "/mystats — Личная статистика\n"
    "/top — Таблица лидеров\n\n"
    "<b>🎮 Игры:</b>\n"
    "/cactus — Полить кактус\n"
    "/cat — Покормить кота\n"
    "/home — Порядок дома\n"
    "/duel @user [мин] — Вызвать на дуэль\n"
    "/roulette — Русская рулетка\n\n"
    "<b>📅 Напоминания и др.:</b>\n"
    "/remind — Создать напоминание\n"
    "/reminders — Мои напоминания\n"
    "/weather — Погода сейчас\n"
    "/city_add город — Добавить город\n"
    "/city_del город — Удалить город\n"
    "/weather_time HH:MM — Время рассылки (OWNER)\n"
    "/quote — Сохранить цитату (reply)\n"
    "/quote_random — Случайная цитата\n"
    "/quote_last N — Последние N цитат\n"
    "/birthday_add имя дд.мм — Добавить ДР (OWNER)\n"
    "/birthdays — Список дней рождения\n"
    "/ясно_топ — Топ «ясно»\n"
    "/top_reactions — Топ реакций\n"
    "/my_reactions — Мои реакции\n"
    "/awards — Награды месяца\n"
    "/awards_all — Все награды"
)

_HELP_GAMES = (
    "🎮 <b>Игры</b>\n\n"
    "🌵 <b>Кактус</b> — полей кактус раз в сутки, чтобы он рос.\n"
    "  Есть шанс уколоться: кактус уменьшается, мут на несколько минут.\n\n"
    "🐈 <b>Кот</b> — покорми кота раз в сутки.\n"
    "  Влияет на уровень порядка в доме.\n\n"
    "⚔️ <b>Дуэль</b> — /duel @username [минуты]\n"
    "  Случайный победитель, проигравший получает мут.\n\n"
    "🔫 <b>Рулетка</b> — /roulette (2–6 игроков)\n"
    "  Один выбывает с мутом на 20 минут.\n\n"
    "🧹 <b>Порядок</b> — /home\n"
    "  Текущий уровень порядка в доме."
)


@router.message(F.text == "📖 Полная справка")
async def handle_full_help(message: Message):
    logger.info("Reply KB: 📖 Полная справка — user=%s", message.from_user.id)
    await message.answer(_HELP_FULL, reply_markup=kb_help(), parse_mode="HTML")


@router.message(F.text == "🎮 О играх")
async def handle_games_help(message: Message):
    logger.info("Reply KB: 🎮 О играх — user=%s", message.from_user.id)
    await message.answer(_HELP_GAMES, reply_markup=kb_help(), parse_mode="HTML")


@router.message(F.text == "📋 О командах")
async def handle_commands_help(message: Message):
    logger.info("Reply KB: 📋 О командах — user=%s", message.from_user.id)
    await message.answer(_HELP_FULL, reply_markup=kb_help(), parse_mode="HTML")
