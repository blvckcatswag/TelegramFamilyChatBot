from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

_KB = KeyboardButton


def kb_start() -> ReplyKeyboardMarkup:
    """Level 0 — shown on /start."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [_KB(text="📋 Меню")],
            [_KB(text="🎮 Игры"), _KB(text="📅 Напоминания")],
            [_KB(text="🌤️ Погода"), _KB(text="💬 Цитаты")],
            [_KB(text="ℹ️ Справка")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выбери действие или напиши команду...",
    )


def kb_menu() -> ReplyKeyboardMarkup:
    """Level 1 — main menu."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [_KB(text="🎮 Игры"), _KB(text="📅 Напоминания")],
            [_KB(text="🌤️ Погода"), _KB(text="💬 Цитаты")],
            [_KB(text="📊 Статистика"), _KB(text="⚙️ Настройки")],
            [_KB(text="ℹ️ Справка"), _KB(text="📣 Фидбек")],
            [_KB(text="💝 Поддержать")],
            [_KB(text="◀️ На главную")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выбери раздел...",
    )


def kb_games() -> ReplyKeyboardMarkup:
    """Level 2 — games submenu."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [_KB(text="🌵 Полить кактус"), _KB(text="🐈 Кот")],
            [_KB(text="⚔️ Дуэль"), _KB(text="🔫 Рулетка")],
            [_KB(text="🧹 Порядок"), _KB(text="🏆 Топ")],
            [_KB(text="◀️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выбери игру...",
    )


def kb_cat() -> ReplyKeyboardMarkup:
    """Level 3 — cat submenu."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [_KB(text="🍗 Покормить")],
            [_KB(text="🐾 Погладить"), _KB(text="🧶 Поиграть")],
            [_KB(text="◀️ К играм")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Что сделать с котом?",
    )


def kb_reminders() -> ReplyKeyboardMarkup:
    """Level 2 — reminders submenu."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [_KB(text="➕ Создать напоминание")],
            [_KB(text="📋 Мои напоминания")],
            [_KB(text="◀️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Управление напоминаниями...",
    )


def kb_weather() -> ReplyKeyboardMarkup:
    """Level 2 — weather submenu."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [_KB(text="🌡️ Текущая погода")],
            [_KB(text="➕ Добавить город"), _KB(text="➖ Удалить город")],
            [_KB(text="◀️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Управление погодой...",
    )


def kb_quotes() -> ReplyKeyboardMarkup:
    """Level 2 — quotes submenu."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [_KB(text="👑 Золотой фонд")],
            [_KB(text="🌚 Тёмная лошадка")],
            [_KB(text="🤔 Со смыслом")],
            [_KB(text="🗿 А чо а всмысле")],
            [_KB(text="🤡 Юрий Гальцев")],
            [_KB(text="📊 Топ авторов")],
            [_KB(text="◀️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выбери раздел цитат...",
    )


def kb_stats() -> ReplyKeyboardMarkup:
    """Level 2 — stats submenu."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [_KB(text="👤 Мой профиль")],
            [_KB(text="🏆 Таблица лидеров")],
            [_KB(text="🎖️ Мои награды")],
            [_KB(text="◀️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выбери статистику...",
    )


def kb_help() -> ReplyKeyboardMarkup:
    """Level 2 — help submenu."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [_KB(text="📖 Полная справка")],
            [_KB(text="🎮 О играх")],
            [_KB(text="📋 О командах")],
            [_KB(text="◀️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выбери раздел справки...",
    )
