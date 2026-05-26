import logging
import logging.handlers
import os


def setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # ── Console: INFO ──────────────────────────────────────────────────────────
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # ── File: WARNING+, rotating 10 MB × 5 ────────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        "logs/bot.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root.addHandler(console)
    root.addHandler(file_handler)

    # ── AI requests log: separate file ────────────────────────────────────────
    # Format: timestamp | user_id | order_type | model | tokens_in | tokens_out | cost_usd
    ai_handler = logging.handlers.RotatingFileHandler(
        "logs/ai_requests.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    ai_handler.setLevel(logging.INFO)
    ai_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))

    ai_logger = logging.getLogger("ai_requests")
    ai_logger.addHandler(ai_handler)
    ai_logger.setLevel(logging.INFO)
    ai_logger.propagate = False  # don't bubble up to root

    # ── Errors log: separate file ──────────────────────────────────────────────
    errors_handler = logging.handlers.RotatingFileHandler(
        "logs/errors.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s\n%(message)s\n",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(errors_handler)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "asyncio", "aiogram.event"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
