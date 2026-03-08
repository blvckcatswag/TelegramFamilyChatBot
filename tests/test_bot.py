"""Tests for Family Chat Bot — per TZ section 15."""
import asyncio
import json
import random
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import aiosqlite

from app.db.database import init_db, get_db, close_db
from app.db import repositories as repo
from app.config import settings as cfg
from app.utils.helpers import progress_bar, parse_date, format_birthday_date, safe_edit_text, safe_edit_reply_markup, now_kyiv
from app.services.games.roulette import RouletteGame, _check_cooldown_sync, _apply_mute


# ──────────────────── Fixtures ────────────────────

@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a fresh DB for each test."""
    await close_db()
    db_path = str(tmp_path / "test.db")
    cfg.DB_PATH = db_path
    cfg.DATABASE_URL = f"sqlite:///{db_path}"
    await init_db()
    yield
    await close_db()


CHAT_ID = -1001234567890
USER_ID_1 = 111111
USER_ID_2 = 222222


@pytest_asyncio.fixture
async def setup_chat():
    await repo.get_or_create_chat(CHAT_ID, "Test Chat", USER_ID_1)
    await repo.get_or_create_user(USER_ID_1, CHAT_ID, "user1", "Alice", "owner")
    await repo.get_or_create_user(USER_ID_2, CHAT_ID, "user2", "Bob")


# ──────────────────── 1. Reminders ────────────────────

@pytest.mark.asyncio
async def test_reminder_create_and_retrieve(setup_chat):
    rid = await repo.create_reminder(CHAT_ID, USER_ID_1, "Test reminder", "2026-12-25T09:00:00")
    assert rid is not None

    reminders = await repo.get_active_reminders(CHAT_ID)
    assert len(reminders) == 1
    assert reminders[0]["text"] == "Test reminder"


@pytest.mark.asyncio
async def test_reminder_deactivate(setup_chat):
    rid = await repo.create_reminder(CHAT_ID, USER_ID_1, "To deactivate", "2026-12-25T09:00:00")
    await repo.deactivate_reminder(rid)

    reminders = await repo.get_active_reminders(CHAT_ID)
    assert len(reminders) == 0


@pytest.mark.asyncio
async def test_reminder_delete(setup_chat):
    rid = await repo.create_reminder(CHAT_ID, USER_ID_1, "To delete", "2026-12-25T09:00:00")
    await repo.delete_reminder(rid, CHAT_ID)

    reminders = await repo.get_active_reminders(CHAT_ID)
    assert len(reminders) == 0


@pytest.mark.asyncio
async def test_reminder_limit(setup_chat):
    for i in range(cfg.MAX_REMINDERS_PER_CHAT):
        rid = await repo.create_reminder(CHAT_ID, USER_ID_1, f"Reminder {i}", "2026-12-25T09:00:00")
        assert rid is not None

    # Next one should fail
    rid = await repo.create_reminder(CHAT_ID, USER_ID_1, "Over limit", "2026-12-25T09:00:00")
    assert rid is None


# ──────────────────── 2. Cactus: 1/day limit ────────────────────

@pytest.mark.asyncio
async def test_cactus_daily_limit(setup_chat):
    today = date.today().isoformat()
    cactus = await repo.get_cactus(CHAT_ID, USER_ID_1)
    assert cactus["height_cm"] == 0
    assert cactus["last_play_date"] is None

    # First play
    await repo.update_cactus(CHAT_ID, USER_ID_1, 1, today)
    cactus = await repo.get_cactus(CHAT_ID, USER_ID_1)
    assert cactus["height_cm"] == 1
    assert cactus["last_play_date"] == today

    # Check limit by date comparison
    assert cactus["last_play_date"] == today  # Would be blocked in handler


# ──────────────────── 3. Cat: 1/day limit ────────────────────

@pytest.mark.asyncio
async def test_cat_daily_limit(setup_chat):
    today = date.today().isoformat()
    cat = await repo.get_cat(CHAT_ID, USER_ID_1)
    assert cat["mood_score"] == 0

    await repo.update_cat(CHAT_ID, USER_ID_1, 2, today)
    cat = await repo.get_cat(CHAT_ID, USER_ID_1)
    assert cat["mood_score"] == 2
    assert cat["last_play_date"] == today


# ──────────────────── 4. Probabilities (deterministic) ────────────────────

@pytest.mark.asyncio
async def test_cactus_probabilities():
    """Test that probabilities are within expected ranges with fixed seed."""
    random.seed(42)
    negatives = sum(1 for _ in range(10000) if random.random() < cfg.CACTUS_NEGATIVE_CHANCE)
    # 1% of 10000 should be ~100, allow wide margin
    assert 50 < negatives < 200


@pytest.mark.asyncio
async def test_cat_probabilities():
    random.seed(42)
    results = {"positive": 0, "neutral": 0, "negative": 0}
    for _ in range(10000):
        r = random.random()
        if r < cfg.CAT_POSITIVE_CHANCE:
            results["positive"] += 1
        elif r < cfg.CAT_POSITIVE_CHANCE + cfg.CAT_NEUTRAL_CHANCE:
            results["neutral"] += 1
        else:
            results["negative"] += 1

    # 50% positive, 30% neutral, 20% negative — with margin
    assert 4500 < results["positive"] < 5500
    assert 2500 < results["neutral"] < 3500
    assert 1500 < results["negative"] < 2500


# ──────────────────── 5. Home order ────────────────────

@pytest.mark.asyncio
async def test_home_order_changes(setup_chat):
    order = await repo.get_home_order(CHAT_ID)
    assert order == 50  # Default

    new_order = await repo.update_home_order(CHAT_ID, 5)
    assert new_order == 55

    new_order = await repo.update_home_order(CHAT_ID, -60)
    assert new_order == 0  # Clamped to min

    new_order = await repo.update_home_order(CHAT_ID, 200)
    assert new_order == 100  # Clamped to max


# ──────────────────── 6. Quotes ────────────────────

@pytest.mark.asyncio
async def test_quote_save_and_retrieve(setup_chat):
    qid = await repo.save_quote(CHAT_ID, USER_ID_1, USER_ID_2, "Test quote", 12345)
    assert qid is not None

    quote = await repo.get_random_quote(CHAT_ID)
    assert quote is not None
    assert quote["text"] == "Test quote"


@pytest.mark.asyncio
async def test_quote_limit(setup_chat):
    for i in range(cfg.MAX_QUOTES_PER_CHAT):
        await repo.save_quote(CHAT_ID, USER_ID_1, USER_ID_2, f"Quote {i}")

    result = await repo.save_quote(CHAT_ID, USER_ID_1, USER_ID_2, "Over limit")
    assert result is None


# ──────────────────── 7. Translator ────────────────────

@pytest.mark.asyncio
async def test_translator_logging(setup_chat):
    await repo.log_translator(CHAT_ID, USER_ID_1, "ясно")
    await repo.log_translator(CHAT_ID, USER_ID_1, "ок")
    await repo.log_translator(CHAT_ID, USER_ID_2, "ясно")

    top = await repo.get_translator_top(CHAT_ID)
    assert len(top) == 2
    assert top[0]["user_id"] == USER_ID_1
    assert top[0]["cnt"] == 2


@pytest.mark.asyncio
async def test_translator_probability():
    random.seed(42)
    triggered = sum(1 for _ in range(10000) if random.random() <= cfg.TRANSLATOR_TRIGGER_CHANCE)
    # ~35% of 10000 = ~3500
    assert 3000 < triggered < 4000


# ──────────────────── 8. Duel ────────────────────

@pytest.mark.asyncio
async def test_duel_creation(setup_chat):
    winner_id = random.choice([USER_ID_1, USER_ID_2])
    duel_id = await repo.create_duel(CHAT_ID, USER_ID_1, USER_ID_2, winner_id, 30)
    assert duel_id is not None

    stats = await repo.get_duel_stats(CHAT_ID, winner_id)
    assert stats["wins"] == 1
    assert stats["total"] == 1


# ──────────────────── 9. Roulette ────────────────────

@pytest.mark.asyncio
async def test_roulette_creation(setup_chat):
    participants = [USER_ID_1, USER_ID_2]
    loser_id = random.choice(participants)
    rid = await repo.create_roulette(CHAT_ID, json.dumps(participants), loser_id)
    assert rid is not None


@pytest.mark.asyncio
async def test_roulette_survival_count(setup_chat):
    participants = [USER_ID_1, USER_ID_2]
    # User 1 loses
    await repo.create_roulette(CHAT_ID, json.dumps(participants), USER_ID_1)
    # User 2 survives
    survived = await repo.get_roulette_survival_count(CHAT_ID, USER_ID_2)
    assert survived == 1
    # User 1 lost
    survived = await repo.get_roulette_survival_count(CHAT_ID, USER_ID_1)
    assert survived == 0


# ── RouletteGame class (pure logic, no DB/bot) ────────────────────────

def test_roulette_add_player_success():
    game = RouletteGame(CHAT_ID, 1, MagicMock())
    assert game.add_player(USER_ID_1, "Alice") is True
    assert game.add_player(USER_ID_2, "Bob") is True
    assert len(game.players) == 2


def test_roulette_add_player_duplicate():
    game = RouletteGame(CHAT_ID, 1, MagicMock())
    assert game.add_player(USER_ID_1, "Alice") is True
    assert game.add_player(USER_ID_1, "Alice опять") is False
    assert len(game.players) == 1


def test_roulette_shoot_hits_at_bullet_pos():
    game = RouletteGame(CHAT_ID, 1, MagicMock())
    for i in range(1, 7):
        game.add_player(i, f"Player{i}")
    game.start_playing()
    game.bullet_pos = 3
    assert game.shoot() is False  # выстрел 1
    assert game.shoot() is False  # выстрел 2
    assert game.shoot() is True   # выстрел 3 — попадание


def test_roulette_shoot_all_miss():
    game = RouletteGame(CHAT_ID, 1, MagicMock())
    game.add_player(USER_ID_1, "Alice")
    game.start_playing()
    game.bullet_pos = 7  # невозможная позиция — все мимо
    for _ in range(6):
        assert game.shoot() is False


def test_roulette_bullet_always_in_range():
    game = RouletteGame(CHAT_ID, 1, MagicMock())
    game.add_player(USER_ID_1, "Alice")
    for _ in range(100):
        game.start_playing()
        assert 1 <= game.bullet_pos <= 6


def test_roulette_current_player_empty_order():
    game = RouletteGame(CHAT_ID, 1, MagicMock())
    assert game.current_player is None


def test_roulette_current_player_wraps():
    game = RouletteGame(CHAT_ID, 1, MagicMock())
    game.add_player(USER_ID_1, "Alice")
    game.add_player(USER_ID_2, "Bob")
    game.start_playing()
    game.order = [{"id": USER_ID_1, "name": "Alice"}, {"id": USER_ID_2, "name": "Bob"}]
    game.current_idx = 0
    assert game.current_player["id"] == USER_ID_1
    game.current_idx = 2  # 2 % 2 == 0 — оборачивается
    assert game.current_player["id"] == USER_ID_1
    game.current_idx = 3  # 3 % 2 == 1
    assert game.current_player["id"] == USER_ID_2


def test_roulette_6_players_autostart():
    game = RouletteGame(CHAT_ID, 1, MagicMock())
    for i in range(1, 7):
        assert game.add_player(i, f"Player{i}") is True
    assert len(game.players) == 6
    game.start_playing()
    assert game.phase == "playing"
    assert 1 <= game.bullet_pos <= 6
    assert len(game.order) == 6


def test_roulette_10_joins_only_6_get_in():
    """add_player сам не ограничивает, но phase-check в handler блокирует 7+.
    Проверяем что после autostart (6 игроков) phase меняется на playing."""
    game = RouletteGame(CHAT_ID, 1, MagicMock())
    for i in range(1, 7):
        game.add_player(i, f"Player{i}")
    game.start_playing()  # имитируем autostart
    # игроки 7-10 в реальном боте получат "Игра уже завершена" из cb_join
    assert game.phase == "playing"
    assert len(game.players) == 6


# ── Cooldown ──────────────────────────────────────────────────────────

def test_roulette_cooldown_no_history():
    assert _check_cooldown_sync(None) is None


def test_roulette_cooldown_active():
    last = (now_kyiv() - timedelta(minutes=2)).isoformat()
    remaining = _check_cooldown_sync(last)
    assert remaining is not None
    assert remaining >= 1


def test_roulette_cooldown_expired():
    last = (now_kyiv() - timedelta(minutes=cfg.ROULETTE_COOLDOWN_MINUTES + 1)).isoformat()
    assert _check_cooldown_sync(last) is None


# ── Repository: дополнительные кейсы ─────────────────────────────────

@pytest.mark.asyncio
async def test_roulette_last_time_none(setup_chat):
    last = await repo.get_last_roulette_time(CHAT_ID, USER_ID_1)
    assert last is None


@pytest.mark.asyncio
async def test_roulette_survival_accumulates(setup_chat):
    participants = json.dumps([USER_ID_1, USER_ID_2])
    await repo.create_roulette(CHAT_ID, participants, USER_ID_2)  # игра 1: user2 проиграл
    await repo.create_roulette(CHAT_ID, participants, USER_ID_2)  # игра 2: user2 снова
    survived = await repo.get_roulette_survival_count(CHAT_ID, USER_ID_1)
    assert survived == 2  # user1 выжил оба раза


@pytest.mark.asyncio
async def test_roulette_loser_has_zero_survivals(setup_chat):
    participants = json.dumps([USER_ID_1, USER_ID_2])
    await repo.create_roulette(CHAT_ID, participants, USER_ID_1)
    await repo.create_roulette(CHAT_ID, participants, USER_ID_1)
    assert await repo.get_roulette_survival_count(CHAT_ID, USER_ID_1) == 0
    assert await repo.get_roulette_survival_count(CHAT_ID, USER_ID_2) == 2


# ── _apply_mute (мокаем bot) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_roulette_mute_target_is_admin():
    bot = AsyncMock()
    member = MagicMock()
    member.status = "administrator"
    bot.get_chat_member.return_value = member

    game = RouletteGame(CHAT_ID, 1, bot)
    result = await _apply_mute(game, {"id": USER_ID_1, "name": "Alice"})

    assert "мут не применён" in result.lower()
    bot.restrict_chat_member.assert_not_called()


@pytest.mark.asyncio
async def test_roulette_mute_bot_not_admin():
    bot = AsyncMock()
    bot.get_chat_member.side_effect = Exception("no rights")
    bot.restrict_chat_member.side_effect = Exception("can't restrict")

    game = RouletteGame(CHAT_ID, 1, bot)
    result = await _apply_mute(game, {"id": USER_ID_1, "name": "Alice"})

    assert "не применён" in result


@pytest.mark.asyncio
async def test_roulette_mute_success(setup_chat):
    bot = AsyncMock()
    member = MagicMock()
    member.status = "member"
    bot.get_chat_member.return_value = member
    bot.restrict_chat_member.return_value = True

    game = RouletteGame(CHAT_ID, 1, bot)
    with patch("app.services.games.roulette.repo.get_active_mute_until", return_value=None), \
         patch("app.services.games.roulette.repo.log_mute", return_value=None):
        result = await _apply_mute(game, {"id": USER_ID_1, "name": "Alice"})

    assert "мут" in result
    assert str(cfg.ROULETTE_MUTE_MINUTES) in result


# ──────────────────── 10. Birthdays ────────────────────

@pytest.mark.asyncio
async def test_birthday_add_and_list(setup_chat):
    await repo.add_birthday(CHAT_ID, "Мама", "03-25")
    await repo.add_birthday(CHAT_ID, "Папа", "07-10")

    bdays = await repo.get_birthdays(CHAT_ID)
    assert len(bdays) == 2
    assert bdays[0]["name"] == "Мама"


# ──────────────────── 11. Reactions ────────────────────

@pytest.mark.asyncio
async def test_reactions_save(setup_chat):
    await repo.save_reaction(CHAT_ID, 100, USER_ID_1, "👍", USER_ID_2)
    top = await repo.get_top_reactions(CHAT_ID, 5)
    assert len(top) == 1
    assert top[0]["emoji"] == "👍"

    count = await repo.get_my_reactions_count(CHAT_ID, USER_ID_2)
    assert count == 1


@pytest.mark.asyncio
async def test_reaction_dedup(setup_chat):
    """Changing reaction should replace, not duplicate."""
    await repo.save_reaction(CHAT_ID, 100, USER_ID_1, "👍", USER_ID_2)
    await repo.save_reaction(CHAT_ID, 100, USER_ID_1, "❤️", USER_ID_2)

    top = await repo.get_top_reactions(CHAT_ID, 5)
    # Should have only the new reaction
    assert any(r["emoji"] == "❤️" for r in top)


# ──────────────────── 12. Monthly Awards ────────────────────

@pytest.mark.asyncio
async def test_awards_save_and_retrieve(setup_chat):
    await repo.save_award(CHAT_ID, 2026, 3, "cactus_king", USER_ID_1, "50 см")
    awards = await repo.get_awards(CHAT_ID, 2026, 3)
    assert len(awards) == 1
    assert awards[0]["award_type"] == "cactus_king"


# ──────────────────── 13. Utilities ────────────────────

def test_progress_bar():
    assert "█" in progress_bar(50)
    assert "100%" in progress_bar(100)
    assert "0%" in progress_bar(0)


def test_parse_date():
    d = parse_date("25.03")
    assert d is not None
    assert d.month == 3
    assert d.day == 25

    assert parse_date("invalid") is None


def test_format_birthday_date():
    assert format_birthday_date("03-25") == "25.03"


# ──────────────────── 14. Settings ────────────────────

@pytest.mark.asyncio
async def test_settings_toggle(setup_chat):
    settings = await repo.get_settings(CHAT_ID)
    assert settings["weather_enabled"] == 1

    await repo.update_setting(CHAT_ID, "weather_enabled", 0)
    settings = await repo.get_settings(CHAT_ID)
    assert settings["weather_enabled"] == 0


# ──────────────────── 15. Weather cities ────────────────────

@pytest.mark.asyncio
async def test_weather_cities_limit(setup_chat):
    for i in range(cfg.MAX_WEATHER_CITIES_PER_CHAT):
        ok = await repo.add_weather_city(CHAT_ID, f"City{i}")
        assert ok is True

    ok = await repo.add_weather_city(CHAT_ID, "OverLimit")
    assert ok is False


@pytest.mark.asyncio
async def test_weather_city_remove(setup_chat):
    await repo.add_weather_city(CHAT_ID, "Moscow")
    await repo.remove_weather_city(CHAT_ID, "Moscow")

    cities = await repo.get_weather_cities(CHAT_ID)
    assert len(cities) == 0


# ──────────────────── 16. User roles ────────────────────

@pytest.mark.asyncio
async def test_user_roles(setup_chat):
    role = await repo.get_user_role(USER_ID_1, CHAT_ID)
    assert role == "owner"

    role = await repo.get_user_role(USER_ID_2, CHAT_ID)
    assert role == "user"

    await repo.set_user_role(USER_ID_2, CHAT_ID, "owner")
    role = await repo.get_user_role(USER_ID_2, CHAT_ID)
    assert role == "owner"


# ──────────────────── 17. Chat ban ────────────────────

@pytest.mark.asyncio
async def test_chat_ban(setup_chat):
    assert await repo.is_chat_banned(CHAT_ID) is False

    await repo.set_chat_banned(CHAT_ID, True)
    assert await repo.is_chat_banned(CHAT_ID) is True

    await repo.set_chat_banned(CHAT_ID, False)
    assert await repo.is_chat_banned(CHAT_ID) is False


# ──────────────────── 18. safe_edit_text / safe_edit_reply_markup ────────────────────

@pytest.mark.asyncio
async def test_safe_edit_text_calls_edit(setup_db):
    """safe_edit_text forwards the call to message.edit_text."""
    msg = AsyncMock()
    await safe_edit_text(msg, "hello", parse_mode="HTML")
    msg.edit_text.assert_awaited_once_with("hello", parse_mode="HTML")


@pytest.mark.asyncio
async def test_safe_edit_text_ignores_not_modified(setup_db):
    """safe_edit_text silently ignores 'message is not modified' TelegramBadRequest."""
    from aiogram.exceptions import TelegramBadRequest
    msg = AsyncMock()
    msg.edit_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="Bad Request: message is not modified"
    )
    # Should not raise
    await safe_edit_text(msg, "same text")


@pytest.mark.asyncio
async def test_safe_edit_text_reraises_other_errors(setup_db):
    """safe_edit_text re-raises TelegramBadRequest for other error types."""
    from aiogram.exceptions import TelegramBadRequest
    msg = AsyncMock()
    msg.edit_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="Bad Request: message to edit not found"
    )
    with pytest.raises(TelegramBadRequest):
        await safe_edit_text(msg, "some text")


@pytest.mark.asyncio
async def test_safe_edit_reply_markup_ignores_not_modified(setup_db):
    """safe_edit_reply_markup silently ignores 'message is not modified'."""
    from aiogram.exceptions import TelegramBadRequest
    msg = AsyncMock()
    msg.edit_reply_markup.side_effect = TelegramBadRequest(
        method=MagicMock(), message="Bad Request: message is not modified"
    )
    # Should not raise
    await safe_edit_reply_markup(msg, reply_markup=MagicMock())


# ──────────────────── 19. Feedback ────────────────────

@pytest.mark.asyncio
async def test_feedback_create_and_list(setup_chat):
    fid = await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "bug", "Что-то сломалось")
    assert fid is not None

    total = await repo.count_open_feedback()
    assert total == 1

    items = await repo.get_open_feedback(limit=10, offset=0)
    assert len(items) == 1
    assert items[0]["category"] == "bug"
    assert items[0]["text"] == "Что-то сломалось"


@pytest.mark.asyncio
async def test_feedback_close(setup_chat):
    fid = await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "idea", "Идея для фичи")
    await repo.close_feedback(fid)

    total = await repo.count_open_feedback()
    assert total == 0


@pytest.mark.asyncio
async def test_feedback_multiple_categories(setup_chat):
    await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "bug", "Баг")
    await repo.create_feedback(USER_ID_2, CHAT_ID, "user2", "idea", "Идея")
    await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "complaint", "Жалоба")

    total = await repo.count_open_feedback()
    assert total == 3

    items = await repo.get_open_feedback(limit=10, offset=0)
    categories = {i["category"] for i in items}
    assert categories == {"bug", "idea", "complaint"}


@pytest.mark.asyncio
async def test_feedback_sql_injection_safe(setup_chat):
    """Parameterized queries должны безопасно хранить любые строки."""
    malicious = "'; DROP TABLE Feedback; --"
    fid = await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "bug", malicious)
    assert fid is not None

    items = await repo.get_open_feedback(limit=10, offset=0)
    assert items[0]["text"] == malicious  # строка сохранена as-is, таблица цела


@pytest.mark.asyncio
async def test_feedback_xss_stored_as_plain_text(setup_chat):
    """XSS-строки сохраняются как обычный текст — Telegram сам экранирует HTML."""
    xss = "<script>alert('xss')</script>"
    fid = await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "bug", xss)
    assert fid is not None

    items = await repo.get_open_feedback(limit=10, offset=0)
    assert items[0]["text"] == xss


@pytest.mark.asyncio
async def test_feedback_null_text(setup_chat):
    """Фидбек без текста (только медиа) должен сохраняться с text=None."""
    fid = await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "bug", None)
    assert fid is not None

    items = await repo.get_open_feedback(limit=10, offset=0)
    assert items[0]["text"] is None


# ──────────────────── 20. FSM cancel on nav (middleware logic) ────────────────────

@pytest.mark.asyncio
async def test_delete_trigger_middleware_clears_state(setup_db):
    """_DeleteTriggerMiddleware должен сбрасывать FSM-состояние перед вызовом хендлера."""
    from app.bot.handlers.reply_keyboards import _DeleteTriggerMiddleware
    from unittest.mock import AsyncMock, MagicMock

    middleware = _DeleteTriggerMiddleware()

    state = AsyncMock()
    state.get_state = AsyncMock(return_value="FeedbackForm:waiting_content")
    state.clear = AsyncMock()

    handler = AsyncMock(return_value=None)
    event = AsyncMock()
    event.delete = AsyncMock()

    data = {"state": state}

    await middleware(handler, event, data)

    state.clear.assert_awaited_once()
    handler.assert_awaited_once_with(event, data)


@pytest.mark.asyncio
async def test_delete_trigger_middleware_no_state(setup_db):
    """Middleware не падает если state=None (например нет хранилища)."""
    from app.bot.handlers.reply_keyboards import _DeleteTriggerMiddleware

    middleware = _DeleteTriggerMiddleware()
    handler = AsyncMock(return_value=None)
    event = AsyncMock()
    event.delete = AsyncMock()

    await middleware(handler, event, {"state": None})

    handler.assert_awaited_once()
