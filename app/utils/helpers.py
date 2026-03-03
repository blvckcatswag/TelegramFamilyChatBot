from datetime import datetime, date
from zoneinfo import ZoneInfo

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
