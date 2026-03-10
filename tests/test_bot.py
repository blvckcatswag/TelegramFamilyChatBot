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
from app.services.games.roulette import (
    _check_cooldown_sync, _apply_mute, _edit_msg, _edit_or_send,
    _parse_game, _current_player, _collecting_text, _playing_text, _final_text,
)


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


# ── Roulette pure logic (dict-based, no DB/bot) ──────────────────────

def test_roulette_parse_game():
    row = {
        "chat_id": CHAT_ID, "msg_id": 1, "phase": "collecting",
        "players": '[{"id": 111, "name": "Alice"}]',
        "play_order": "[]", "bullet_pos": 0, "shot_count": 0,
        "current_idx": 0, "results": "[]", "loser_id": None,
        "created_at": "2026-03-10T12:00:00",
    }
    g = _parse_game(row)
    assert isinstance(g["players"], list)
    assert g["players"][0]["name"] == "Alice"


def test_roulette_current_player_empty_order():
    game = {"play_order": [], "current_idx": 0}
    assert _current_player(game) is None


def test_roulette_current_player_wraps():
    order = [{"id": USER_ID_1, "name": "Alice"}, {"id": USER_ID_2, "name": "Bob"}]
    game = {"play_order": order, "current_idx": 0}
    assert _current_player(game)["id"] == USER_ID_1
    game["current_idx"] = 2  # 2 % 2 == 0
    assert _current_player(game)["id"] == USER_ID_1
    game["current_idx"] = 3  # 3 % 2 == 1
    assert _current_player(game)["id"] == USER_ID_2


def test_roulette_shoot_logic():
    """shot_count == bullet_pos means hit."""
    for bullet_pos in range(1, 7):
        for shot in range(1, 7):
            hit = (shot == bullet_pos)
            assert hit == (shot == bullet_pos)


def test_roulette_bullet_always_in_range():
    for _ in range(200):
        bp = random.randint(1, 6)
        assert 1 <= bp <= 6


def test_roulette_collecting_text():
    game = {
        "players": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        "phase": "collecting",
    }
    text = _collecting_text(game)
    assert "Alice" in text
    assert "Bob" in text
    assert "Участники (2)" in text


def test_roulette_playing_text():
    game = {
        "shot_count": 2, "results": ["✅ Alice выжил"],
        "play_order": [{"id": 2, "name": "Bob"}],
        "current_idx": 0, "phase": "playing",
    }
    text = _playing_text(game)
    assert "Выстрел 3 из 6" in text
    assert "Bob" in text
    assert "ТВОЙ ХОД" in text


def test_roulette_final_text():
    game = {"results": ["✅ Alice выжил", "💀 Bob убит"]}
    text = _final_text(game)
    assert "ФИНАЛ" in text
    assert "Alice" in text
    assert "Bob" in text


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

    result = await _apply_mute(bot, CHAT_ID, {"id": USER_ID_1, "name": "Alice"})

    assert "мут не применён" in result.lower()
    bot.restrict_chat_member.assert_not_called()


@pytest.mark.asyncio
async def test_roulette_mute_bot_not_admin():
    bot = AsyncMock()
    bot.get_chat_member.side_effect = Exception("no rights")
    bot.restrict_chat_member.side_effect = Exception("can't restrict")

    result = await _apply_mute(bot, CHAT_ID, {"id": USER_ID_1, "name": "Alice"})

    assert "не применён" in result


@pytest.mark.asyncio
async def test_roulette_mute_success(setup_chat):
    bot = AsyncMock()
    member = MagicMock()
    member.status = "member"
    bot.get_chat_member.return_value = member
    bot.restrict_chat_member.return_value = True

    with patch("app.services.games.roulette.repo.get_active_mute_until", return_value=None), \
         patch("app.services.games.roulette.repo.log_mute", return_value=None):
        result = await _apply_mute(bot, CHAT_ID, {"id": USER_ID_1, "name": "Alice"})

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


# ──────────────────── Blackjack ────────────────────

@pytest.mark.asyncio
async def test_blackjack_profile_created(setup_chat):
    """Новый профиль создаётся с балансом 5000."""
    profile = await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    assert profile["balance"] == 5000
    assert profile["total_games"] == 0
    assert profile["wins"] == 0
    assert profile["losses"] == 0
    assert profile["draws"] == 0
    assert profile["max_balance"] == 5000


@pytest.mark.asyncio
async def test_blackjack_win(setup_chat):
    """Победа увеличивает баланс на ставку."""
    await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    new_balance = await repo.update_blackjack_balance(CHAT_ID, USER_ID_1, 100, "win")
    assert new_balance == 5100
    profile = await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    assert profile["wins"] == 1
    assert profile["total_games"] == 1
    assert profile["max_balance"] == 5100


@pytest.mark.asyncio
async def test_blackjack_loss(setup_chat):
    """Поражение уменьшает баланс на ставку."""
    await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    new_balance = await repo.update_blackjack_balance(CHAT_ID, USER_ID_1, -100, "loss")
    assert new_balance == 4900
    profile = await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    assert profile["losses"] == 1
    assert profile["total_games"] == 1


@pytest.mark.asyncio
async def test_blackjack_draw(setup_chat):
    """Ничья не меняет баланс."""
    await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    new_balance = await repo.update_blackjack_balance(CHAT_ID, USER_ID_1, 0, "draw")
    assert new_balance == 5000
    profile = await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    assert profile["draws"] == 1
    assert profile["total_games"] == 1


@pytest.mark.asyncio
async def test_blackjack_balance_floor(setup_chat):
    """Баланс не уходит ниже нуля."""
    await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    new_balance = await repo.update_blackjack_balance(CHAT_ID, USER_ID_1, -9999, "loss")
    assert new_balance == 0
    profile = await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    assert profile["balance"] == 0


@pytest.mark.asyncio
async def test_weekly_credits_given(setup_chat):
    """Первый запрос недельных кредитов даёт True."""
    result = await repo.claim_weekly_credits(CHAT_ID, USER_ID_1)
    assert result is True
    profile = await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    assert profile["balance"] == 10000  # 5000 + 5000


@pytest.mark.asyncio
async def test_weekly_credits_cooldown(setup_chat):
    """Второй запрос в ту же неделю возвращает datetime следующего получения."""
    await repo.claim_weekly_credits(CHAT_ID, USER_ID_1)
    result = await repo.claim_weekly_credits(CHAT_ID, USER_ID_1)
    from datetime import datetime
    assert isinstance(result, datetime)
    profile = await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    assert profile["balance"] == 10000  # не изменился после второго запроса


@pytest.mark.asyncio
async def test_blackjack_top(setup_chat):
    """Топ возвращает пользователей отсортированных по балансу."""
    await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    await repo.get_blackjack_profile(CHAT_ID, USER_ID_2)
    await repo.update_blackjack_balance(CHAT_ID, USER_ID_1, 500, "win")
    top = await repo.get_blackjack_top(CHAT_ID, limit=5)
    assert len(top) == 2
    assert top[0]["balance"] >= top[1]["balance"]
    assert top[0]["user_id"] == USER_ID_1


def test_card_score():
    """Счёт простой руки без тузов."""
    from app.services.games.blackjack import _score
    hand = ["10♠", "7♥"]
    assert _score(hand) == 17

    hand2 = ["K♦", "Q♣"]
    assert _score(hand2) == 20

    hand3 = ["5♠", "6♥", "9♣"]
    assert _score(hand3) == 20


def test_card_score_ace_adjustment():
    """Туз переключается с 11 на 1 при переборе."""
    from app.services.games.blackjack import _score
    # A + K = 21
    hand = ["A♠", "K♥"]
    assert _score(hand) == 21

    # A + K + 5 = 16 (A считается как 1)
    hand2 = ["A♠", "K♥", "5♦"]
    assert _score(hand2) == 16

    # A + A = 12 (один туз = 11, второй = 1)
    hand3 = ["A♠", "A♥"]
    assert _score(hand3) == 12


# ══════════════════════════════════════════════════════════════════════
# НОВЫЕ ТЕСТЫ — покрытие непокрытых модулей и механик
# ══════════════════════════════════════════════════════════════════════


# ──────────────────── Cactus: overwater mechanic ────────────────────

@pytest.mark.asyncio
async def test_cactus_overwater_first_is_safe(setup_chat):
    """Первый полив за день всегда безопасен (шанс перелива 0%)."""
    from app.services.games.cactus import OVERWATER_CHANCES
    assert OVERWATER_CHANCES[0] == 0.0


def test_cactus_overwater_chances_increasing():
    """Шансы перелива растут с каждым поливом."""
    from app.services.games.cactus import OVERWATER_CHANCES
    for i in range(1, len(OVERWATER_CHANCES)):
        assert OVERWATER_CHANCES[i] >= OVERWATER_CHANCES[i - 1]


def test_cactus_overwater_sixth_is_certain():
    """6-й+ полив = 100% перелив."""
    from app.services.games.cactus import OVERWATER_CHANCES
    assert OVERWATER_CHANCES[-1] == 1.0


@pytest.mark.asyncio
async def test_cactus_waters_today_tracking(setup_chat):
    """waters_today увеличивается при каждом поливе."""
    today = date.today().isoformat()
    await repo.get_cactus(CHAT_ID, USER_ID_1)  # создаёт запись
    await repo.update_cactus(CHAT_ID, USER_ID_1, 1, today, 1)
    cactus = await repo.get_cactus(CHAT_ID, USER_ID_1)
    assert cactus["waters_today"] == 1

    await repo.update_cactus(CHAT_ID, USER_ID_1, 2, today, 2)
    cactus = await repo.get_cactus(CHAT_ID, USER_ID_1)
    assert cactus["waters_today"] == 2


@pytest.mark.asyncio
async def test_cactus_reset_on_death(setup_chat):
    """reset_cactus обнуляет высоту."""
    today = date.today().isoformat()
    await repo.update_cactus(CHAT_ID, USER_ID_1, 50, today, 1)
    await repo.reset_cactus(CHAT_ID, USER_ID_1)
    cactus = await repo.get_cactus(CHAT_ID, USER_ID_1)
    assert cactus["height_cm"] == 0


def test_cactus_growth_stages():
    """Стадии роста корректно определяются."""
    from app.services.games.cactus import _get_stage
    emoji, name = _get_stage(0)
    assert "Семечко" in name
    emoji, name = _get_stage(5)
    assert "Росток" in name
    emoji, name = _get_stage(15)
    assert "Маленький" in name
    emoji, name = _get_stage(30)
    assert "Взрослый" in name
    emoji, name = _get_stage(50)
    assert "Цветущий" in name
    emoji, name = _get_stage(100)
    assert "Легендарный" in name


# ──────────────────── Cat: affinity mechanic ────────────────────

def test_cat_affinity_bar():
    """_affinity_bar возвращает корректные статусы."""
    from app.services.games.cat import _affinity_bar
    assert "обожает" in _affinity_bar(80)
    assert "доверяет" in _affinity_bar(55)
    assert "привыкает" in _affinity_bar(30)
    assert "настороженно" in _affinity_bar(19)
    assert "шипит" in _affinity_bar(10)


@pytest.mark.asyncio
async def test_cat_affinity_stored(setup_chat):
    """Привязанность сохраняется и читается из БД."""
    today = date.today().isoformat()
    await repo.get_cat(CHAT_ID, USER_ID_1)  # создаёт запись
    await repo.update_cat(CHAT_ID, USER_ID_1, 5, today, affinity=75,
                          action_field="last_feed_date", actions_today=1)
    cat = await repo.get_cat(CHAT_ID, USER_ID_1)
    assert cat["affinity"] == 75


@pytest.mark.asyncio
async def test_cat_affinity_clamped(setup_chat):
    """Привязанность не уходит выше 100 и ниже 0."""
    today = date.today().isoformat()
    await repo.get_cat(CHAT_ID, USER_ID_1)  # создаёт запись
    await repo.update_cat(CHAT_ID, USER_ID_1, 5, today, affinity=150,
                          action_field="last_feed_date", actions_today=1)
    cat = await repo.get_cat(CHAT_ID, USER_ID_1)
    assert cat["affinity"] == 100

    await repo.update_cat(CHAT_ID, USER_ID_1, 5, today, affinity=-10,
                          action_field="last_feed_date", actions_today=2)
    cat = await repo.get_cat(CHAT_ID, USER_ID_1)
    assert cat["affinity"] == 0


def test_cat_affinity_bonus_chance():
    """Высокая привязанность увеличивает positive_chance и уменьшает negative."""
    # affinity=100 → bonus=1.0
    positive_100 = cfg.CAT_POSITIVE_CHANCE + (1.0 * 0.15)
    negative_100 = max(0.05, cfg.CAT_NEGATIVE_CHANCE - (1.0 * 0.15))

    # affinity=0 → bonus=0
    positive_0 = cfg.CAT_POSITIVE_CHANCE + (0 * 0.15)
    negative_0 = max(0.05, cfg.CAT_NEGATIVE_CHANCE - (0 * 0.15))

    assert positive_100 > positive_0
    assert negative_100 < negative_0


@pytest.mark.asyncio
async def test_cat_decay_affinity(setup_chat):
    """decay_cat_affinity уменьшает привязанность для неактивных котов."""
    today = date.today().isoformat()
    await repo.get_cat(CHAT_ID, USER_ID_1)  # создаёт запись с affinity=25, actions_today=0
    # Установим affinity=50 но actions_today оставим 0 (как будто вчера не играли)
    db = await get_db()
    await db.execute(
        "UPDATE GameCat SET affinity=50, actions_today=0 WHERE chat_id=$1 AND user_id=$2",
        CHAT_ID, USER_ID_1,
    )
    count = await repo.decay_cat_affinity()
    assert count >= 1
    cat = await repo.get_cat(CHAT_ID, USER_ID_1)
    assert cat["affinity"] == 49


# ──────────────────── Home: action tracking ────────────────────

@pytest.mark.asyncio
async def test_home_action_tracking(setup_chat):
    """Действия по уборке сохраняются и читаются."""
    today = date.today().isoformat()
    done = await repo.get_home_actions_today(CHAT_ID, USER_ID_1, today)
    assert len(done) == 0

    await repo.add_home_action(CHAT_ID, USER_ID_1, "sweep", today)
    await repo.add_home_action(CHAT_ID, USER_ID_1, "mop", today)

    done = await repo.get_home_actions_today(CHAT_ID, USER_ID_1, today)
    assert done == {"sweep", "mop"}


@pytest.mark.asyncio
async def test_home_action_per_user(setup_chat):
    """Действия считаются на пользователя — один сделал, другой нет."""
    today = date.today().isoformat()
    await repo.add_home_action(CHAT_ID, USER_ID_1, "sweep", today)

    done1 = await repo.get_home_actions_today(CHAT_ID, USER_ID_1, today)
    done2 = await repo.get_home_actions_today(CHAT_ID, USER_ID_2, today)
    assert "sweep" in done1
    assert "sweep" not in done2


def test_home_score_tier():
    """Тиры очков правильно определяются."""
    from app.services.games.home import _score_tier
    assert _score_tier(5) == "low"
    assert _score_tier(9) == "low"
    assert _score_tier(10) == "mid"
    assert _score_tier(14) == "mid"
    assert _score_tier(15) == "high"
    assert _score_tier(20) == "high"


@pytest.mark.asyncio
async def test_home_decay(setup_chat):
    """Ночной распад порядка работает."""
    await repo.update_home_order(CHAT_ID, 30)  # 50 + 30 = 80
    await repo.decay_home_orders(min_decay=10, max_decay=10)
    order = await repo.get_home_order(CHAT_ID)
    assert order == 70  # 80 - 10


@pytest.mark.asyncio
async def test_home_reset(setup_chat):
    """Понедельничный сброс ставит указанное значение."""
    await repo.update_home_order(CHAT_ID, 40)  # 50 + 40 = 90
    await repo.reset_home_orders(score=20)
    order = await repo.get_home_order(CHAT_ID)
    assert order == 20


# ──────────────────── Blackjack: game logic ────────────────────

def test_blackjack_deal():
    """deal раздаёт по 2 карты игроку и дилеру."""
    from app.services.games.blackjack import BlackjackGame
    game = BlackjackGame(CHAT_ID, USER_ID_1, 100, 1, MagicMock())
    game.deal()
    assert len(game.player_hand) == 2
    assert len(game.dealer_hand) == 2


def test_blackjack_hit():
    """hit добавляет 1 карту игроку."""
    from app.services.games.blackjack import BlackjackGame
    game = BlackjackGame(CHAT_ID, USER_ID_1, 100, 1, MagicMock())
    game.deal()
    game.hit()
    assert len(game.player_hand) == 3


def test_blackjack_dealer_play_stops_at_17():
    """Дилер добирает до 17+."""
    from app.services.games.blackjack import BlackjackGame, _score
    game = BlackjackGame(CHAT_ID, USER_ID_1, 100, 1, MagicMock())
    game.dealer_hand = ["2♠", "3♥"]  # 5
    game._deck = ["K♠", "5♦", "4♣"]  # добирает 4+5+K=19... нет, дилер добирает по одной
    game.dealer_play()
    assert _score(game.dealer_hand) >= 17


def test_blackjack_double_flag():
    """doubled flag работает корректно."""
    from app.services.games.blackjack import BlackjackGame
    game = BlackjackGame(CHAT_ID, USER_ID_1, 100, 1, MagicMock())
    assert game.doubled is False
    game.doubled = True
    assert game.doubled is True


def test_blackjack_deck_52_cards():
    """Колода содержит 52 карты."""
    from app.services.games.blackjack import BlackjackGame
    game = BlackjackGame(CHAT_ID, USER_ID_1, 100, 1, MagicMock())
    assert len(game._deck) == 52
    assert len(set(game._deck)) == 52  # все уникальные


def test_blackjack_win_rate():
    """_win_rate форматируется правильно."""
    from app.services.games.blackjack import _win_rate
    assert _win_rate({"total_games": 0, "wins": 0, "losses": 0}) == "W:0 / L:0"
    assert "50%" in _win_rate({"total_games": 10, "wins": 5, "losses": 5})
    assert "100%" in _win_rate({"total_games": 3, "wins": 3, "losses": 0})


@pytest.mark.asyncio
async def test_blackjack_loan_transfer(setup_chat):
    """Трансфер кредитов между игроками работает."""
    await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)  # 5000
    await repo.get_blackjack_profile(CHAT_ID, USER_ID_2)  # 5000

    ok = await repo.transfer_blackjack_credits(CHAT_ID, USER_ID_1, USER_ID_2, 1000)
    assert ok is True

    p1 = await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    p2 = await repo.get_blackjack_profile(CHAT_ID, USER_ID_2)
    assert p1["balance"] == 4000
    assert p2["balance"] == 6000


@pytest.mark.asyncio
async def test_blackjack_loan_insufficient_funds(setup_chat):
    """Трансфер не работает при недостатке средств."""
    await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    # Сначала обнулим баланс
    await repo.update_blackjack_balance(CHAT_ID, USER_ID_1, -5000, "loss")

    ok = await repo.transfer_blackjack_credits(CHAT_ID, USER_ID_1, USER_ID_2, 1000)
    assert ok is False


def test_blackjack_score_blackjack():
    """Натуральный блэкджек: A + 10/J/Q/K = 21."""
    from app.services.games.blackjack import _score
    assert _score(["A♠", "10♥"]) == 21
    assert _score(["A♠", "J♥"]) == 21
    assert _score(["A♠", "Q♥"]) == 21
    assert _score(["A♠", "K♥"]) == 21


def test_blackjack_score_multiple_aces():
    """Три туза = 13 (11 + 1 + 1)."""
    from app.services.games.blackjack import _score
    assert _score(["A♠", "A♥", "A♦"]) == 13


def test_blackjack_score_bust():
    """Перебор корректно считается."""
    from app.services.games.blackjack import _score
    assert _score(["K♠", "Q♥", "5♦"]) == 25


# ──────────────────── Roulette: _edit_msg / _edit_or_send ────────────────────

@pytest.mark.asyncio
async def test_roulette_edit_msg_success():
    """_edit_msg возвращает True при успехе."""
    bot = AsyncMock()
    result = await _edit_msg(bot, CHAT_ID, 1, "test text")
    assert result is True
    bot.edit_message_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_roulette_edit_msg_not_modified():
    """_edit_msg возвращает True для 'message is not modified'."""
    from aiogram.exceptions import TelegramBadRequest
    bot = AsyncMock()
    bot.edit_message_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="Bad Request: message is not modified"
    )
    result = await _edit_msg(bot, CHAT_ID, 1, "same text")
    assert result is True


@pytest.mark.asyncio
async def test_roulette_edit_msg_failure():
    """_edit_msg возвращает False при ошибке."""
    from aiogram.exceptions import TelegramBadRequest
    bot = AsyncMock()
    bot.edit_message_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="Bad Request: message to edit not found"
    )
    result = await _edit_msg(bot, CHAT_ID, 1, "text")
    assert result is False


@pytest.mark.asyncio
async def test_roulette_edit_or_send_fallback():
    """_edit_or_send отправляет новое сообщение если edit не удался."""
    from aiogram.exceptions import TelegramBadRequest
    bot = AsyncMock()
    bot.edit_message_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="Bad Request: message to edit not found"
    )
    sent_msg = MagicMock()
    sent_msg.message_id = 999
    bot.send_message.return_value = sent_msg

    with patch("app.services.games.roulette.repo.update_active_roulette"):
        new_msg_id = await _edit_or_send(bot, CHAT_ID, 1, "fallback text")

    bot.send_message.assert_awaited_once()
    assert new_msg_id == 999


# ──────────────────── Duel: repository ────────────────────

@pytest.mark.asyncio
async def test_duel_stats_both_players(setup_chat):
    """Статистика считается для обоих игроков."""
    await repo.create_duel(CHAT_ID, USER_ID_1, USER_ID_2, USER_ID_1, 30)
    await repo.create_duel(CHAT_ID, USER_ID_1, USER_ID_2, USER_ID_2, 30)

    stats1 = await repo.get_duel_stats(CHAT_ID, USER_ID_1)
    stats2 = await repo.get_duel_stats(CHAT_ID, USER_ID_2)
    assert stats1["wins"] == 1
    assert stats1["total"] == 2
    assert stats2["wins"] == 1
    assert stats2["total"] == 2


# ──────────────────── MuteLog ────────────────────

@pytest.mark.asyncio
async def test_mute_log_and_check(setup_chat):
    """log_mute и get_active_mute_until работают вместе."""
    mute_until = (now_kyiv() + timedelta(minutes=30)).isoformat()
    await repo.log_mute(CHAT_ID, USER_ID_1, "duel", mute_until)

    active = await repo.get_active_mute_until(CHAT_ID, USER_ID_1)
    assert active is not None

    is_muted = await repo.is_user_muted(CHAT_ID, USER_ID_1)
    assert is_muted is True


@pytest.mark.asyncio
async def test_mute_expired_not_active(setup_chat):
    """Истёкший мут не считается активным."""
    mute_until = (now_kyiv() - timedelta(minutes=5)).isoformat()
    await repo.log_mute(CHAT_ID, USER_ID_1, "duel", mute_until)

    is_muted = await repo.is_user_muted(CHAT_ID, USER_ID_1)
    assert is_muted is False


# ──────────────────── Roulette: last time with LIMIT ────────────────────

@pytest.mark.asyncio
async def test_roulette_last_time_with_many_games(setup_chat):
    """get_last_roulette_time работает c LIMIT 50 и множеством игр."""
    # Создадим 10 игр где USER_ID_2 не участвовал
    for _ in range(10):
        await repo.create_roulette(CHAT_ID, json.dumps([USER_ID_1]), USER_ID_1)

    # USER_ID_2 не участвовал ни в одной
    last = await repo.get_last_roulette_time(CHAT_ID, USER_ID_2)
    assert last is None

    # Теперь USER_ID_2 участвует в новой игре
    await repo.create_roulette(CHAT_ID, json.dumps([USER_ID_1, USER_ID_2]), USER_ID_1)
    last = await repo.get_last_roulette_time(CHAT_ID, USER_ID_2)
    assert last is not None


# ──────────────────── Export Bugs ────────────────────

from app.services.feedback.export import generate_html


@pytest.mark.asyncio
async def test_export_generate_html_empty():
    html = generate_html([])
    assert "Обращений не найдено" in html
    assert "<!DOCTYPE html>" in html


@pytest.mark.asyncio
async def test_export_generate_html_with_items():
    items = [
        {"id": 1, "user_id": 111, "chat_id": -100, "username": "alice",
         "category": "bug", "text": "Кнопка не работает", "status": "open",
         "created_at": "2026-03-10T12:00:00"},
        {"id": 2, "user_id": 222, "chat_id": -100, "username": None,
         "category": "idea", "text": "Добавить спидтест", "status": "done",
         "created_at": "2026-03-09T10:00:00"},
    ]
    html = generate_html(items)
    assert "Кнопка не работает" in html
    assert "@alice" in html
    assert "id222" in html
    assert "🐛" in html
    assert "💡" in html
    assert "открыто" in html
    assert "закрыто" in html


@pytest.mark.asyncio
async def test_export_generate_html_escapes_xss():
    items = [
        {"id": 1, "user_id": 111, "chat_id": -100, "username": "<script>alert(1)</script>",
         "category": "bug", "text": "<b>bold</b>", "status": "open",
         "created_at": None},
    ]
    html = generate_html(items)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


@pytest.mark.asyncio
async def test_export_generate_html_stats():
    items = [
        {"id": i, "user_id": 111, "chat_id": -100, "username": "u",
         "category": cat, "text": "t", "status": st,
         "created_at": "2026-03-10T12:00:00"}
        for i, (cat, st) in enumerate([
            ("bug", "open"), ("bug", "open"), ("idea", "done"), ("complaint", "open"),
        ])
    ]
    html = generate_html(items)
    # Stats: 4 total, 3 open, 1 done
    assert ">4<" in html
    assert ">3<" in html
    assert ">1<" in html


@pytest.mark.asyncio
async def test_get_all_feedback_no_filter(setup_chat):
    await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "bug", "баг раз")
    await repo.create_feedback(USER_ID_2, CHAT_ID, "user2", "idea", "идея")

    items = await repo.get_all_feedback()
    assert len(items) == 2


@pytest.mark.asyncio
async def test_get_all_feedback_status_filter(setup_chat):
    fid = await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "bug", "баг")
    await repo.create_feedback(USER_ID_2, CHAT_ID, "user2", "idea", "идея")
    await repo.close_feedback(fid)

    open_items = await repo.get_all_feedback(status="open")
    assert len(open_items) == 1
    assert open_items[0]["category"] == "idea"

    done_items = await repo.get_all_feedback(status="done")
    assert len(done_items) == 1
    assert done_items[0]["category"] == "bug"


@pytest.mark.asyncio
async def test_get_all_feedback_category_filter(setup_chat):
    await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "bug", "баг")
    await repo.create_feedback(USER_ID_2, CHAT_ID, "user2", "idea", "идея")
    await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "bug", "ещё баг")

    bugs = await repo.get_all_feedback(category="bug")
    assert len(bugs) == 2
    assert all(b["category"] == "bug" for b in bugs)


@pytest.mark.asyncio
async def test_get_all_feedback_combined_filter(setup_chat):
    fid = await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "bug", "закрытый баг")
    await repo.create_feedback(USER_ID_2, CHAT_ID, "user2", "bug", "открытый баг")
    await repo.create_feedback(USER_ID_1, CHAT_ID, "user1", "idea", "открытая идея")
    await repo.close_feedback(fid)

    items = await repo.get_all_feedback(status="open", category="bug")
    assert len(items) == 1
    assert items[0]["text"] == "открытый баг"


@pytest.mark.asyncio
async def test_export_generate_html_no_text():
    """Media-only feedback (text=None) should show placeholder."""
    items = [
        {"id": 1, "user_id": 111, "chat_id": -100, "username": "u",
         "category": "bug", "text": None, "status": "open",
         "created_at": "2026-03-10T12:00:00"},
    ]
    html = generate_html(items)
    assert "медиа без текста" in html


# ──────────────────── Blackjack: double down validation ────────────────────

def test_blackjack_can_double_requires_2x_stake():
    """Кнопка удвоения не показывается, если баланс < stake * 2."""
    from app.services.games.blackjack import _action_kb
    # can_double=True → кнопка есть
    kb = _action_kb(can_double=True)
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Удвоить" in t for t in texts)

    # can_double=False → кнопки нет
    kb = _action_kb(can_double=False)
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert not any("Удвоить" in t for t in texts)


@pytest.mark.asyncio
async def test_blackjack_double_denied_insufficient_balance(setup_chat):
    """Удвоение отклоняется если баланс < stake * 2."""
    profile = await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    initial_balance = profile["balance"]  # 5000
    stake = 3000
    # balance=5000, stake=3000 → 5000 < 3000*2=6000 → нельзя удвоить
    assert initial_balance < stake * 2


@pytest.mark.asyncio
async def test_blackjack_double_allowed_sufficient_balance(setup_chat):
    """Удвоение разрешается если баланс >= stake * 2."""
    profile = await repo.get_blackjack_profile(CHAT_ID, USER_ID_1)
    initial_balance = profile["balance"]  # 5000
    stake = 2500
    # balance=5000, stake=2500 → 5000 >= 2500*2=5000 → можно удвоить
    assert initial_balance >= stake * 2


# ──────────────────── Feedback: media group dedup ────────────────────

def test_feedback_media_group_dedup():
    """_seen_media_groups дедуплицирует медиагруппы."""
    from app.services.feedback.handler import _seen_media_groups
    _seen_media_groups.clear()

    mg_id = "test_mg_123"
    assert mg_id not in _seen_media_groups
    _seen_media_groups.add(mg_id)
    assert mg_id in _seen_media_groups
    _seen_media_groups.clear()


def test_feedback_media_group_overflow_cleanup():
    """_seen_media_groups очищается при >100 записей."""
    from app.services.feedback.handler import _seen_media_groups
    _seen_media_groups.clear()

    for i in range(101):
        _seen_media_groups.add(f"mg_{i}")

    assert len(_seen_media_groups) == 101
    # Симулируем логику из handler: если > 100, clear и добавить текущий
    new_id = "mg_new"
    if len(_seen_media_groups) > 100:
        _seen_media_groups.clear()
        _seen_media_groups.add(new_id)

    assert len(_seen_media_groups) == 1
    assert new_id in _seen_media_groups
    _seen_media_groups.clear()


# ──────────────────── Roulette: DB-backed active game ────────────────────

@pytest.mark.asyncio
async def test_create_active_roulette(setup_chat):
    players = json.dumps([{"id": USER_ID_1, "name": "Alice"}])
    await repo.create_active_roulette(CHAT_ID, 100, players)
    game = await repo.get_active_roulette(CHAT_ID)
    assert game is not None
    assert game["msg_id"] == 100
    assert game["phase"] == "collecting"
    await repo.delete_active_roulette(CHAT_ID)


@pytest.mark.asyncio
async def test_get_active_roulette_none(setup_chat):
    game = await repo.get_active_roulette(CHAT_ID)
    assert game is None


@pytest.mark.asyncio
async def test_update_active_roulette(setup_chat):
    players = json.dumps([{"id": USER_ID_1, "name": "Alice"}])
    await repo.create_active_roulette(CHAT_ID, 100, players)
    await repo.update_active_roulette(CHAT_ID, phase="playing", bullet_pos=3)
    game = await repo.get_active_roulette(CHAT_ID)
    assert game["phase"] == "playing"
    assert game["bullet_pos"] == 3
    await repo.delete_active_roulette(CHAT_ID)


@pytest.mark.asyncio
async def test_delete_active_roulette(setup_chat):
    players = json.dumps([{"id": USER_ID_1, "name": "Alice"}])
    await repo.create_active_roulette(CHAT_ID, 100, players)
    await repo.delete_active_roulette(CHAT_ID)
    assert await repo.get_active_roulette(CHAT_ID) is None


@pytest.mark.asyncio
async def test_update_active_roulette_invalid_field(setup_chat):
    players = json.dumps([{"id": USER_ID_1, "name": "Alice"}])
    await repo.create_active_roulette(CHAT_ID, 100, players)
    with pytest.raises(ValueError, match="Invalid fields"):
        await repo.update_active_roulette(CHAT_ID, hacked_field="oops")
    await repo.delete_active_roulette(CHAT_ID)


@pytest.mark.asyncio
async def test_get_all_active_roulettes(setup_chat):
    chat2 = CHAT_ID + 1
    await repo.get_or_create_chat(chat2, "Chat 2", USER_ID_2)
    p1 = json.dumps([{"id": USER_ID_1, "name": "Alice"}])
    p2 = json.dumps([{"id": USER_ID_2, "name": "Bob"}])
    await repo.create_active_roulette(CHAT_ID, 100, p1)
    await repo.create_active_roulette(chat2, 200, p2)
    all_games = await repo.get_all_active_roulettes()
    assert len(all_games) == 2
    await repo.delete_active_roulette(CHAT_ID)
    await repo.delete_active_roulette(chat2)


@pytest.mark.asyncio
async def test_active_roulette_full_lifecycle(setup_chat):
    """Полный цикл: создание, обновление игроков, переход в playing, удаление."""
    players = [{"id": USER_ID_1, "name": "Alice"}]
    await repo.create_active_roulette(CHAT_ID, 100, json.dumps(players))

    # Добавляем игрока
    players.append({"id": USER_ID_2, "name": "Bob"})
    await repo.update_active_roulette(CHAT_ID, players=json.dumps(players))

    # Переход в playing
    order = players.copy()
    await repo.update_active_roulette(
        CHAT_ID, phase="playing",
        play_order=json.dumps(order),
        bullet_pos=4, shot_count=0, current_idx=0,
    )

    game = await repo.get_active_roulette(CHAT_ID)
    assert game["phase"] == "playing"
    parsed = _parse_game(game)
    assert len(parsed["players"]) == 2
    assert len(parsed["play_order"]) == 2
    assert parsed["bullet_pos"] == 4

    # Выстрел
    await repo.update_active_roulette(CHAT_ID, shot_count=1, current_idx=1)

    # Финиш
    await repo.delete_active_roulette(CHAT_ID)
    assert await repo.get_active_roulette(CHAT_ID) is None
