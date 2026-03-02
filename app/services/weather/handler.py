import aiohttp
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.db import repositories as repo
from app.config import settings as cfg
from app.bot.keyboards import weather_menu_kb, weather_cities_delete_kb, back_to_menu_kb

router = Router()


class WeatherAddCity(StatesGroup):
    waiting_city = State()


WEATHER_ICONS = {
    "01": "\u2600\ufe0f", "02": "\U0001f324\ufe0f", "03": "\u2601\ufe0f", "04": "\u2601\ufe0f",
    "09": "\U0001f327\ufe0f", "10": "\U0001f326\ufe0f", "11": "\u26c8\ufe0f", "13": "\u2744\ufe0f", "50": "\U0001f32b\ufe0f",
}


async def fetch_weather(city: str) -> str | None:
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": cfg.OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "ru",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        icon_code = data["weather"][0]["icon"][:2]
        icon = WEATHER_ICONS.get(icon_code, "\U0001f321\ufe0f")
        temp = data["main"]["temp"]
        feels = data["main"]["feels_like"]
        desc = data["weather"][0]["description"]
        humidity = data["main"]["humidity"]
        wind = data["wind"]["speed"]

        return (
            f"{icon} <b>{city}</b>\n"
            f"\U0001f321\ufe0f \u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430: {temp:.0f}\u00b0C (\u043e\u0449\u0443\u0449\u0430\u0435\u0442\u0441\u044f {feels:.0f}\u00b0C)\n"
            f"\U0001f4a7 \u0412\u043b\u0430\u0436\u043d\u043e\u0441\u0442\u044c: {humidity}%\n"
            f"\U0001f4a8 \u0412\u0435\u0442\u0435\u0440: {wind} \u043c/\u0441\n"
            f"\u2601\ufe0f {desc.capitalize()}"
        )
    except Exception:
        return None


async def get_weather_for_chat(chat_id: int) -> str:
    cities = await repo.get_weather_cities(chat_id)
    if not cities:
        return "\u26c5 \u041d\u0435\u0442 \u0433\u043e\u0440\u043e\u0434\u043e\u0432. \u0414\u043e\u0431\u0430\u0432\u044c \u0447\u0435\u0440\u0435\u0437 /city_add"

    results = []
    for city in cities:
        w = await fetch_weather(city)
        if w:
            results.append(w)
        else:
            results.append(f"\u274c <b>{city}</b>: \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0434\u0430\u043d\u043d\u044b\u0435")

    return "\U0001f324\ufe0f <b>\u041f\u043e\u0433\u043e\u0434\u0430</b>\n\n" + "\n\n".join(results)


@router.message(Command("weather"))
async def cmd_weather(message: Message):
    text = await get_weather_for_chat(message.chat.id)
    await message.answer(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "weather:now")
async def cb_weather_now(callback: CallbackQuery):
    text = await get_weather_for_chat(callback.message.chat.id)
    await callback.message.edit_text(text, reply_markup=weather_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(Command("city_add"))
async def cmd_city_add(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /city_add \u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0433\u043e\u0440\u043e\u0434\u0430")
        return
    city = args[1].strip()
    ok = await repo.add_weather_city(message.chat.id, city)
    if ok:
        await message.answer(f"\u2705 \u0413\u043e\u0440\u043e\u0434 <b>{city}</b> \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d!", parse_mode="HTML")
    else:
        await message.answer(f"\u274c \u041b\u0438\u043c\u0438\u0442 \u0433\u043e\u0440\u043e\u0434\u043e\u0432 ({cfg.MAX_WEATHER_CITIES_PER_CHAT}) \u0434\u043e\u0441\u0442\u0438\u0433\u043d\u0443\u0442!")


@router.message(Command("city_del"))
async def cmd_city_del(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /city_del \u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0433\u043e\u0440\u043e\u0434\u0430")
        return
    city = args[1].strip()
    await repo.remove_weather_city(message.chat.id, city)
    await message.answer(f"\u2705 \u0413\u043e\u0440\u043e\u0434 <b>{city}</b> \u0443\u0434\u0430\u043b\u0451\u043d.", parse_mode="HTML")


@router.message(Command("weather_time"))
async def cmd_weather_time(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    role = await repo.get_user_role(user_id, chat_id)
    if role != "owner" and user_id != cfg.SUPERADMIN_ID:
        await message.answer("\u26d4 \u0422\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f OWNER!")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /weather_time HH:MM")
        return

    time_str = args[1].strip()
    try:
        h, m = map(int, time_str.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("\u274c \u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 HH:MM")
        return

    await repo.update_setting(chat_id, "weather_time", time_str)
    await message.answer(f"\u2705 \u0412\u0440\u0435\u043c\u044f \u0440\u0430\u0441\u0441\u044b\u043b\u043a\u0438 \u043f\u043e\u0433\u043e\u0434\u044b: <b>{time_str}</b>", parse_mode="HTML")


@router.callback_query(F.data == "weather:add_city")
async def cb_weather_add_city(callback: CallbackQuery, state: FSMContext):
    await state.set_state(WeatherAddCity.waiting_city)
    await callback.message.edit_text(
        "\U0001f3d9\ufe0f \u041d\u0430\u043f\u0438\u0448\u0438 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0433\u043e\u0440\u043e\u0434\u0430:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(WeatherAddCity.waiting_city)
async def process_add_city(message: Message, state: FSMContext):
    await state.clear()
    city = message.text.strip()
    ok = await repo.add_weather_city(message.chat.id, city)
    if ok:
        await message.answer(f"\u2705 \u0413\u043e\u0440\u043e\u0434 <b>{city}</b> \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d!", parse_mode="HTML",
                             reply_markup=weather_menu_kb())
    else:
        await message.answer(f"\u274c \u041b\u0438\u043c\u0438\u0442 \u0433\u043e\u0440\u043e\u0434\u043e\u0432 \u0434\u043e\u0441\u0442\u0438\u0433\u043d\u0443\u0442!", reply_markup=weather_menu_kb())


@router.callback_query(F.data == "weather:del_city")
async def cb_weather_del_city(callback: CallbackQuery):
    cities = await repo.get_weather_cities(callback.message.chat.id)
    if not cities:
        await callback.message.edit_text("\u041d\u0435\u0442 \u0433\u043e\u0440\u043e\u0434\u043e\u0432.", reply_markup=weather_menu_kb())
        await callback.answer()
        return
    await callback.message.edit_text(
        "\U0001f3d9\ufe0f \u0412\u044b\u0431\u0435\u0440\u0438 \u0433\u043e\u0440\u043e\u0434 \u0434\u043b\u044f \u0443\u0434\u0430\u043b\u0435\u043d\u0438\u044f:",
        reply_markup=weather_cities_delete_kb(cities),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("weather:remove:"))
async def cb_weather_remove_city(callback: CallbackQuery):
    city = callback.data.split(":", 2)[2]
    await repo.remove_weather_city(callback.message.chat.id, city)
    cities = await repo.get_weather_cities(callback.message.chat.id)
    if not cities:
        await callback.message.edit_text("\u2705 \u0412\u0441\u0435 \u0433\u043e\u0440\u043e\u0434\u0430 \u0443\u0434\u0430\u043b\u0435\u043d\u044b.", reply_markup=weather_menu_kb())
    else:
        await callback.message.edit_reply_markup(reply_markup=weather_cities_delete_kb(cities))
    await callback.answer(f"\u2705 {city} \u0443\u0434\u0430\u043b\u0451\u043d")
