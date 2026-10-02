"""Logging setup with automatic secret redaction."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Iterable

from .config import PROJECT_ROOT, Settings

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


class RedactingFormatter(logging.Formatter):
    """Replaces secrets (e.g. the bot token) anywhere in the final log line,
    including tracebacks, so they can never leak into log files."""

    def __init__(self, fmt: str, secrets: Iterable[str]) -> None:
        super().__init__(fmt)
        self._secrets = [s for s in secrets if s]

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text


def setup_logging(settings: Settings) -> None:
    formatter = RedactingFormatter(_FORMAT, [settings.bot_token])
    level = getattr(logging, settings.log_level, logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        log_dir = PROJECT_ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_dir / "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
        )
    except OSError as exc:  # read-only filesystem etc. — console logging still works
        print(f"تعذر إنشاء ملف السجل: {exc}", file=sys.stderr)

    for handler in handlers:
        handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    for handler in handlers:
        root.addHandler(handler)

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
