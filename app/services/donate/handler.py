import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    LabeledPrice, Message, PreCheckoutQuery,
)

from app.config import settings as cfg
from app.utils.reply_keyboards import kb_start

router = Router()
logger = logging.getLogger(__name__)

STARS_OPTIONS = [5, 10, 25, 50, 100]


class DonateForm(StatesGroup):
    waiting_custom_amount = State()


def _donate_kb() -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton(text=f"{a} ⭐", callback_data=f"donate:stars:{a}")
        for a in STARS_OPTIONS[:3]
    ]
    row2 = [
        InlineKeyboardButton(text=f"{a} ⭐", callback_data=f"donate:stars:{a}")
        for a in STARS_OPTIONS[3:]
    ]
    row2.append(InlineKeyboardButton(text="✏️ Своя сумма", callback_data="donate:stars:custom"))
    return InlineKeyboardMarkup(inline_keyboard=[
        row1,
        row2,
        [InlineKeyboardButton(text="🪙 Крипта", callback_data="donate:crypto")],
    ])


async def _send_stars_invoice(chat_id: int, amount: int, bot) -> None:
    await bot.send_invoice(
        chat_id=chat_id,
        title="Поддержать разработчика",
        description=f"Добровольный донат {amount} ⭐. Не хочешь — не донать, бот работает бесплатно.",
        payload=f"donation_{amount}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Донат", amount=amount)],
    )


async def cmd_donate(message: Message) -> None:
    await message.answer(
        "💝 <b>Поддержать разработчика</b>\n\n"
        "Бот написан на свои деньги и работает бесплатно.\n"
        "Если хочешь сказать спасибо — можно задонатить звёздами или крипто.\n"
        "Не хочешь — всё равно спасибо что пользуешься.\n\n"
        "Выбери способ:",
        reply_markup=_donate_kb(),
        parse_mode="HTML",
    )


@router.message(Command("donate"))
async def cmd_donate_command(message: Message) -> None:
    await cmd_donate(message)


@router.callback_query(F.data.regexp(r"^donate:stars:\d+$"))
async def cb_donate_stars(callback: CallbackQuery) -> None:
    amount = int(callback.data.split(":")[2])
    await _send_stars_invoice(callback.message.chat.id, amount, callback.bot)
    await callback.answer()


@router.callback_query(F.data == "donate:stars:custom")
async def cb_donate_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DonateForm.waiting_custom_amount)
    await callback.message.answer("✏️ Напиши сколько звёзд хочешь задонатить (от 1 до 2500):")
    await callback.answer()


@router.message(DonateForm.waiting_custom_amount)
async def process_custom_amount(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("❌ Напиши просто число, например: 150")
        return
    amount = int(message.text.strip())
    if not (1 <= amount <= 2500):
        await message.answer("❌ Сумма должна быть от 1 до 2500 звёзд.")
        return
    await state.clear()
    await _send_stars_invoice(message.chat.id, amount, message.bot)


@router.callback_query(F.data == "donate:crypto")
async def cb_donate_crypto(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "🪙 <b>Крипто-адреса для доната</b>\n\n"
        f"<b>USDT TRC20:</b>\n<code>{cfg.CRYPTO_USDT_TRC20}</code>\n\n"
        f"<b>TON:</b>\n<code>{cfg.CRYPTO_TON}</code>\n\n"
        "Нажми на адрес чтобы скопировать, переведи через свой кошелёк.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    stars = message.successful_payment.total_amount
    logger.info("Donation: %s stars from user %s", stars, message.from_user.id)

    await message.answer(
        f"🙏 Спасибо за {stars} ⭐! Это очень приятно и помогает.",
        reply_markup=kb_start(),
    )

    if cfg.SUPERADMIN_ID:
        user = message.from_user
        user_info = f"@{user.username}" if user.username else user.first_name
        try:
            await message.bot.send_message(
                cfg.SUPERADMIN_ID,
                f"⭐ <b>Новый донат!</b>\n\nОт: {user_info} ({user.id})\nСумма: {stars} звёзд",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Не удалось уведомить суперадмина о донате")
