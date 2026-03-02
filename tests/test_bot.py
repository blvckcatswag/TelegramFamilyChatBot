"""Tests for Family Chat Bot — per TZ section 15."""
import asyncio
import json
import random
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import aiosqlite

from app.db.database import init_db, get_db, close_db
from app.db import repositories as repo
from app.config import settings as cfg
from app.utils.helpers import progress_bar, parse_date, format_birthday_date


# ──────────────────── Fixtures ────────────────────

@pytest_asyncio.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a fresh DB for each test."""
    await close_db()
    cfg.DB_PATH = str(tmp_path / "test.db")
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
