import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
SUPERADMIN_ID: int = int(os.getenv("SUPERADMIN_ID", "0"))
OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "")
SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")

# Database: PostgreSQL (production) or SQLite (local dev/tests)
# postgresql://user:pass@host:port/dbname  OR  sqlite:///path/to/bot.db
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'bot.db'}")

# Legacy fallback
DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "bot.db"))

DEFAULT_WEATHER_TIME: str = os.getenv("DEFAULT_WEATHER_TIME", "07:00")
DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "Europe/Kiev")

# --- Donation crypto wallets ---
CRYPTO_USDT_TRC20: str = os.getenv("CRYPTO_USDT_TRC20", "TXAu1JRDwtoYbVVW7xm7sKoxmsB41hjByE")
CRYPTO_TON: str = os.getenv("CRYPTO_TON", "UQA6R_p4Wcazh9yGV5_mDIzeIu9i5FHpIzspbzdpSs8QtTqW")

# --- Limits ---
MAX_WEATHER_CITIES_PER_CHAT = 5
MAX_REMINDERS_PER_CHAT = 20
MAX_QUOTES_PER_CHAT = 500
MAX_WEATHER_REQUESTS_PER_HOUR = 10

# --- Game defaults ---
CACTUS_SUCCESS_CHANCE = 0.99
CACTUS_NEGATIVE_CHANCE = 0.01
CACTUS_MUTE_MINUTES = 15

CAT_POSITIVE_CHANCE = 0.50
CAT_NEUTRAL_CHANCE = 0.30
CAT_NEGATIVE_CHANCE = 0.20
CAT_CACTUS_EASTER_EGG_CHANCE = 0.0001

DUEL_ACCEPT_TIMEOUT = 60
DUEL_DEFAULT_MUTE_MINUTES = 30
DUEL_COOLDOWN_MINUTES = 10

ROULETTE_JOIN_TIMEOUT = 60
ROULETTE_MUTE_MINUTES = 20
ROULETTE_COOLDOWN_MINUTES = 10
ROULETTE_MIN_PLAYERS = 1
ROULETTE_MAX_PLAYERS = 6

TRANSLATOR_TRIGGER_CHANCE = 0.35

HOME_ORDER_MAX = 100
HOME_ORDER_MIN = 0
