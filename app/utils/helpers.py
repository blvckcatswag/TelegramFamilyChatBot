from datetime import datetime, date


def progress_bar(value: int, max_val: int = 100, length: int = 10) -> str:
    filled = round(length * value / max_val) if max_val else 0
    empty = length - filled
    bar = "\u2588" * filled + "\u2591" * empty
    return f"{bar} {value}%"


def mention_user(first_name: str | None, username: str | None, user_id: int) -> str:
    if username:
        return f"@{username}"
    name = first_name or "User"
    return f'<a href="tg://user?id={user_id}">{name}</a>'


def today_str() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.utcnow().isoformat()


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
