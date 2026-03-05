from datetime import datetime, date
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message as AiogramMessage

from app.config import settings as cfg

KYIV_TZ = ZoneInfo(cfg.DEFAULT_TIMEZONE)


def now_kyiv() -> datetime:
    return datetime.now(KYIV_TZ)


def progress_bar(value: int, max_val: int = 100, length: int = 10) -> str:
    filled = round(length * value / max_val) if max_val else 0
    empty = length - filled
    bar = "█" * filled + "░" * empty
    return f"{bar} {value}%"


def mention_user(first_name: str | None, username: str | None, user_id: int) -> str:
    if username:
        return f"@{username}"
    name = first_name or "User"
    return f'<a href="tg://user?id={user_id}">{name}</a>'


def today_str() -> str:
    return now_kyiv().date().isoformat()


def now_iso() -> str:
    return now_kyiv().isoformat()


def parse_date(s: str) -> date | None:
    for fmt in ("%d.%m", "%d.%m.%Y"):
        try:
            d = datetime.strptime(s, fmt).date()
            return d
        except ValueError:
            continue
    return None


def format_birthday_date(d: str) -> str:
    try:
        parts = d.split("-")
        return f"{parts[1]}.{parts[0]}"
    except (IndexError, ValueError):
        return d


async def safe_edit_text(message: AiogramMessage, text: str, **kwargs) -> None:
    """Edit message text, silently ignoring 'message is not modified' errors."""
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def safe_edit_reply_markup(message: AiogramMessage, **kwargs) -> None:
    """Edit message reply markup, silently ignoring 'message is not modified' errors."""
    try:
        await message.edit_reply_markup(**kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
