from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from app.bot.keyboards import (
    main_menu_kb, games_menu_kb, reminders_menu_kb, weather_menu_kb,
    quotes_menu_kb, stats_menu_kb, settings_kb, back_to_menu_kb,
)
from app.db import repositories as repo
from app.utils.helpers import mention_user, progress_bar
from app.config.settings import SUPERADMIN_ID

router = Router()

WELCOME_TEXT = (
    "\U0001f916 <b>Family Chat Bot</b>\n\n"
    "\u041f\u0440\u0438\u0432\u0435\u0442! \u042f \u0441\u0435\u043c\u0435\u0439\u043d\u044b\u0439 \u0431\u043e\u0442 \u0441 \u0438\u0433\u0440\u0430\u043c\u0438, \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f\u043c\u0438, "
    "\u043f\u043e\u0433\u043e\u0434\u043e\u0439, \u0446\u0438\u0442\u0430\u0442\u0430\u043c\u0438 \u0438 \u043c\u043d\u043e\u0433\u0438\u043c \u0434\u0440\u0443\u0433\u0438\u043c!\n\n"
    "\U0001f449 \u041d\u0430\u0436\u043c\u0438 <b>\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043c\u0435\u043d\u044e</b> \u0434\u043b\u044f \u043d\u0430\u0447\u0430\u043b\u0430.\n"
    "\U0001f4dd /help \u2014 \u043f\u043e\u043b\u043d\u044b\u0439 \u0441\u043f\u0438\u0441\u043e\u043a \u043a\u043e\u043c\u0430\u043d\u0434.\n\n"
    "\u2757 \u0414\u043b\u044f \u043f\u043e\u043b\u043d\u043e\u0446\u0435\u043d\u043d\u043e\u0439 \u0440\u0430\u0431\u043e\u0442\u044b (\u043c\u0443\u0442 \u0432 \u0438\u0433\u0440\u0430\u0445) \u0432\u044b\u0434\u0430\u0439\u0442\u0435 \u0431\u043e\u0442\u0443 \u043f\u0440\u0430\u0432\u0430 \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0430."
)

HELP_TEXT = (
    "<b>\U0001f4d6 \u0421\u043f\u0438\u0441\u043e\u043a \u043a\u043e\u043c\u0430\u043d\u0434</b>\n\n"
    "<b>\U0001f4cc \u041e\u0431\u0449\u0438\u0435:</b>\n"
    "/start \u2014 \u041f\u0440\u0438\u0432\u0435\u0442\u0441\u0442\u0432\u0438\u0435\n"
    "/menu \u2014 \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e\n"
    "/help \u2014 \u042d\u0442\u043e\u0442 \u0441\u043f\u0438\u0441\u043e\u043a\n"
    "/status \u2014 \u0414\u0438\u0430\u0433\u043d\u043e\u0441\u0442\u0438\u043a\u0430 \u0431\u043e\u0442\u0430\n"
    "/mystats \u2014 \u041b\u0438\u0447\u043d\u0430\u044f \u0441\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430\n"
    "/top \u2014 \u0422\u0430\u0431\u043b\u0438\u0446\u0430 \u043b\u0438\u0434\u0435\u0440\u043e\u0432\n\n"
    "<b>\U0001f3ae \u0418\u0433\u0440\u044b:</b>\n"
    "/cactus \u2014 \u041f\u043e\u043b\u0438\u0442\u044c \u043a\u0430\u043a\u0442\u0443\u0441\n"
    "/cat \u2014 \u041f\u043e\u043a\u043e\u0440\u043c\u0438\u0442\u044c \u043a\u043e\u0442\u0430\n"
    "/home \u2014 \u041f\u043e\u0440\u044f\u0434\u043e\u043a \u0434\u043e\u043c\u0430\n"
    "/duel @user [\u043c\u0438\u043d] \u2014 \u0412\u044b\u0437\u0432\u0430\u0442\u044c \u043d\u0430 \u0434\u0443\u044d\u043b\u044c\n"
    "/roulette \u2014 \u0420\u0443\u0441\u0441\u043a\u0430\u044f \u0440\u0443\u043b\u0435\u0442\u043a\u0430\n\n"
    "<b>\U0001f4c5 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f \u0438 \u0434\u0440.:</b>\n"
    "/remind \u2014 \u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435\n"
    "/reminders \u2014 \u041c\u043e\u0438 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f\n"
    "/weather \u2014 \u041f\u043e\u0433\u043e\u0434\u0430 \u0441\u0435\u0439\u0447\u0430\u0441\n"
    "/city_add \u0433\u043e\u0440\u043e\u0434 \u2014 \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0433\u043e\u0440\u043e\u0434\n"
    "/city_del \u0433\u043e\u0440\u043e\u0434 \u2014 \u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0433\u043e\u0440\u043e\u0434\n"
    "/weather_time HH:MM \u2014 \u0412\u0440\u0435\u043c\u044f \u0440\u0430\u0441\u0441\u044b\u043b\u043a\u0438 (OWNER)\n"
    "/quote \u2014 \u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0446\u0438\u0442\u0430\u0442\u0443 (reply)\n"
    "/quote_random \u2014 \u0421\u043b\u0443\u0447\u0430\u0439\u043d\u0430\u044f \u0446\u0438\u0442\u0430\u0442\u0430\n"
    "/quote_last N \u2014 \u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 N \u0446\u0438\u0442\u0430\u0442\n"
    "/birthday_add \u0438\u043c\u044f \u0434\u0434.\u043c\u043c \u2014 \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0414\u0420 (OWNER)\n"
    "/birthdays \u2014 \u0421\u043f\u0438\u0441\u043e\u043a \u0434\u043d\u0435\u0439 \u0440\u043e\u0436\u0434\u0435\u043d\u0438\u044f\n"
    "/\u044f\u0441\u043d\u043e_\u0442\u043e\u043f \u2014 \u0422\u043e\u043f \u00ab\u044f\u0441\u043d\u043e\u00bb\n"
    "/top_reactions \u2014 \u0422\u043e\u043f \u0440\u0435\u0430\u043a\u0446\u0438\u0439\n"
    "/my_reactions \u2014 \u041c\u043e\u0438 \u0440\u0435\u0430\u043a\u0446\u0438\u0438\n"
    "/awards \u2014 \u041d\u0430\u0433\u0440\u0430\u0434\u044b \u043c\u0435\u0441\u044f\u0446\u0430\n"
    "/awards_all \u2014 \u0412\u0441\u0435 \u043d\u0430\u0433\u0440\u0430\u0434\u044b"
)


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(
        "\U0001f3e0 <b>\u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e</b>\n\u0412\u044b\u0431\u0435\u0440\u0438 \u0440\u0430\u0437\u0434\u0435\u043b:",
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
        ("weather_enabled", "\u26c5 \u041f\u043e\u0433\u043e\u0434\u0430"),
        ("games_enabled", "\U0001f3ae \u0418\u0433\u0440\u044b"),
        ("translator_enabled", "\U0001f50e \u041f\u0435\u0440\u0435\u0432\u043e\u0434\u0447\u0438\u043a"),
        ("quotes_enabled", "\U0001f4ac \u0426\u0438\u0442\u0430\u0442\u044b"),
        ("birthdays_enabled", "\U0001f382 \u0414\u043d\u0438 \u0440\u043e\u0436\u0434\u0435\u043d\u0438\u044f"),
    ]:
        state = "\u2705" if settings.get(key) else "\u274c"
        modules.append(f"  {state} {label}")

    modules_text = "\n".join(modules)
    cities_text = ", ".join(cities) if cities else "\u043d\u0435 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u044b"
    weather_time = settings.get("weather_time", "08:00")
    text = (
        "\U0001f4ca <b>\u0421\u0442\u0430\u0442\u0443\u0441 \u0431\u043e\u0442\u0430</b>\n\n"
        f"<b>\u041c\u043e\u0434\u0443\u043b\u0438:</b>\n{modules_text}\n\n"
        f"\U0001f321\ufe0f \u0412\u0440\u0435\u043c\u044f \u043f\u043e\u0433\u043e\u0434\u044b: {weather_time}\n"
        f"\U0001f3d9\ufe0f \u0413\u043e\u0440\u043e\u0434\u0430: {cities_text}\n"
        f"\U0001f514 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0439: {len(reminders)}\n"
        f"\U0001f3e0 \u041f\u043e\u0440\u044f\u0434\u043e\u043a \u0434\u043e\u043c\u0430: {progress_bar(home)}"
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
        f"\U0001f464 <b>\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430 {message.from_user.first_name}</b>\n\n"
        f"\U0001f335 \u041a\u0430\u043a\u0442\u0443\u0441: {cactus['height_cm']} \u0441\u043c ({cactus['total_plays']} \u043f\u043e\u043b\u0438\u0432\u043e\u0432)\n"
        f"\U0001f408 \u041a\u043e\u0442: {cat['mood_score']} \u043e\u0447\u043a\u043e\u0432 ({cat['total_plays']} \u043a\u043e\u0440\u043c\u043b\u0435\u043d\u0438\u0439)\n"
        f"\u2694\ufe0f \u0414\u0443\u044d\u043b\u0438: {duel_stats['wins']}/{duel_stats['total']} \u043f\u043e\u0431\u0435\u0434\n"
        f"\U0001f52b \u0420\u0443\u043b\u0435\u0442\u043a\u0430: \u0432\u044b\u0436\u0438\u043b {roulette_survived} \u0440\u0430\u0437\n"
        f"\U0001f44d \u0420\u0435\u0430\u043a\u0446\u0438\u0439 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u043e: {reactions_received}"
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
            return "  \u041f\u043e\u043a\u0430 \u043d\u0438\u043a\u043e\u0433\u043e"
        lines = []
        for i, item in enumerate(items, 1):
            name = item.get("first_name") or item.get("username") or "?"
            lines.append(f"  {i}. {name} \u2014 {item[val_key]} {unit}")
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
    await callback.message.edit_text(
        "\U0001f3e0 <b>\u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e</b>\n\u0412\u044b\u0431\u0435\u0440\u0438 \u0440\u0430\u0437\u0434\u0435\u043b:",
        reply_markup=main_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:games")
async def cb_menu_games(callback: CallbackQuery):
    await callback.message.edit_text(
        "\U0001f3ae <b>\u0418\u0433\u0440\u044b</b>\n\u0412\u044b\u0431\u0435\u0440\u0438 \u0438\u0433\u0440\u0443:",
        reply_markup=games_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:reminders")
async def cb_menu_reminders(callback: CallbackQuery):
    await callback.message.edit_text(
        "\U0001f4c5 <b>\u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f</b>",
        reply_markup=reminders_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:weather")
async def cb_menu_weather(callback: CallbackQuery):
    await callback.message.edit_text(
        "\u26c5 <b>\u041f\u043e\u0433\u043e\u0434\u0430</b>",
        reply_markup=weather_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:quotes")
async def cb_menu_quotes(callback: CallbackQuery):
    await callback.message.edit_text(
        "\U0001f4ac <b>\u0426\u0438\u0442\u0430\u0442\u044b</b>",
        reply_markup=quotes_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:stats")
async def cb_menu_stats(callback: CallbackQuery):
    await callback.message.edit_text(
        "\U0001f4ca <b>\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430</b>",
        reply_markup=stats_menu_kb(), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:help")
async def cb_menu_help(callback: CallbackQuery):
    await callback.message.edit_text(HELP_TEXT, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "menu:settings")
async def cb_menu_settings(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    role = await repo.get_user_role(user_id, chat_id)
    if role != "owner" and user_id != SUPERADMIN_ID:
        await callback.answer("\u26d4 \u0422\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f OWNER", show_alert=True)
        return

    settings = await repo.get_settings(chat_id)
    await callback.message.edit_text(
        "\u2699\ufe0f <b>\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438</b>\n\u041d\u0430\u0436\u043c\u0438 \u0434\u043b\u044f \u043f\u0435\u0440\u0435\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f:",
        reply_markup=settings_kb(settings), parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setting:"))
async def cb_toggle_setting(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    role = await repo.get_user_role(user_id, chat_id)
    if role != "owner" and user_id != SUPERADMIN_ID:
        await callback.answer("\u26d4 \u0422\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f OWNER", show_alert=True)
        return

    key = callback.data.split(":")[1]
    settings = await repo.get_settings(chat_id)
    new_val = 0 if settings.get(key) else 1
    await repo.update_setting(chat_id, key, new_val)

    settings = await repo.get_settings(chat_id)
    await callback.message.edit_reply_markup(reply_markup=settings_kb(settings))
    await callback.answer("\u2705 \u0418\u0437\u043c\u0435\u043d\u0435\u043d\u043e")


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
        f"\U0001f464 <b>\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430 {callback.from_user.first_name}</b>\n\n"
        f"\U0001f335 \u041a\u0430\u043a\u0442\u0443\u0441: {cactus['height_cm']} \u0441\u043c ({cactus['total_plays']} \u043f\u043e\u043b\u0438\u0432\u043e\u0432)\n"
        f"\U0001f408 \u041a\u043e\u0442: {cat['mood_score']} \u043e\u0447\u043a\u043e\u0432 ({cat['total_plays']} \u043a\u043e\u0440\u043c\u043b\u0435\u043d\u0438\u0439)\n"
        f"\u2694\ufe0f \u0414\u0443\u044d\u043b\u0438: {duel_stats['wins']}/{duel_stats['total']} \u043f\u043e\u0431\u0435\u0434\n"
        f"\U0001f52b \u0420\u0443\u043b\u0435\u0442\u043a\u0430: \u0432\u044b\u0436\u0438\u043b {roulette_survived} \u0440\u0430\u0437\n"
        f"\U0001f44d \u0420\u0435\u0430\u043a\u0446\u0438\u0439: {reactions_received}"
    )
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "stats:top")
async def cb_stats_top(callback: CallbackQuery):
    chat_id = callback.message.chat.id

    cactus_top = await repo.get_cactus_top(chat_id, 5)
    cat_top = await repo.get_cat_top(chat_id, 5)
    duel_top = await repo.get_duel_top(chat_id, 5)

    def fmt_list(items, val_key, unit):
        if not items:
            return "  \u041f\u043e\u043a\u0430 \u043d\u0438\u043a\u043e\u0433\u043e"
        lines = []
        for i, item in enumerate(items, 1):
            name = item.get("first_name") or item.get("username") or "?"
            lines.append(f"  {i}. {name} \u2014 {item[val_key]} {unit}")
        return "\n".join(lines)

    text = (
        "\U0001f3c6 <b>\u0422\u0430\u0431\u043b\u0438\u0446\u0430 \u043b\u0438\u0434\u0435\u0440\u043e\u0432</b>\n\n"
        f"<b>\U0001f335 \u041a\u0430\u043a\u0442\u0443\u0441:</b>\n{fmt_list(cactus_top, 'height_cm', '\u0441\u043c')}\n\n"
        f"<b>\U0001f408 \u041a\u043e\u0442:</b>\n{fmt_list(cat_top, 'mood_score', '\u043e\u0447\u043a\u043e\u0432')}\n\n"
        f"<b>\u2694\ufe0f \u0414\u0443\u044d\u043b\u0438:</b>\n{fmt_list(duel_top, 'wins', '\u043f\u043e\u0431\u0435\u0434')}"
    )
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()
