import asyncio
import logging
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
    BJ_DOUBLE_DOWN_WIN, BJ_DOUBLE_DOWN_BUST, BJ_DOUBLE_DOWN_LOSS, BJ_DOUBLE_DOWN_DEALER_BUST,
    BJ_NATURAL, BJ_NATURAL_PUSH,
    BJ_TIMEOUT, GAMES_DISABLED,
    BJ_NO_LENDERS, BJ_LOAN_CHOOSE, BJ_LOAN_REQUEST_SENT, BJ_LOAN_INCOMING,
    BJ_LOAN_ACCEPTED_BORROWER, BJ_LOAN_DECLINED_BORROWER,
    BJ_LOAN_ACCEPTED_LENDER, BJ_LOAN_DECLINED_LENDER,
    BJ_LOAN_NO_FUNDS, BJ_LOAN_ALREADY_PENDING,
)

router = Router()
logger = logging.getLogger(__name__)

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
STAKES = [50, 100, 250, 500]
GAME_TIMEOUT = 180  # 3 minutes
LOAN_AMOUNT = 1000

# Active games: (chat_id, user_id) -> BlackjackGame
_games: dict[tuple[int, int], "BlackjackGame"] = {}

# Pending loan requests: "{chat_id}:{requester_id}:{lender_id}" -> {requester_name, lender_id, chat_id, req_msg_id}
_pending_loans: dict[str, dict] = {}


class BlackjackGame:
    def __init__(self, chat_id: int, user_id: int, stake: int, msg_id: int, bot: Bot):
        self.chat_id = chat_id
        self.user_id = user_id
        self.stake = stake
        self.msg_id = msg_id
        self.bot = bot
        self.player_hand: list[str] = []
        self.dealer_hand: list[str] = []
        self.doubled = False
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
    rank = card[:-1]
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


def _win_rate(profile: dict) -> str:
    total = profile.get("total_games") or 0
    wins = profile.get("wins") or 0
    losses = profile.get("losses") or 0
    if total == 0:
        return "W:0 / L:0"
    pct = round(wins / total * 100)
    return f"W:{wins} / L:{losses} ({pct}%)"


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


def _action_kb(can_double: bool = False) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text="🃏 Ещё", callback_data="bj:hit"),
        InlineKeyboardButton(text="✋ Хватит", callback_data="bj:stand"),
    ]
    buttons = [row]
    if can_double:
        buttons.append([InlineKeyboardButton(text="2️⃣ Удвоить ставку", callback_data="bj:double")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _play_again_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Сыграть ещё", callback_data="game:blackjack"),
    ]])


def _borrow_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🙏 Унизительно попросить в долг", callback_data="bj:borrow"),
    ]])


def _game_text(game: BlackjackGame, dealer_hidden: bool = True) -> str:
    pscore = _score(game.player_hand)
    stake_label = f"{game.stake}💰" + (" (×2)" if game.doubled else "")
    if dealer_hidden:
        dealer_display = f"{game.dealer_hand[0]}  🂠"
        dscore_str = f"~{_card_value(game.dealer_hand[0])}"
    else:
        dealer_display = _hand_str(game.dealer_hand)
        dscore_str = str(_score(game.dealer_hand))

    return (
        f"🃏 <b>Блэкджек</b> | Ставка: {stake_label}\n\n"
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
            reply_markup=_play_again_kb(),
        )
    except Exception:
        pass


async def _finish(game: BlackjackGame, outcome: str, result_line: str):
    key = (game.chat_id, game.user_id)
    _games.pop(key, None)
    game.cancel_task()

    effective_stake = game.stake * (2 if game.doubled else 1)
    if outcome == "win":
        delta = effective_stake
    elif outcome == "loss":
        delta = -effective_stake
    else:
        delta = 0

    new_balance = await repo.update_blackjack_balance(game.chat_id, game.user_id, delta, outcome)

    sign = "+" if delta > 0 else ""
    text = (
        f"{_game_text(game, dealer_hidden=False)}\n\n"
        f"{result_line}\n"
        f"{'➕' if delta >= 0 else '➖'} {sign}{delta}💰 → Баланс: {new_balance}💰"
    )
    kb = _play_again_kb()
    if new_balance == 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Сыграть ещё", callback_data="game:blackjack")],
            [InlineKeyboardButton(text="🙏 Унизительно попросить в долг", callback_data="bj:borrow")],
        ])
    try:
        await game.bot.edit_message_text(
            text, chat_id=game.chat_id, message_id=game.msg_id,
            reply_markup=kb, parse_mode="HTML",
        )
    except Exception:
        pass


async def _start_round(chat_id: int, user_id: int, bot: Bot, msg_id: int, stake: int):
    """Deal cards and show the initial game state."""
    key = (chat_id, user_id)
    game = _games[key]
    game.cancel_task()
    game.stake = stake
    game.deal()

    pscore = _score(game.player_hand)
    dscore = _score(game.dealer_hand)

    # Natural blackjack check
    if pscore == 21:
        if dscore == 21:
            await _finish(game, "draw", BJ_NATURAL_PUSH)
        else:
            await _finish(game, "win", BJ_NATURAL)
        return

    profile = await repo.get_blackjack_profile(chat_id, user_id)
    can_double = profile["balance"] >= stake * 2  # need enough for both the original bet and the double
    text = _game_text(game, dealer_hidden=True)
    try:
        await bot.edit_message_text(
            text, chat_id=chat_id, message_id=msg_id,
            reply_markup=_action_kb(can_double=can_double), parse_mode="HTML",
        )
    except Exception:
        pass

    game._task = asyncio.create_task(_timeout_game(key))


# ── Entry points ───────────────────────────────────────────────────────

async def _send_lobby(chat_id: int, user_id: int, bot: Bot, send_fn):
    """Show stake selection or zero-balance message."""
    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        return GAMES_DISABLED, None

    key = (chat_id, user_id)
    if key in _games:
        return "🃏 У тебя уже идёт игра! Доиграй сначала.", None

    profile = await repo.get_blackjack_profile(chat_id, user_id)
    if profile["balance"] <= 0:
        return BJ_BALANCE_ZERO, _borrow_kb()

    if not any(s <= profile["balance"] for s in STAKES):
        return (
            f"💰 Баланс {profile['balance']}💰 — слишком мало для ставки. "
            f"Получи недельные кредиты: /weekly"
        ), None

    return None, None  # signal: show lobby


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
        await message.answer(BJ_BALANCE_ZERO, reply_markup=_borrow_kb())
        return

    if not any(s <= profile["balance"] for s in STAKES):
        await message.answer(
            f"💰 Баланс {profile['balance']}💰 — слишком мало для ставки. Получи /weekly"
        )
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
    _games[key]._task = asyncio.create_task(_timeout_game(key))


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
        await safe_edit_text(callback.message, BJ_BALANCE_ZERO,
                             reply_markup=_borrow_kb(), parse_mode="HTML")
        await callback.answer()
        return

    if not any(st <= profile["balance"] for st in STAKES):
        await callback.answer(
            f"💰 Баланс {profile['balance']}💰 — слишком мало. Используй /weekly",
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
    _games[key]._task = asyncio.create_task(_timeout_game(key))
    await callback.answer()


# ── Stake selection ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bj:stake:"))
async def cb_stake(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    key = (chat_id, user_id)

    try:
        stake = int(callback.data.split(":")[2])
        profile = await repo.get_blackjack_profile(chat_id, user_id)

        if profile["balance"] < stake:
            await callback.answer("Недостаточно кредитов!", show_alert=True)
            return

        game = _games.get(key)
        if not game:
            await callback.answer("Игра не найдена, начни заново.", show_alert=True)
            return

        await _start_round(chat_id, user_id, bot, callback.message.message_id, stake)
    except Exception as e:
        logger.error("Error in bj:stake chat=%s user=%s: %s", chat_id, user_id, e)
        _games.pop(key, None)
    await callback.answer()


# ── Player actions ─────────────────────────────────────────────────────

@router.callback_query(F.data == "bj:hit")
async def cb_hit(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    key = (chat_id, user_id)

    game = _games.get(key)
    if not game or game.stake == 0:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    try:
        game.cancel_task()
        game.hit()
        pscore = _score(game.player_hand)

        if pscore > 21:
            await _finish(game, "loss", BJ_BUST)
        else:
            text = _game_text(game, dealer_hidden=True)
            try:
                await callback.message.edit_text(text, reply_markup=_action_kb(can_double=False), parse_mode="HTML")
            except Exception:
                pass
            game._task = asyncio.create_task(_timeout_game(key))
    except Exception as e:
        logger.error("Error in bj:hit chat=%s user=%s: %s", chat_id, user_id, e)
        _games.pop(key, None)

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

    try:
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
    except Exception as e:
        logger.error("Error in bj:stand chat=%s user=%s: %s", chat_id, user_id, e)
        _games.pop(key, None)

    await callback.answer()


@router.callback_query(F.data == "bj:double")
async def cb_double_down(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    key = (chat_id, user_id)

    game = _games.get(key)
    if not game or game.stake == 0:
        await callback.answer("Игра не найдена.", show_alert=True)
        return

    if len(game.player_hand) != 2:
        await callback.answer("Удвоить можно только на первых двух картах.", show_alert=True)
        return

    try:
        profile = await repo.get_blackjack_profile(chat_id, user_id)
        if profile["balance"] < game.stake * 2:
            await callback.answer("Недостаточно кредитов для удвоения.", show_alert=True)
            return

        game.cancel_task()
        game.doubled = True
        game.hit()  # exactly one card

        pscore = _score(game.player_hand)
        if pscore > 21:
            await _finish(game, "loss", BJ_DOUBLE_DOWN_BUST)
            await callback.answer()
            return

        game.dealer_play()
        dscore = _score(game.dealer_hand)

        if dscore > 21:
            outcome, line = "win", BJ_DOUBLE_DOWN_DEALER_BUST
        elif pscore > dscore:
            outcome, line = "win", BJ_DOUBLE_DOWN_WIN
        elif pscore < dscore:
            outcome, line = "loss", BJ_DOUBLE_DOWN_LOSS
        else:
            outcome, line = "draw", BJ_DRAW

        await _finish(game, outcome, line)
    except Exception as e:
        logger.error("Error in bj:double chat=%s user=%s: %s", chat_id, user_id, e)
        _games.pop(key, None)

    await callback.answer()


# ── Loan mechanic ──────────────────────────────────────────────────────

@router.callback_query(F.data == "bj:borrow")
async def cb_borrow(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    try:
        # Check if there's already a pending loan from this user
        pending_key = next(
            (k for k in _pending_loans if k.startswith(f"{chat_id}:{user_id}:")), None
        )
        if pending_key:
            await callback.answer(BJ_LOAN_ALREADY_PENDING, show_alert=True)
            return

        lenders = await repo.get_blackjack_lenders(chat_id, exclude_user_id=user_id, min_balance=LOAN_AMOUNT)
        if not lenders:
            await callback.answer(BJ_NO_LENDERS, show_alert=True)
            return

        buttons = []
        for l in lenders:
            name = l["first_name"] or l["username"] or "???"
            buttons.append([InlineKeyboardButton(
                text=f"{name} 💰{l['balance']}",
                callback_data=f"bj:borrow_from:{l['user_id']}",
            )])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="bj:borrow_cancel")])

        await safe_edit_text(
            callback.message,
            BJ_LOAN_CHOOSE,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Error in bj:borrow chat=%s user=%s: %s", chat_id, user_id, e)
    await callback.answer()


@router.callback_query(F.data.startswith("bj:borrow_from:"))
async def cb_borrow_from(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    requester_id = callback.from_user.id
    lender_id = int(callback.data.split(":")[2])

    loan_key = f"{chat_id}:{requester_id}:{lender_id}"

    if loan_key in _pending_loans:
        await callback.answer(BJ_LOAN_ALREADY_PENDING, show_alert=True)
        return

    try:
        requester_name = callback.from_user.first_name or callback.from_user.username or "Кто-то"

        # Edit borrower's message
        await safe_edit_text(
            callback.message,
            BJ_LOAN_REQUEST_SENT,
            reply_markup=None,
            parse_mode="HTML",
        )

        # Send notification to lender
        accept_cb = f"bj:la:{chat_id}:{requester_id}:{lender_id}"
        decline_cb = f"bj:ld:{chat_id}:{requester_id}:{lender_id}"
        loan_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💸 Швырнуть деньги на пол", callback_data=accept_cb),
            InlineKeyboardButton(text="🚪 Хлопнуть дверью", callback_data=decline_cb),
        ]])

        sent = await bot.send_message(
            chat_id,
            BJ_LOAN_INCOMING.format(requester=requester_name),
            reply_markup=loan_kb,
            parse_mode="HTML",
        )
        _pending_loans[loan_key] = {
            "requester_id": requester_id,
            "requester_name": requester_name,
            "lender_id": lender_id,
            "chat_id": chat_id,
            "loan_msg_id": sent.message_id,
        }
    except Exception as e:
        logger.error("Error in bj:borrow_from chat=%s: %s", chat_id, e)

    await callback.answer()


@router.callback_query(F.data == "bj:borrow_cancel")
async def cb_borrow_cancel(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        BJ_BALANCE_ZERO,
        reply_markup=_borrow_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bj:la:"))
async def cb_loan_accept(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    chat_id = int(parts[2])
    requester_id = int(parts[3])
    lender_id = int(parts[4])

    if callback.from_user.id != lender_id:
        await callback.answer("Это не твой запрос.", show_alert=True)
        return

    loan_key = f"{chat_id}:{requester_id}:{lender_id}"
    loan = _pending_loans.pop(loan_key, None)
    if not loan:
        await callback.answer("Запрос уже обработан.", show_alert=True)
        return

    try:
        lender_name = callback.from_user.first_name or callback.from_user.username or "Кто-то"
        ok = await repo.transfer_blackjack_credits(chat_id, lender_id, requester_id, LOAN_AMOUNT)
        if not ok:
            await callback.answer(BJ_LOAN_NO_FUNDS, show_alert=True)
            _pending_loans[loan_key] = loan  # put back
            return

        # Edit loan message
        try:
            await bot.edit_message_text(
                BJ_LOAN_ACCEPTED_LENDER,
                chat_id=chat_id,
                message_id=loan["loan_msg_id"],
                reply_markup=None,
            )
        except Exception:
            pass

        # Notify borrower
        try:
            await bot.send_message(
                chat_id,
                BJ_LOAN_ACCEPTED_BORROWER.format(lender=lender_name),
            )
        except Exception:
            pass
    except Exception as e:
        logger.error("Error in loan accept chat=%s: %s", chat_id, e)

    await callback.answer()


@router.callback_query(F.data.startswith("bj:ld:"))
async def cb_loan_decline(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    chat_id = int(parts[2])
    requester_id = int(parts[3])
    lender_id = int(parts[4])

    if callback.from_user.id != lender_id:
        await callback.answer("Это не твой запрос.", show_alert=True)
        return

    loan_key = f"{chat_id}:{requester_id}:{lender_id}"
    loan = _pending_loans.pop(loan_key, None)
    if not loan:
        await callback.answer("Запрос уже обработан.", show_alert=True)
        return

    try:
        lender_name = callback.from_user.first_name or callback.from_user.username or "Кто-то"

        try:
            await bot.edit_message_text(
                BJ_LOAN_DECLINED_LENDER,
                chat_id=chat_id,
                message_id=loan["loan_msg_id"],
                reply_markup=None,
            )
        except Exception:
            pass

        try:
            await bot.send_message(
                chat_id,
                BJ_LOAN_DECLINED_BORROWER.format(lender=lender_name),
            )
        except Exception:
            pass
    except Exception as e:
        logger.error("Error in loan decline chat=%s: %s", chat_id, e)

    await callback.answer()


# ── /weekly, /balance, /top_blackjack ────────────────────────────────

@router.message(Command("weekly"))
async def cmd_weekly(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    result = await repo.claim_weekly_credits(chat_id, user_id)
    if result is True:
        profile = await repo.get_blackjack_profile(chat_id, user_id)
        await message.answer(BJ_WEEKLY_CLAIMED.format(balance=profile["balance"]))
    else:
        next_time = result.strftime("%d.%m в %H:%M")
        await message.answer(BJ_WEEKLY_COOLDOWN.format(next_time=next_time))


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    profile = await repo.get_blackjack_profile(message.chat.id, message.from_user.id)
    wr = _win_rate(profile)
    await message.answer(
        f"💰 <b>Твой баланс</b>\n\n"
        f"Кредиты: <b>{profile['balance']}💰</b>\n"
        f"Макс. баланс: {profile['max_balance']}💰\n"
        f"Партий: {profile['total_games']} | {wr}",
        parse_mode="HTML",
    )


@router.message(Command("top_blackjack"))
async def cmd_top_blackjack(message: Message):
    chat_id = message.chat.id
    top = await repo.get_blackjack_top(chat_id, 10)
    if not top:
        await message.answer("💰 Никто ещё не играл в блэкджек.")
        return

    lines = ["💰 <b>Топ блэкджека</b>\n"]
    for i, row in enumerate(top, 1):
        name = row["first_name"] or row["username"] or "???"
        total = row["total_games"] or 0
        wins = row["wins"] or 0
        losses = row["losses"] or 0
        pct = round(wins / total * 100) if total else 0
        lines.append(
            f"{i}. {name} — {row['balance']}💰  "
            f"W:{wins}/L:{losses} ({pct}%)"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")
