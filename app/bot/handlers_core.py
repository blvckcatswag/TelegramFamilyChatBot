from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import Message, CallbackQuery
from app.bot.keyboards import (
    main_menu_kb, games_menu_kb, reminders_menu_kb, weather_menu_kb,
    quotes_menu_kb, stats_menu_kb, settings_kb, back_to_menu_kb,
)
from app.db import repositories as repo
from app.utils.helpers import mention_user, progress_bar, safe_edit_text, safe_edit_reply_markup
from app.config.settings import SUPERADMIN_ID
from app.utils.reply_keyboards import kb_start

router = Router()

WELCOME_TEXT = (
    "🤖 <b>Привет! Я семейный чат-бот.</b>\n\n"
    "Выбери что делать или нажми любую кнопку выше:\n"
    "• 📋 Меню — главное меню\n"
    "• 🎮 Игры — мини-игры (кактус, кот, дуэль, рулетка)\n"
    "• 📅 Напоминания — создание и управление напоминаниями\n"
    "• 🌤️ Погода — текущая погода и рассылка\n"
    "• 💬 Цитаты — цитатник\n"
    "• ℹ️ Справка — полная справка по командам\n\n"
    "❗ Для полноценной работы (мут в играх) выдайте боту права администратора."
)

HELP_TEXT = (
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


@router.message(Command("cancel"), ~StateFilter(default_state))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.", reply_markup=kb_start(), parse_mode="HTML")


@router.message(Command("cancel"), StateFilter(default_state))
async def cmd_cancel_idle(message: Message):
    await message.answer("Нечего отменять.", reply_markup=kb_start(), parse_mode="HTML")


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(WELCOME_TEXT, reply_markup=kb_start(), parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(
        "🏠 <b>Главное меню</b>\nВыбери раздел:",
        reply_markup=main_menu_kb(), parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, reply_markup=back_to_menu_kb(), parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message):
    chat_id = message.chat.id
    settings = await repo.get_settings(chat_id)
    cities = await repo.get_weather_cities(chat_id)
    reminders = await repo.get_active_reminders(chat_id)
    home = await repo.get_home_order(chat_id)

    modules = []
    for key, label in [
        ("weather_enabled", "⛅ Погода"),
        ("games_enabled", "🎮 Игры"),
        ("translator_enabled", "🔎 Переводчик"),
        ("quotes_enabled", "💬 Цитаты"),
        ("birthdays_enabled", "🎂 Дни рождения"),
    ]:
        state = "✅" if settings.get(key) else "❌"
        modules.append(f"  {state} {label}")

    modules_text = "\n".join(modules)
    cities_text = ", ".join(cities) if cities else "не добавлены"
    weather_time = settings.get("weather_time", "08:00")
    text = (
        "📊 <b>Статус бота</b>\n\n"
        f"<b>Модули:</b>\n{modules_text}\n\n"
        f"🌡️ Время погоды: {weather_time}\n"
        f"🏙️ Города: {cities_text}\n"
        f"🔔 Напоминаний: {len(reminders)}\n"
        f"🏠 Порядок дома: {progress_bar(home)}"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("mystats"))
async def cmd_mystats(message: Message):
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
    await message.answer(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")


@router.message(Command("top"))
async def cmd_top(message: Message):
    chat_id = message.chat.id

    cactus_top = await repo.get_cactus_top(chat_id, 5)
    cat_top = await repo.get_cat_top(chat_id, 5)
    duel_top = await repo.get_duel_top(chat_id, 5)

    def fmt_list(items, val_key, unit):
        if not items:
            return "  Пока никого"
        lines = []
        for i, item in enumerate(items, 1):
            name = item.get("first_name") or item.get("username") or "?"
            lines.append(f"  {i}. {name} — {item[val_key]} {unit}")
        return "\n".join(lines)

    text = (
        "🏆 <b>Таблица лидеров</b>\n\n"
        f"<b>🌵 Кактус:</b>\n{fmt_list(cactus_top, 'height_cm', 'см')}\n\n"
        f"<b>🐈 Кот:</b>\n{fmt_list(cat_top, 'mood_score', 'очков')}\n\n"
        f"<b>⚔️ Дуэли:</b>\n{fmt_list(duel_top, 'wins', 'побед')}"
    )
    await message.answer(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")


# ──────────────────── Menu navigation callbacks ────────────────────

@router.callback_query(F.data == "menu:main")
async def cb_menu_main(callback: CallbackQuery):
    await safe_edit_text(callback.message, 
        "🏠 <b>Главное меню</b>\nВыбери раздел:",
        reply_markup=main_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:games")
async def cb_menu_games(callback: CallbackQuery):
    await safe_edit_text(callback.message, 
        "🎮 <b>Игры</b>\nВыбери игру:",
        reply_markup=games_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:reminders")
async def cb_menu_reminders(callback: CallbackQuery):
    await safe_edit_text(callback.message, 
        "📅 <b>Напоминания</b>",
        reply_markup=reminders_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:weather")
async def cb_menu_weather(callback: CallbackQuery):
    await safe_edit_text(callback.message, 
        "⛅ <b>Погода</b>",
        reply_markup=weather_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:quotes")
async def cb_menu_quotes(callback: CallbackQuery):
    await safe_edit_text(callback.message, 
        "💬 <b>Цитаты</b>",
        reply_markup=quotes_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:stats")
async def cb_menu_stats(callback: CallbackQuery):
    await safe_edit_text(callback.message, 
        "📊 <b>Статистика</b>",
        reply_markup=stats_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:help")
async def cb_menu_help(callback: CallbackQuery):
    await safe_edit_text(callback.message, HELP_TEXT, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "menu:settings")
async def cb_menu_settings(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    role = await repo.get_user_role(user_id, chat_id)
    if role != "owner" and user_id != SUPERADMIN_ID:
        await callback.answer("⛔ Только для OWNER", show_alert=True)
        return

    settings = await repo.get_settings(chat_id)
    await safe_edit_text(callback.message, 
        "⚙️ <b>Настройки</b>\nНажми для переключения:",
        reply_markup=settings_kb(settings), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setting:"))
async def cb_toggle_setting(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    role = await repo.get_user_role(user_id, chat_id)
    if role != "owner" and user_id != SUPERADMIN_ID:
        await callback.answer("⛔ Только для OWNER", show_alert=True)
        return

    key = callback.data.split(":")[1]
    settings = await repo.get_settings(chat_id)
    new_val = not bool(settings.get(key))
    await repo.update_setting(chat_id, key, new_val)

    settings = await repo.get_settings(chat_id)
    await safe_edit_reply_markup(callback.message, reply_markup=settings_kb(settings))
    await callback.answer("✅ Изменено")


@router.callback_query(F.data == "stats:my")
async def cb_stats_my(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    cactus = await repo.get_cactus(chat_id, user_id)
    cat = await repo.get_cat(chat_id, user_id)
    duel_stats = await repo.get_duel_stats(chat_id, user_id)
    roulette_survived = await repo.get_roulette_survival_count(chat_id, user_id)
    reactions_received = await repo.get_my_reactions_count(chat_id, user_id)

    text = (
        f"👤 <b>Статистика {callback.from_user.first_name}</b>\n\n"
        f"🌵 Кактус: {cactus['height_cm']} см ({cactus['total_plays']} поливов)\n"
        f"🐈 Кот: {cat['mood_score']} очков ({cat['total_plays']} кормлений)\n"
        f"⚔️ Дуэли: {duel_stats['wins']}/{duel_stats['total']} побед\n"
        f"🔫 Рулетка: выжил {roulette_survived} раз\n"
        f"👍 Реакций: {reactions_received}"
    )
    await safe_edit_text(callback.message, text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "stats:top")
async def cb_stats_top(callback: CallbackQuery):
    chat_id = callback.message.chat.id

    cactus_top = await repo.get_cactus_top(chat_id, 5)
    cat_top = await repo.get_cat_top(chat_id, 5)
    duel_top = await repo.get_duel_top(chat_id, 5)

    def fmt_list(items, val_key, unit):
        if not items:
            return "  Пока никого"
        lines = []
        for i, item in enumerate(items, 1):
            name = item.get("first_name") or item.get("username") or "?"
            lines.append(f"  {i}. {name} — {item[val_key]} {unit}")
        return "\n".join(lines)

    text = (
        "🏆 <b>Таблица лидеров</b>\n\n"
        f"<b>🌵 Кактус:</b>\n{fmt_list(cactus_top, 'height_cm', 'см')}\n\n"
        f"<b>🐈 Кот:</b>\n{fmt_list(cat_top, 'mood_score', 'очков')}\n\n"
        f"<b>⚔️ Дуэли:</b>\n{fmt_list(duel_top, 'wins', 'побед')}"
    )
    await safe_edit_text(callback.message, text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()
