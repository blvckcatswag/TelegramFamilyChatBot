import asyncio
import json
import logging
import random
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery, ChatPermissions, InlineKeyboardButton,
    InlineKeyboardMarkup, Message,
)

from app.config import settings as cfg
from app.db import repositories as repo
from app.texts import ROULETTE_SURVIVE, ROULETTE_DEATH
from app.utils.helpers import now_kyiv, KYIV_TZ

router = Router()
logger = logging.getLogger(__name__)

COLLECT_TIMEOUT = 60    # 1 minute
TURN_TIMEOUT = 60       # 60 seconds
SHOOT_DELAY = 2.0       # dramatic pause (multi-player)
SOLO_SHOOT_DELAY = 7.0  # longer suspense for solo mode

# One active game per chat
_games: dict[int, "RouletteGame"] = {}


# ── Game state ────────────────────────────────────────────────────────

class RouletteGame:
    def __init__(self, chat_id: int, msg_id: int, bot: Bot):
        self.chat_id = chat_id
        self.msg_id = msg_id
        self.bot = bot
        self.players: list[dict] = []       # [{id, name}]
        self.phase = "collecting"           # collecting | playing | finished
        self.order: list[dict] = []
        self.bullet_pos = 0
        self.shot_count = 0
        self.current_idx = 0
        self.results: list[str] = []
        self.loser: dict | None = None
        self._task: asyncio.Task | None = None

    @property
    def current_player(self) -> dict | None:
        if not self.order:
            return None
        return self.order[self.current_idx % len(self.order)]

    def add_player(self, user_id: int, name: str) -> bool:
        if any(p["id"] == user_id for p in self.players):
            return False
        self.players.append({"id": user_id, "name": name})
        return True

    def start_playing(self):
        self.phase = "playing"
        self.bullet_pos = random.randint(1, 6)
        self.shot_count = 0
        self.order = self.players.copy()
        random.shuffle(self.order)
        self.current_idx = 0
        self.results = []
        logger.info(
            "Roulette started: chat=%s, bullet=%s, players=%s",
            self.chat_id, self.bullet_pos, [p["id"] for p in self.order],
        )

    def shoot(self) -> bool:
        """Returns True if bullet fires."""
        self.shot_count += 1
        return self.shot_count == self.bullet_pos

    def cancel_task(self):
        if self._task and not self._task.done():
            try:
                current = asyncio.current_task()
            except RuntimeError:
                current = None
            if self._task is not current:
                self._task.cancel()
        self._task = None


# ── Keyboards ─────────────────────────────────────────────────────────

def _join_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔫 Я участвую", callback_data="roulette:join"),
    ]])


def _shoot_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔫 Нажать курок", callback_data="roulette:shoot"),
    ]])


# ── Message builders ──────────────────────────────────────────────────

def _collecting_text(game: RouletteGame) -> str:
    plist = "\n".join(
        f"  {i + 1}. {p['name']}" for i, p in enumerate(game.players)
    )
    return (
        f"🔫 <b>Русская рулетка!</b>\n\n"
        f"Барабан на 6 позиций, 1 патрон.\n"
        f"⏳ 1 минута на сбор!\n\n"
        f"<b>Участники ({len(game.players)}):</b>\n{plist}"
    )


def _playing_text(game: RouletteGame) -> str:
    lines = [f"🎰 <b>Русская рулетка</b> | Выстрел {game.shot_count + 1} из 6\n"]
    for r in game.results:
        lines.append(r)
    cp = game.current_player
    if cp and game.phase == "playing":
        lines.append(f"\n🔫 <b>{cp['name']}</b> — ТВОЙ ХОД")
    return "\n".join(lines)


def _final_text(game: RouletteGame) -> str:
    lines = ["🎰 <b>Русская рулетка — ФИНАЛ</b>\n"]
    for r in game.results:
        lines.append(r)
    return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────

async def _edit_msg(game: RouletteGame, text: str, kb=None) -> bool:
    """Edit game message. Returns True on success, False on failure."""
    try:
        await game.bot.edit_message_text(
            text, chat_id=game.chat_id, message_id=game.msg_id,
            reply_markup=kb, parse_mode="HTML",
        )
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return True
        logger.warning(
            "Failed to edit roulette msg chat=%s msg=%s: %s",
            game.chat_id, game.msg_id, e,
        )
        return False
    except Exception as e:
        logger.warning(
            "Failed to edit roulette msg chat=%s msg=%s: %s",
            game.chat_id, game.msg_id, e,
        )
        return False


async def _send_fallback(game: RouletteGame, text: str, kb=None) -> bool:
    """Send a new message if edit fails, updating game.msg_id."""
    try:
        sent = await game.bot.send_message(
            game.chat_id, text, reply_markup=kb, parse_mode="HTML",
        )
        game.msg_id = sent.message_id
        return True
    except Exception as e:
        logger.warning("Failed to send fallback msg chat=%s: %s", game.chat_id, e)
        return False


async def _edit_or_send(game: RouletteGame, text: str, kb=None):
    """Try to edit the game message; if that fails, send a new one."""
    ok = await _edit_msg(game, text, kb)
    if not ok:
        await _send_fallback(game, text, kb)


async def _cleanup(chat_id: int):
    game = _games.pop(chat_id, None)
    if game:
        game.cancel_task()


async def _apply_mute(game: RouletteGame, loser: dict) -> str:
    try:
        member = await game.bot.get_chat_member(game.chat_id, loser["id"])
        if member.status in ("creator", "administrator"):
            return f"\nℹ️ Мут не применён (проигравший — админ/владелец чата)."
    except Exception:
        pass

    try:
        mute_until = now_kyiv() + timedelta(minutes=cfg.ROULETTE_MUTE_MINUTES)
        existing = await repo.get_active_mute_until(game.chat_id, loser["id"])
        if existing and existing >= mute_until:
            return "\nℹ️ Мут не изменён — уже действует более длинный."

        await game.bot.restrict_chat_member(
            game.chat_id, loser["id"],
            permissions=ChatPermissions(can_send_messages=False),
            until_date=mute_until,
        )
        await repo.log_mute(game.chat_id, loser["id"], "roulette", mute_until.isoformat())
        return f"\n🔇 {loser['name']} в муте на {cfg.ROULETTE_MUTE_MINUTES} мин."
    except Exception:
        return "\nℹ️ Мут не применён (бот не админ?)."


async def _finish_game(game: RouletteGame):
    game.phase = "finished"
    game.cancel_task()

    mute_text = ""
    if game.loser:
        mute_text = await _apply_mute(game, game.loser)
        await repo.create_roulette(
            game.chat_id,
            json.dumps([p["id"] for p in game.players]),
            game.loser["id"],
        )
    else:
        await repo.create_roulette(
            game.chat_id,
            json.dumps([p["id"] for p in game.players]),
            0,
        )

    final = _final_text(game) + mute_text
    await _edit_or_send(game, final)
    _games.pop(game.chat_id, None)


async def _next_turn(game: RouletteGame):
    if game.phase != "playing":
        return

    if not game.order:
        game.phase = "finished"
        await _edit_or_send(game, _final_text(game))
        _games.pop(game.chat_id, None)
        return

    if game.current_idx >= len(game.order):
        game.current_idx = 0

    await _edit_or_send(game, _playing_text(game), _shoot_kb())

    game.cancel_task()
    game._task = asyncio.create_task(_turn_timeout(game))


async def _turn_timeout(game: RouletteGame):
    await asyncio.sleep(TURN_TIMEOUT)
    if game.phase != "playing":
        return

    current = game.current_player
    if not current:
        return

    game.results.append(f"🐔 {current['name']} — струсил! Выбывает")
    game.order.remove(current)

    if not game.order:
        game.phase = "finished"
        await _edit_or_send(game, _final_text(game))
        _games.pop(game.chat_id, None)
        return

    if game.current_idx >= len(game.order):
        game.current_idx = 0

    await _next_turn(game)


async def _collection_timeout(game: RouletteGame):
    await asyncio.sleep(COLLECT_TIMEOUT)
    if game.phase != "collecting":
        return

    if not game.players:
        await _edit_or_send(game, "🔫 Никто не присоединился. Игра отменена.")
        _games.pop(game.chat_id, None)
        return

    if len(game.players) == 1:
        await _solo_mode(game)
        return

    game.start_playing()
    await _next_turn(game)


async def _solo_mode(game: RouletteGame):
    game.phase = "playing"
    player = game.players[0]

    await _edit_or_send(game,
        f"🎰 <b>Соло-рулетка!</b>\n\n"
        f"🔫 {player['name']} приставляет револьвер к виску...\n\n"
        f"🫣 Барабан крутится...",
    )

    await asyncio.sleep(SOLO_SHOOT_DELAY)

    hit = random.randint(1, 6) == 1
    if hit:
        game.loser = player
        game.results = [ROULETTE_DEATH.format(name=player["name"])]
    else:
        game.results = [random.choice(ROULETTE_SURVIVE).format(name=player["name"])]

    await _finish_game(game)


def _check_cooldown_sync(last: str | None) -> int | None:
    """Returns remaining minutes if on cooldown, else None."""
    if not last:
        return None
    last_dt = datetime.fromisoformat(last)
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=KYIV_TZ)
    diff = now_kyiv() - last_dt
    if diff < timedelta(minutes=cfg.ROULETTE_COOLDOWN_MINUTES):
        return max(1, cfg.ROULETTE_COOLDOWN_MINUTES - int(diff.total_seconds() / 60))
    return None


# ── Handlers ──────────────────────────────────────────────────────────

@router.message(Command("roulette"))
async def cmd_roulette(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer("🎮 Игры отключены.")
        return

    if chat_id in _games:
        game = _games[chat_id]
        if game.phase == "collecting":
            already_in = any(p["id"] == user_id for p in game.players)
            if already_in:
                await message.answer("🔫 Ты уже в игре, жди остальных!")
            else:
                # Add directly instead of creating a second message with button
                await repo.get_or_create_user(
                    user_id, chat_id, message.from_user.username,
                    message.from_user.first_name,
                )
                game.add_player(user_id, message.from_user.first_name)
                await _edit_or_send(game, _collecting_text(game), _join_kb())
                await message.answer("✅ Ты в игре!")

                if len(game.players) >= 6:
                    game.cancel_task()
                    game.start_playing()
                    await _next_turn(game)
        else:
            await message.answer("🔫 Рулетка уже в процессе, подожди следующего раунда.")
        return

    last = await repo.get_last_roulette_time(chat_id, user_id)
    remaining = _check_cooldown_sync(last)
    if remaining:
        await message.answer(f"🔫 Кулдаун! Подожди {remaining} мин.")
        return

    sent = await message.answer("🔫 Запускаю...", parse_mode="HTML")

    game = RouletteGame(chat_id, sent.message_id, bot)
    game.add_player(user_id, message.from_user.first_name)
    _games[chat_id] = game

    await _edit_or_send(game, _collecting_text(game), _join_kb())
    game._task = asyncio.create_task(_collection_timeout(game))


@router.callback_query(F.data == "roulette:join")
async def cb_join(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    game = _games.get(chat_id)

    if not game or game.phase != "collecting":
        await callback.answer("🔫 Игра уже завершена.", show_alert=True)
        return

    user_id = callback.from_user.id

    if any(p["id"] == user_id for p in game.players):
        await callback.answer("Ты уже в игре!", show_alert=True)
        return

    try:
        await repo.get_or_create_user(
            user_id, chat_id, callback.from_user.username,
            callback.from_user.first_name,
        )
        game.add_player(user_id, callback.from_user.first_name)
        await _edit_or_send(game, _collecting_text(game), _join_kb())
        await callback.answer("✅ Ты в игре!")
    except Exception as e:
        logger.error("Error joining roulette chat=%s user=%s: %s", chat_id, user_id, e)
        await callback.answer("Ошибка, попробуй ещё раз.", show_alert=True)
        return

    # 6 players — auto-start
    if len(game.players) >= 6:
        game.cancel_task()
        game.start_playing()
        await _next_turn(game)


@router.callback_query(F.data == "roulette:shoot")
async def cb_shoot(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    game = _games.get(chat_id)

    if not game or game.phase != "playing":
        await callback.answer("🔫 Игра не найдена.", show_alert=True)
        return

    current = game.current_player
    if not current or callback.from_user.id != current["id"]:
        await callback.answer("Не твоя очередь, подожди 😏")
        return

    game.cancel_task()
    await callback.answer()

    try:
        # Dramatic pause — remove button, show suspense
        suspense_text = _playing_text(game).replace("ТВОЙ ХОД", "тянет курок... 🥶")
        await _edit_or_send(game, suspense_text)

        await asyncio.sleep(SHOOT_DELAY)

        hit = game.shoot()
        if hit:
            game.loser = current
            game.results.append(ROULETTE_DEATH.format(name=current["name"]))
            await _finish_game(game)
        else:
            survive_text = random.choice(ROULETTE_SURVIVE).format(name=current["name"])
            game.results.append(f"✅ {survive_text}")
            game.current_idx += 1
            if game.current_idx >= len(game.order):
                game.current_idx = 0
            await _next_turn(game)
    except Exception as e:
        logger.error("Error in roulette shoot chat=%s: %s", chat_id, e)
        # Force cleanup on critical error
        await _cleanup(chat_id)


@router.callback_query(F.data == "game:roulette")
async def cb_roulette_info(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    game = _games.get(chat_id)

    # If a game is collecting — auto-join via menu click
    if game and game.phase == "collecting":
        if any(p["id"] == user_id for p in game.players):
            await callback.answer("🔫 Ты уже в игре, жди остальных!", show_alert=True)
            return
        try:
            await repo.get_or_create_user(
                user_id, chat_id, callback.from_user.username,
                callback.from_user.first_name,
            )
            game.add_player(user_id, callback.from_user.first_name)
            await _edit_or_send(game, _collecting_text(game), _join_kb())
            await callback.answer("✅ Ты в игре!")
        except Exception as e:
            logger.error("Error joining roulette via menu chat=%s user=%s: %s", chat_id, user_id, e)
            await callback.answer("Ошибка, попробуй ещё раз.", show_alert=True)
            return

        if len(game.players) >= 6:
            game.cancel_task()
            game.start_playing()
            await _next_turn(game)
        return

    if game and game.phase == "playing":
        await callback.answer("🔫 Рулетка уже в процессе, жди следующего раунда.", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            "🔫 <b>Русская рулетка</b>\n\n"
            "Используй /roulette для запуска.\n"
            f"2–6 игроков, 1 минута на сбор.\n"
            f"Проигравший получает мут на {cfg.ROULETTE_MUTE_MINUTES} мин.\n"
            "Соло: 1/6 шанс мута.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer()
