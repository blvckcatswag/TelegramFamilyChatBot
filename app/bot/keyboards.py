from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Игры", callback_data="menu:games"),
         InlineKeyboardButton(text="📅 Напоминания", callback_data="menu:reminders")],
        [InlineKeyboardButton(text="⛅ Погода", callback_data="menu:weather"),
         InlineKeyboardButton(text="💬 Цитаты", callback_data="menu:quotes")],
        [InlineKeyboardButton(text="🎂 Дни рождения", callback_data="menu:birthdays"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")],
        [InlineKeyboardButton(text="ℹ️ Справка", callback_data="menu:help"),
         InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")],
    ])


def games_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌵 Кактус", callback_data="game:cactus"),
         InlineKeyboardButton(text="🐈 Кот", callback_data="game:cat")],
        [InlineKeyboardButton(text="🃏 Блэкджек", callback_data="game:blackjack"),
         InlineKeyboardButton(text="🧹 Порядок дома", callback_data="game:home")],
        [InlineKeyboardButton(text="⚔️ Дуэль", callback_data="game:duel"),
         InlineKeyboardButton(text="🔫 Рулетка", callback_data="game:roulette")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])


def reminders_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать", callback_data="remind:create")],
        [InlineKeyboardButton(text="📋 Мои напоминания", callback_data="remind:list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])


def weather_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌡️ Погода сейчас", callback_data="weather:now")],
        [InlineKeyboardButton(text="➕ Добавить город", callback_data="weather:add_city"),
         InlineKeyboardButton(text="➖ Удалить город", callback_data="weather:del_city")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])


def quotes_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Случайная", callback_data="quote:random")],
        [InlineKeyboardButton(text="📖 Последние 5", callback_data="quote:last")],
        [InlineKeyboardButton(text="📊 Счётчик цитат", callback_data="quote:counts")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])


def stats_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="stats:my")],
        [InlineKeyboardButton(text="🏆 Рейтинги", callback_data="stats:top")],
        [InlineKeyboardButton(text="🏅 Награды", callback_data="stats:awards")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])


def settings_kb(settings: dict) -> InlineKeyboardMarkup:
    def toggle(key: str, label: str) -> InlineKeyboardButton:
        state = "✅" if settings.get(key) else "❌"
        return InlineKeyboardButton(text=f"{state} {label}", callback_data=f"setting:{key}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [toggle("weather_enabled", "Погода"), toggle("games_enabled", "Игры")],
        [toggle("translator_enabled", "Переводчик"), toggle("quotes_enabled", "Цитаты")],
        [toggle("birthdays_enabled", "Дни рождения")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])


def birthdays_menu_kb(is_owner: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if is_owner:
        buttons.append([InlineKeyboardButton(text="➕ Добавить", callback_data="birthday:add")])
    buttons.append([InlineKeyboardButton(text="📋 Список", callback_data="birthday:list")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def birthday_delete_kb(birthdays: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for b in birthdays:
        from app.utils.helpers import format_birthday_date
        buttons.append([InlineKeyboardButton(
            text=f"❌ {b['name']} — {format_birthday_date(b['date'])}",
            callback_data=f"birthday:del:{b['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:birthdays")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="menu:main")],
    ])


def duel_accept_kb(challenger_id: int, mute_minutes: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⚔️ Принять дуэль",
            callback_data=f"duel:accept:{challenger_id}:{mute_minutes}",
        )],
    ])


def reminder_delete_kb(reminders: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for r in reminders:
        text_preview = r["text"][:30] + ("..." if len(r["text"]) > 30 else "")
        buttons.append([InlineKeyboardButton(
            text=f"❌ {text_preview} ({r['run_at'][:16]})",
            callback_data=f"remind:del:{r['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:reminders")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def weather_cities_delete_kb(cities: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    for city in cities:
        buttons.append([InlineKeyboardButton(
            text=f"❌ {city}",
            callback_data=f"weather:remove:{city}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:weather")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
