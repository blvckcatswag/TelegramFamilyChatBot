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
    "01": "☀️", "02": "🌤️", "03": "☁️", "04": "☁️",
    "09": "🌧️", "10": "🌦️", "11": "⛈️", "13": "❄️", "50": "🌫️",
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
        icon = WEATHER_ICONS.get(icon_code, "🌡️")
        temp = data["main"]["temp"]
        feels = data["main"]["feels_like"]
        desc = data["weather"][0]["description"]
        humidity = data["main"]["humidity"]
        wind = data["wind"]["speed"]

        return (
            f"{icon} <b>{city}</b>\n"
            f"🌡️ Температура: {temp:.0f}°C (ощущается {feels:.0f}°C)\n"
            f"💧 Влажность: {humidity}%\n"
            f"💨 Ветер: {wind} м/с\n"
            f"☁️ {desc.capitalize()}"
        )
    except Exception:
        return None


async def get_weather_for_chat(chat_id: int) -> str:
    cities = await repo.get_weather_cities(chat_id)
    if not cities:
        return "⛅ Нет городов. Добавь через /city_add"

    results = []
    for city in cities:
        w = await fetch_weather(city)
        if w:
            results.append(w)
        else:
            results.append(f"❌ <b>{city}</b>: не удалось получить данные")

    return "🌤️ <b>Погода</b>\n\n" + "\n\n".join(results)


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
        await message.answer("Использование: /city_add Название города")
        return
    city = args[1].strip()
    ok = await repo.add_weather_city(message.chat.id, city)
    if ok:
        await message.answer(f"✅ Город <b>{city}</b> добавлен!", parse_mode="HTML")
    else:
        await message.answer(f"❌ Лимит городов ({cfg.MAX_WEATHER_CITIES_PER_CHAT}) достигнут!")


@router.message(Command("city_del"))
async def cmd_city_del(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /city_del Название города")
        return
    city = args[1].strip()
    await repo.remove_weather_city(message.chat.id, city)
    await message.answer(f"✅ Город <b>{city}</b> удалён.", parse_mode="HTML")


@router.message(Command("weather_time"))
async def cmd_weather_time(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    role = await repo.get_user_role(user_id, chat_id)
    if role != "owner" and user_id != cfg.SUPERADMIN_ID:
        await message.answer("⛔ Только для OWNER!")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /weather_time HH:MM")
        return

    time_str = args[1].strip()
    try:
        h, m = map(int, time_str.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используй HH:MM")
        return

    await repo.update_setting(chat_id, "weather_time", time_str)
    await message.answer(f"✅ Время рассылки погоды: <b>{time_str}</b>", parse_mode="HTML")


@router.callback_query(F.data == "weather:add_city")
async def cb_weather_add_city(callback: CallbackQuery, state: FSMContext):
    await state.set_state(WeatherAddCity.waiting_city)
    await callback.message.edit_text(
        "🏙️ Напиши название города:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(WeatherAddCity.waiting_city)
async def process_add_city(message: Message, state: FSMContext):
    await state.clear()
    city = message.text.strip()
    ok = await repo.add_weather_city(message.chat.id, city)
    if ok:
        await message.answer(f"✅ Город <b>{city}</b> добавлен!", parse_mode="HTML",
                             reply_markup=weather_menu_kb())
    else:
        await message.answer("❌ Лимит городов достигнут!", reply_markup=weather_menu_kb())


@router.callback_query(F.data == "weather:del_city")
async def cb_weather_del_city(callback: CallbackQuery):
    cities = await repo.get_weather_cities(callback.message.chat.id)
    if not cities:
        await callback.message.edit_text("Нет городов.", reply_markup=weather_menu_kb())
        await callback.answer()
        return
    await callback.message.edit_text(
        "🏙️ Выбери город для удаления:",
        reply_markup=weather_cities_delete_kb(cities),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("weather:remove:"))
async def cb_weather_remove_city(callback: CallbackQuery):
    city = callback.data.split(":", 2)[2]
    await repo.remove_weather_city(callback.message.chat.id, city)
    cities = await repo.get_weather_cities(callback.message.chat.id)
    if not cities:
        await callback.message.edit_text("✅ Все города удалены.", reply_markup=weather_menu_kb())
    else:
        await callback.message.edit_reply_markup(reply_markup=weather_cities_delete_kb(cities))
    await callback.answer(f"✅ {city} удалён")
