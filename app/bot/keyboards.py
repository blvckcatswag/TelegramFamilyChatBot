from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f3ae \u0418\u0433\u0440\u044b", callback_data="menu:games"),
         InlineKeyboardButton(text="\U0001f4c5 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f", callback_data="menu:reminders")],
        [InlineKeyboardButton(text="\u26c5 \u041f\u043e\u0433\u043e\u0434\u0430", callback_data="menu:weather"),
         InlineKeyboardButton(text="\U0001f4ac \u0426\u0438\u0442\u0430\u0442\u044b", callback_data="menu:quotes")],
        [InlineKeyboardButton(text="\U0001f4ca \u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430", callback_data="menu:stats"),
         InlineKeyboardButton(text="\u2139\ufe0f \u0421\u043f\u0440\u0430\u0432\u043a\u0430", callback_data="menu:help")],
        [InlineKeyboardButton(text="\u2699\ufe0f \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438", callback_data="menu:settings")],
    ])


def games_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f335 \u041a\u0430\u043a\u0442\u0443\u0441", callback_data="game:cactus"),
         InlineKeyboardButton(text="\U0001f408 \u041a\u043e\u0442", callback_data="game:cat")],
        [InlineKeyboardButton(text="\U0001f9f9 \u041f\u043e\u0440\u044f\u0434\u043e\u043a \u0434\u043e\u043c\u0430", callback_data="game:home"),
         InlineKeyboardButton(text="\u2694\ufe0f \u0414\u0443\u044d\u043b\u044c", callback_data="game:duel")],
        [InlineKeyboardButton(text="\U0001f52b \u0420\u0443\u043b\u0435\u0442\u043a\u0430", callback_data="game:roulette")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="menu:main")],
    ])


def reminders_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2795 \u0421\u043e\u0437\u0434\u0430\u0442\u044c", callback_data="remind:create")],
        [InlineKeyboardButton(text="\U0001f4cb \u041c\u043e\u0438 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f", callback_data="remind:list")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="menu:main")],
    ])


def weather_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f321\ufe0f \u041f\u043e\u0433\u043e\u0434\u0430 \u0441\u0435\u0439\u0447\u0430\u0441", callback_data="weather:now")],
        [InlineKeyboardButton(text="\u2795 \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0433\u043e\u0440\u043e\u0434", callback_data="weather:add_city"),
         InlineKeyboardButton(text="\u2796 \u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0433\u043e\u0440\u043e\u0434", callback_data="weather:del_city")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="menu:main")],
    ])


def quotes_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f3b2 \u0421\u043b\u0443\u0447\u0430\u0439\u043d\u0430\u044f", callback_data="quote:random")],
        [InlineKeyboardButton(text="\U0001f4d6 \u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 5", callback_data="quote:last")],
        [InlineKeyboardButton(text="\U0001f4ca \u0421\u0447\u0451\u0442\u0447\u0438\u043a \u0446\u0438\u0442\u0430\u0442", callback_data="quote:counts")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="menu:main")],
    ])


def stats_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f464 \u041c\u043e\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c", callback_data="stats:my")],
        [InlineKeyboardButton(text="\U0001f3c6 \u0420\u0435\u0439\u0442\u0438\u043d\u0433\u0438", callback_data="stats:top")],
        [InlineKeyboardButton(text="\U0001f3c5 \u041d\u0430\u0433\u0440\u0430\u0434\u044b", callback_data="stats:awards")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="menu:main")],
    ])


def settings_kb(settings: dict) -> InlineKeyboardMarkup:
    def toggle(key: str, label: str) -> InlineKeyboardButton:
        state = "\u2705" if settings.get(key) else "\u274c"
        return InlineKeyboardButton(text=f"{state} {label}", callback_data=f"setting:{key}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [toggle("weather_enabled", "\u041f\u043e\u0433\u043e\u0434\u0430"), toggle("games_enabled", "\u0418\u0433\u0440\u044b")],
        [toggle("translator_enabled", "\u041f\u0435\u0440\u0435\u0432\u043e\u0434\u0447\u0438\u043a"), toggle("quotes_enabled", "\u0426\u0438\u0442\u0430\u0442\u044b")],
        [toggle("birthdays_enabled", "\u0414\u043d\u0438 \u0440\u043e\u0436\u0434\u0435\u043d\u0438\u044f")],
        [InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="menu:main")],
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u25c0\ufe0f \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e", callback_data="menu:main")],
    ])


def duel_accept_kb(challenger_id: int, mute_minutes: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="\u2694\ufe0f \u041f\u0440\u0438\u043d\u044f\u0442\u044c \u0434\u0443\u044d\u043b\u044c",
            callback_data=f"duel:accept:{challenger_id}:{mute_minutes}",
        )],
    ])


def roulette_join_kb(roulette_msg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="\U0001f52b \u042f \u0443\u0447\u0430\u0441\u0442\u0432\u0443\u044e!",
            callback_data=f"roulette:join:{roulette_msg_id}",
        )],
        [InlineKeyboardButton(
            text="\U0001f3b0 \u041d\u0430\u0447\u0430\u0442\u044c!",
            callback_data=f"roulette:start:{roulette_msg_id}",
        )],
    ])


def reminder_delete_kb(reminders: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for r in reminders:
        text_preview = r["text"][:30] + ("..." if len(r["text"]) > 30 else "")
        buttons.append([InlineKeyboardButton(
            text=f"\u274c {text_preview} ({r['run_at'][:16]})",
            callback_data=f"remind:del:{r['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="menu:reminders")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def weather_cities_delete_kb(cities: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    for city in cities:
        buttons.append([InlineKeyboardButton(
            text=f"\u274c {city}",
            callback_data=f"weather:remove:{city}",
        )])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f \u041d\u0430\u0437\u0430\u0434", callback_data="menu:weather")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
