"""
Russian roulette — DB-backed state, APScheduler timeouts.

All game state lives in the RouletteActiveGame table (one row per chat).
Each handler: load from DB → validate → mutate → save → respond.
Timeouts are scheduled via APScheduler (survive redeploys).
"""
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


# ── Parse DB row ─────────────────────────────────────────────────────

def _parse_game(row: dict) -> dict:
    """Parse JSON fields from DB row into Python objects."""
    g = dict(row)
    g["players"] = json.loads(g["players"]) if isinstance(g["players"], str) else g["players"]
    g["play_order"] = json.loads(g["play_order"]) if isinstance(g["play_order"], str) else g["play_order"]
    g["results"] = json.loads(g["results"]) if isinstance(g["results"], str) else g["results"]
    return g


def _current_player(game: dict) -> dict | None:
    order = game["play_order"]
    if not order:
        return None
    return order[game["current_idx"] % len(order)]


# ── Keyboards ────────────────────────────────────────────────────────

def _join_kb(msg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔫 Я участвую", callback_data=f"roulette:join:{msg_id}"),
    ]])


def _shoot_kb(msg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔫 Нажать курок", callback_data=f"roulette:shoot:{msg_id}"),
    ]])


# ── Message builders ─────────────────────────────────────────────────

def _collecting_text(game: dict) -> str:
    players = game["players"]
    plist = "\n".join(
        f"  {i + 1}. {p['name']}" for i, p in enumerate(players)
    )
    return (
        f"🔫 <b>Русская рулетка!</b>\n\n"
        f"Барабан на 6 позиций, 1 патрон.\n"
        f"⏳ 1 минута на сбор!\n\n"
        f"<b>Участники ({len(players)}):</b>\n{plist}"
    )


def _playing_text(game: dict) -> str:
    lines = [f"🎰 <b>Русская рулетка</b> | Выстрел {game['shot_count'] + 1} из 6\n"]
    for r in game["results"]:
        lines.append(r)
    cp = _current_player(game)
    if cp and game["phase"] == "playing":
        lines.append(f"\n🔫 <b>{cp['name']}</b> — ТВОЙ ХОД")
    return "\n".join(lines)


def _final_text(game: dict) -> str:
    lines = ["🎰 <b>Русская рулетка — ФИНАЛ</b>\n"]
    for r in game["results"]:
        lines.append(r)
    return "\n".join(lines)


# ── Telegram message helpers ─────────────────────────────────────────

async def _edit_msg(bot: Bot, chat_id: int, msg_id: int, text: str, kb=None) -> bool:
    try:
        await bot.edit_message_text(
            text, chat_id=chat_id, message_id=msg_id,
            reply_markup=kb, parse_mode="HTML",
        )
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return True
        logger.warning("Failed to edit roulette msg chat=%s msg=%s: %s", chat_id, msg_id, e)
        return False
    except Exception as e:
        logger.warning("Failed to edit roulette msg chat=%s msg=%s: %s", chat_id, msg_id, e)
        return False


async def _send_fallback(bot: Bot, chat_id: int, text: str, kb=None) -> int | None:
    """Send a new message, return new msg_id or None."""
    try:
        sent = await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
        return sent.message_id
    except Exception as e:
        logger.warning("Failed to send fallback msg chat=%s: %s", chat_id, e)
        return None


async def _edit_or_send(bot: Bot, chat_id: int, msg_id: int, text: str, kb=None) -> int:
    """Try to edit; if that fails, send new message. Returns the actual msg_id."""
    ok = await _edit_msg(bot, chat_id, msg_id, text, kb)
    if ok:
        return msg_id
    new_id = await _send_fallback(bot, chat_id, text, kb)
    if new_id:
        await repo.update_active_roulette(chat_id, msg_id=new_id)
        return new_id
    return msg_id


# ── Game logic helpers ───────────────────────────────────────────────

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


async def _apply_mute(bot: Bot, chat_id: int, loser: dict) -> str:
    try:
        member = await bot.get_chat_member(chat_id, loser["id"])
        if member.status in ("creator", "administrator"):
            return "\nℹ️ Мут не применён (проигравший — админ/владелец чата)."
    except Exception:
        pass

    try:
        mute_until = now_kyiv() + timedelta(minutes=cfg.ROULETTE_MUTE_MINUTES)
        existing = await repo.get_active_mute_until(chat_id, loser["id"])
        if existing and existing >= mute_until:
            return "\nℹ️ Мут не изменён — уже действует более длинный."

        await bot.restrict_chat_member(
            chat_id, loser["id"],
            permissions=ChatPermissions(can_send_messages=False),
            until_date=mute_until,
        )
        await repo.log_mute(chat_id, loser["id"], "roulette", mute_until.isoformat())
        return f"\n🔇 {loser['name']} в муте на {cfg.ROULETTE_MUTE_MINUTES} мин."
    except Exception:
        return "\nℹ️ Мут не применён (бот не админ?)."


async def _finish_game(bot: Bot, game: dict):
    """Write result to history, apply mute, delete active game, edit message."""
    chat_id = game["chat_id"]
    players = game["players"]

    mute_text = ""
    loser_id = 0
    if game.get("loser_id") and game["loser_id"] != 0:
        loser_id = game["loser_id"]
        loser_name = None
        for p in players:
            if p["id"] == loser_id:
                loser_name = p["name"]
                break
        if loser_name:
            mute_text = await _apply_mute(bot, chat_id, {"id": loser_id, "name": loser_name})

    await repo.create_roulette(
        chat_id,
        json.dumps([p["id"] for p in players]),
        loser_id,
    )

    final = _final_text(game) + mute_text
    await _edit_or_send(bot, chat_id, game["msg_id"], final)
    await repo.delete_active_roulette(chat_id)


async def _start_playing(bot: Bot, game: dict):
    """Transition from collecting to playing phase."""
    from app.scheduler.jobs import cancel_roulette_job, schedule_roulette_turn

    chat_id = game["chat_id"]
    players = game["players"]
    order = players.copy()
    random.shuffle(order)
    bullet_pos = random.randint(1, 6)

    game["phase"] = "playing"
    game["play_order"] = order
    game["bullet_pos"] = bullet_pos
    game["shot_count"] = 0
    game["current_idx"] = 0
    game["results"] = []

    await repo.update_active_roulette(
        chat_id,
        phase="playing",
        play_order=json.dumps(order),
        bullet_pos=bullet_pos,
        shot_count=0,
        current_idx=0,
        results="[]",
    )

    logger.info(
        "Roulette started: chat=%s, bullet=%s, players=%s",
        chat_id, bullet_pos, [p["id"] for p in order],
    )

    cancel_roulette_job(chat_id, "collect")
    await _show_turn(bot, game)


async def _show_turn(bot: Bot, game: dict):
    """Show current turn and schedule turn timeout."""
    from app.scheduler.jobs import schedule_roulette_turn

    chat_id = game["chat_id"]
    order = game["play_order"]

    if not order:
        game["results"].append("🏁 Все выбыли!")
        await repo.update_active_roulette(chat_id, results=json.dumps(game["results"]))
        await _finish_game(bot, game)
        return

    idx = game["current_idx"]
    if idx >= len(order):
        idx = 0
        game["current_idx"] = 0
        await repo.update_active_roulette(chat_id, current_idx=0)

    msg_id = await _edit_or_send(bot, chat_id, game["msg_id"], _playing_text(game), _shoot_kb(game["msg_id"]))
    if msg_id != game["msg_id"]:
        game["msg_id"] = msg_id

    schedule_roulette_turn(chat_id, TURN_TIMEOUT)


async def _solo_mode(bot: Bot, game: dict):
    """Handle solo roulette (1 player)."""
    chat_id = game["chat_id"]
    player = game["players"][0]

    await _edit_or_send(bot, chat_id, game["msg_id"],
        f"🎰 <b>Соло-рулетка!</b>\n\n"
        f"🔫 {player['name']} приставляет револьвер к виску...\n\n"
        f"🫣 Барабан крутится...",
    )

    await asyncio.sleep(SOLO_SHOOT_DELAY)

    hit = random.randint(1, 6) == 1
    if hit:
        game["loser_id"] = player["id"]
        game["results"] = [ROULETTE_DEATH.format(name=player["name"])]
    else:
        game["results"] = [random.choice(ROULETTE_SURVIVE).format(name=player["name"])]

    await repo.update_active_roulette(
        chat_id,
        loser_id=player["id"] if hit else 0,
        results=json.dumps(game["results"]),
        phase="finished",
    )
    await _finish_game(bot, game)


# ── Scheduler-called functions ───────────────────────────────────────

async def handle_collect_timeout(chat_id: int, bot: Bot):
    """Called by scheduler when collection phase expires."""
    row = await repo.get_active_roulette(chat_id)
    if not row or row["phase"] != "collecting":
        return

    game = _parse_game(row)
    players = game["players"]

    if not players:
        await _edit_or_send(bot, chat_id, game["msg_id"],
                            "🔫 Никто не присоединился. Игра отменена.")
        await repo.delete_active_roulette(chat_id)
        return

    if len(players) == 1:
        await _solo_mode(bot, game)
        return

    await _start_playing(bot, game)


async def handle_turn_timeout(chat_id: int, bot: Bot):
    """Called by scheduler when current player's turn expires."""
    row = await repo.get_active_roulette(chat_id)
    if not row or row["phase"] != "playing":
        return

    game = _parse_game(row)
    order = game["play_order"]
    if not order:
        await _finish_game(bot, game)
        return

    current = _current_player(game)
    if not current:
        await _finish_game(bot, game)
        return

    game["results"].append(f"🐔 {current['name']} — струсил! Выбывает")
    order.remove(current)

    if not order:
        await repo.update_active_roulette(
            chat_id,
            play_order=json.dumps(order),
            results=json.dumps(game["results"]),
            phase="finished",
        )
        await _finish_game(bot, game)
        return

    idx = game["current_idx"]
    if idx >= len(order):
        idx = 0
    game["current_idx"] = idx

    await repo.update_active_roulette(
        chat_id,
        play_order=json.dumps(order),
        results=json.dumps(game["results"]),
        current_idx=idx,
    )
    await _show_turn(bot, game)


# ── Handlers ─────────────────────────────────────────────────────────

async def _try_join(bot: Bot, chat_id: int, user_id: int, first_name: str,
                    username: str | None, game: dict,
                    last_name: str | None = None, language_code: str | None = None,
                    is_premium: bool = False) -> str:
    """Add user to an active collecting game. Returns status message."""
    players = game["players"]
    if any(p["id"] == user_id for p in players):
        return "already_in"

    await repo.get_or_create_user(
        user_id, chat_id, username, first_name,
        last_name=last_name, language_code=language_code,
        is_premium=is_premium,
    )
    players.append({"id": user_id, "name": first_name})
    await repo.update_active_roulette(chat_id, players=json.dumps(players))

    msg_id = await _edit_or_send(bot, chat_id, game["msg_id"],
                                 _collecting_text(game), _join_kb(game["msg_id"]))
    if msg_id != game["msg_id"]:
        game["msg_id"] = msg_id

    if len(players) >= 6:
        await _start_playing(bot, game)

    return "joined"


@router.message(Command("roulette"))
async def cmd_roulette(message: Message, bot: Bot):
    chat_id = message.chat.id
    user_id = message.from_user.id

    s = await repo.get_settings(chat_id)
    if not s.get("games_enabled"):
        await message.answer("🎮 Игры отключены.")
        return

    row = await repo.get_active_roulette(chat_id)
    if row:
        game = _parse_game(row)
        if game["phase"] == "collecting":
            status = await _try_join(bot, chat_id, user_id,
                                     message.from_user.first_name,
                                     message.from_user.username, game,
                                     last_name=message.from_user.last_name,
                                     language_code=message.from_user.language_code,
                                     is_premium=bool(message.from_user.is_premium))
            if status == "already_in":
                await message.answer("🔫 Ты уже в игре, жди остальных!")
            else:
                await message.answer("✅ Ты в игре!")
        else:
            await message.answer("🔫 Рулетка уже в процессе, подожди следующего раунда.")
        return

    last = await repo.get_last_roulette_time(chat_id, user_id)
    remaining = _check_cooldown_sync(last)
    if remaining:
        await message.answer(f"🔫 Кулдаун! Подожди {remaining} мин.")
        return

    # Create new game
    from app.scheduler.jobs import schedule_roulette_collect

    sent = await message.answer("🔫 Запускаю...", parse_mode="HTML")
    players = [{"id": user_id, "name": message.from_user.first_name}]

    await repo.create_active_roulette(chat_id, sent.message_id, json.dumps(players))

    game = {
        "chat_id": chat_id, "msg_id": sent.message_id,
        "players": players, "phase": "collecting",
        "play_order": [], "results": [],
    }
    await _edit_or_send(bot, chat_id, sent.message_id,
                        _collecting_text(game), _join_kb(sent.message_id))
    schedule_roulette_collect(chat_id, COLLECT_TIMEOUT)


@router.callback_query(F.data.startswith("roulette:join:"))
async def cb_join(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    cb_msg_id = int(callback.data.split(":")[2])

    row = await repo.get_active_roulette(chat_id)
    if not row or row["phase"] != "collecting":
        await callback.answer("🔫 Игра уже завершена.", show_alert=True)
        return

    if row["msg_id"] != cb_msg_id:
        await callback.answer("🔫 Эта игра уже закончилась.", show_alert=True)
        return

    game = _parse_game(row)
    user_id = callback.from_user.id

    try:
        status = await _try_join(bot, chat_id, user_id,
                                 callback.from_user.first_name,
                                 callback.from_user.username, game,
                                 last_name=callback.from_user.last_name,
                                 language_code=callback.from_user.language_code,
                                 is_premium=bool(callback.from_user.is_premium))
        if status == "already_in":
            await callback.answer("Ты уже в игре!", show_alert=True)
        else:
            await callback.answer("✅ Ты в игре!")
    except Exception as e:
        logger.error("Error joining roulette chat=%s user=%s: %s", chat_id, user_id, e)
        await callback.answer("Ошибка, попробуй ещё раз.", show_alert=True)


@router.callback_query(F.data.startswith("roulette:shoot:"))
async def cb_shoot(callback: CallbackQuery, bot: Bot):
    from app.scheduler.jobs import cancel_roulette_job

    chat_id = callback.message.chat.id
    cb_msg_id = int(callback.data.split(":")[2])

    row = await repo.get_active_roulette(chat_id)
    if not row or row["phase"] != "playing":
        await callback.answer("🔫 Игра не найдена.", show_alert=True)
        return

    if row["msg_id"] != cb_msg_id:
        await callback.answer("🔫 Эта игра уже закончилась.", show_alert=True)
        return

    game = _parse_game(row)
    current = _current_player(game)
    if not current or callback.from_user.id != current["id"]:
        await callback.answer("Не твоя очередь, подожди 😏")
        return

    cancel_roulette_job(chat_id, "turn")
    await callback.answer()

    try:
        # Dramatic pause
        suspense_text = _playing_text(game).replace("ТВОЙ ХОД", "тянет курок... 🥶")
        await _edit_or_send(bot, chat_id, game["msg_id"], suspense_text)

        await asyncio.sleep(SHOOT_DELAY)

        game["shot_count"] += 1
        hit = game["shot_count"] == game["bullet_pos"]

        if hit:
            game["loser_id"] = current["id"]
            game["results"].append(ROULETTE_DEATH.format(name=current["name"]))
            await repo.update_active_roulette(
                chat_id,
                shot_count=game["shot_count"],
                loser_id=current["id"],
                results=json.dumps(game["results"]),
                phase="finished",
            )
            await _finish_game(bot, game)
        else:
            survive_text = random.choice(ROULETTE_SURVIVE).format(name=current["name"])
            game["results"].append(f"✅ {survive_text}")
            game["current_idx"] += 1
            if game["current_idx"] >= len(game["play_order"]):
                game["current_idx"] = 0
            await repo.update_active_roulette(
                chat_id,
                shot_count=game["shot_count"],
                current_idx=game["current_idx"],
                results=json.dumps(game["results"]),
            )
            await _show_turn(bot, game)
    except Exception as e:
        logger.error("Error in roulette shoot chat=%s: %s", chat_id, e)
        await repo.delete_active_roulette(chat_id)


@router.callback_query(F.data == "game:roulette")
async def cb_roulette_info(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    row = await repo.get_active_roulette(chat_id)

    if row:
        game = _parse_game(row)
        if game["phase"] == "collecting":
            try:
                status = await _try_join(bot, chat_id, user_id,
                                         callback.from_user.first_name,
                                         callback.from_user.username, game,
                                         last_name=callback.from_user.last_name,
                                         language_code=callback.from_user.language_code,
                                         is_premium=bool(callback.from_user.is_premium))
                if status == "already_in":
                    await callback.answer("🔫 Ты уже в игре, жди остальных!", show_alert=True)
                else:
                    await callback.answer("✅ Ты в игре!")
            except Exception as e:
                logger.error("Error joining roulette via menu chat=%s user=%s: %s", chat_id, user_id, e)
                await callback.answer("Ошибка, попробуй ещё раз.", show_alert=True)
            return

        if game["phase"] == "playing":
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
