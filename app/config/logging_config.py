import logging


def setup_logging() -> None:
    """Configure logging for Railway (stdout only) with noise reduction."""
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt, datefmt))

    logging.basicConfig(level=logging.INFO, handlers=[handler])

    # These libraries are very noisy at INFO level — only show warnings+
    for noisy in ("aiogram", "aiohttp", "asyncio", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
