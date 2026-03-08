import asyncio
import random
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from app.db import repositories as repo
from app.utils.helpers import safe_edit_text
from app.texts import (
    BJ_BALANCE_ZERO, BJ_WEEKLY_CLAIMED, BJ_WEEKLY_COOLDOWN,
    BJ_WIN, BJ_LOSS, BJ_DRAW, BJ_BUST, BJ_DEALER_BUST,
    BJ_TIMEOUT, GAMES_DISABLED,
)

router = Router()

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
STAKES = [50, 100, 250, 500]
GAME_TIMEOUT = 180  # 3 minutes

# Active games: (chat_id, user_id) -> BlackjackGame
_games: dict[tuple[int, int], "BlackjackGame"] = {}


class BlackjackGame:
    def __init__(self, chat_id: int, user_id: int, stake: int, msg_id: int, bot: Bot):
        self.chat_id = chat_id
        self.user_id = user_id
        self.stake = stake
        self.msg_id = msg_id
        self.bot = bot
        self.player_hand: list[str] = []
        self.dealer_hand: list[str] = []
        self._deck = self._new_deck()
        self._task: asyncio.Task | None = None

    def _new_deck(self) -> list[str]:
        deck = [f"{r}{s}" for s in SUITS for r in RANKS]
        random.shuffle(deck)
        return deck

    def _draw(self) -> str:
        return self._deck.pop()

    def deal(self):
        self.player_hand = [self._draw(), self._draw()]
        self.dealer_hand = [self._draw(), self._draw()]

    def hit(self):
        self.player_hand.append(self._draw())

    def dealer_play(self):
        while _score(self.dealer_hand) < 17:
            self.dealer_hand.append(self._draw())

    def cancel_task(self):
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None


def _card_value(card: str) -> int:
    rank = card[:-1]  # strip suit
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)


def _score(hand: list[str]) -> int:
    total = sum(_card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[:-1] == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _hand_str(hand: list[str]) -> str:
    return "  ".join(hand)


def _stake_kb(profile: dict) -> InlineKeyboardMarkup:
    balance = profile["balance"]
    buttons = []
    row = []
    for s in STAKES:
        if s <= balance:
            row.append(InlineKeyboardButton(text=f"{s}💰", callback_data=f"bj:stake:{s}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _action_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🃏 Ещё", callback_data="bj:hit"),
        InlineKeyboardButton(text="✋ Хватит", callback_data="bj:stand"),
    ]])


def _game_text(game: BlackjackGame, dealer_hidden: bool = True) -> str:
    pscore = _score(game.player_hand)
    if dealer_hidden:
        dealer_display = f"{game.dealer_hand[0]}  🂠"
        dscore = _card_value(game.dealer_hand[0])
        dscore_str = f"~{dscore}"
    else:
        dealer_display = _hand_str(game.dealer_hand)
        dscore = _score(game.dealer_hand)
        dscore_str = str(dscore)

    return (
        f"🃏 <b>Блэкджек</b> | Ставка: {game.stake}💰\n\n"
        f"<b>Дилер</b> [{dscore_str}]:\n  {dealer_display}\n\n"
        f"<b>Ты</b> [{pscore}]:\n  {_hand_str(game.player_hand)}"
    )


async def _timeout_game(key: tuple[int, int]):
    await asyncio.sleep(GAME_TIMEOUT)
    game = _games.pop(key, None)
    if not game:
        return
    try:
        await game.bot.edit_message_text(
            BJ_TIMEOUT,
            chat_id=game.chat_id,
            message_id=game.msg_id,
            reply_markup=None,
        )
    except Exception:
        pass


async def _finish(game: BlackjackGame, outcome: str, result_line: str):
    key = (game.chat_id, game.user_id)
    _games.pop(key, None)
    game.cancel_task()

    if outcome == "win":
        delta = game.stake
    elif outcome == "loss":
        delta = -game.stake
    else:
        delta = 0

    new_balance = await repo.update_blackjack_balance(game.chat_id, game.user_id, delta, outcome)

    sign = "+" if delta > 0 else ""
    text = (
        f"{_game_text(game, dealer_hidden=False)}\n\n"
        f"{result_line}\n"
        f"{'➕' if delta >= 0 else '➖'} {sign}{delta}💰 → Баланс: {new_balance}💰"
    )
    try:
        await game.bot.edit_message_text(
            text, chat_id=game.chat_id, message_id=game.msg_id,
            reply_markup=None, parse_mode="HTML",
        )
    except Exception:
        pass


@router.message(Command("blackjack"))
async def cmd_blackjack(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer(GAMES_DISABLED)
        return

    key = (chat_id, user_id)
    if key in _games:
        await message.answer("🃏 У тебя уже идёт игра! Доиграй сначала.")
        return

    profile = await repo.get_blackjack_profile(chat_id, user_id)
    if profile["balance"] <= 0:
        await message.answer(BJ_BALANCE_ZERO)
        return

    if not any(s <= profile["balance"] for s in STAKES):
        await message.answer(f"💰 Баланс {profile['balance']}💰 — слишком мало для ставки. Получи недельные кредиты: /weekly")
        return

    kb = _stake_kb(profile)
    sent = await message.answer(
        f"🃏 <b>Блэкджек</b>\n\n"
        f"💰 Баланс: {profile['balance']}💰\n\n"
        f"Выбери ставку:",
        reply_markup=kb,
        parse_mode="HTML",
    )

    _games[key] = BlackjackGame(chat_id, user_id, 0, sent.message_id, bot)
    game = _games[key]
    game._task = asyncio.create_task(_timeout_game(key))


@router.callback_query(F.data == "game:blackjack")
async def cb_blackjack_menu(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await callback.answer(GAMES_DISABLED, show_alert=True)
        return

    key = (chat_id, user_id)
    if key in _games:
        await callback.answer("🃏 У тебя уже идёт игра!", show_alert=True)
        return

    profile = await repo.get_blackjack_profile(chat_id, user_id)
    if profile["balance"] <= 0:
        await callback.answer(BJ_BALANCE_ZERO, show_alert=True)
        return

    if not any(st <= profile["balance"] for st in STAKES):
        await callback.answer(
            f"💰 Баланс {profile['balance']}💰 — слишком мало для ставки. Используй /weekly",
            show_alert=True,
        )
        return

    kb = _stake_kb(profile)
    await safe_edit_text(
        callback.message,
        f"🃏 <b>Блэкджек</b>\n\n"
        f"💰 Баланс: {profile['balance']}💰\n\n"
        f"Выбери ставку:",
        reply_markup=kb,
        parse_mode="HTML",
    )

    _games[key] = BlackjackGame(chat_id, user_id, 0, callback.message.message_id, bot)
    game = _games[key]
    game._task = asyncio.create_task(_timeout_game(key))
    await callback.answer()


@router.callback_query(F.data.startswith("bj:stake:"))
async def cb_stake(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    key = (chat_id, user_id)

    stake = int(callback.data.split(":")[2])
    profile = await repo.get_blackjack_profile(chat_id, user_id)

    if profile["balance"] < stake:
        await callback.answer("Недостаточно кредитов!", show_alert=True)
        return

    game = _games.get(key)
    if not game:
        await callback.answer("Игра не найдена, начни заново.", show_alert=True)
        return

    game.cancel_task()
    game.stake = stake
    game.deal()

    pscore = _score(game.player_hand)

    # Natural blackjack (21 on first 2 cards)
    if pscore == 21:
        await _finish(game, "win", BJ_WIN)
        await callback.answer()
        return

    text = _game_text(game, dealer_hidden=True)
    try:
        await callback.message.edit_text(text, reply_markup=_action_kb(), parse_mode="HTML")
    except Exception:
        pass

    game._task = asyncio.create_task(_timeout_game(key))
    await callback.answer()


@router.callback_query(F.data == "bj:hit")
async def cb_hit(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    key = (chat_id, user_id)

    game = _games.get(key)
    if not game or game.stake == 0:
        await callback.answer("Игра не найдена.", show_alert=True)
        return
    if callback.from_user.id != user_id:
        await callback.answer("Это не твоя игра!", show_alert=True)
        return

    game.cancel_task()
    game.hit()
    pscore = _score(game.player_hand)

    if pscore > 21:
        await _finish(game, "loss", BJ_BUST)
    else:
        text = _game_text(game, dealer_hidden=True)
        try:
            await callback.message.edit_text(text, reply_markup=_action_kb(), parse_mode="HTML")
        except Exception:
            pass
        game._task = asyncio.create_task(_timeout_game(key))

    await callback.answer()


@router.callback_query(F.data == "bj:stand")
async def cb_stand(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    key = (chat_id, user_id)

    game = _games.get(key)
    if not game or game.stake == 0:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    game.cancel_task()
    game.dealer_play()

    pscore = _score(game.player_hand)
    dscore = _score(game.dealer_hand)

    if dscore > 21:
        outcome, line = "win", BJ_DEALER_BUST
    elif pscore > dscore:
        outcome, line = "win", BJ_WIN
    elif pscore < dscore:
        outcome, line = "loss", BJ_LOSS
    else:
        outcome, line = "draw", BJ_DRAW

    await _finish(game, outcome, line)
    await callback.answer()


@router.message(Command("weekly"))
async def cmd_weekly(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    given = await repo.claim_weekly_credits(chat_id, user_id)
    if given:
        profile = await repo.get_blackjack_profile(chat_id, user_id)
        await message.answer(BJ_WEEKLY_CLAIMED.format(balance=profile["balance"]))
    else:
        await message.answer(BJ_WEEKLY_COOLDOWN)


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    profile = await repo.get_blackjack_profile(message.chat.id, message.from_user.id)
    await message.answer(
        f"💰 <b>Твой баланс</b>\n\n"
        f"Кредиты: <b>{profile['balance']}💰</b>\n"
        f"Макс. баланс: {profile['max_balance']}💰\n"
        f"Игр: {profile['total_games']} | "
        f"Побед: {profile['wins']} | "
        f"Поражений: {profile['losses']} | "
        f"Ничьих: {profile['draws']}",
        parse_mode="HTML",
    )
