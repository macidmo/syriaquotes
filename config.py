"""Application settings loaded from environment variables (.env)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent


class ConfigError(RuntimeError):
    """Raised when the configuration is missing or invalid."""


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"المتغير {name} مطلوب — أضفه إلى ملف .env")
    return value


def _get_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} يجب أن يكون رقماً صحيحاً (القيمة الحالية: {raw!r})") from exc
    if value < minimum:
        raise ConfigError(f"{name} يجب أن يكون {minimum} أو أكبر")
    return value


def _get_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} يجب أن يكون رقماً (القيمة الحالية: {raw!r})") from exc
    if value < minimum:
        raise ConfigError(f"{name} يجب أن يكون {minimum} أو أكبر")
    return value


def _parse_channel_id(raw: str) -> int | str:
    raw = raw.strip()
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"@[A-Za-z][A-Za-z0-9_]{3,}", raw):
        return raw
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,}", raw):
        return f"@{raw}"
    raise ConfigError("CHANNEL_ID يجب أن يكون رقماً مثل -1001234567890 أو @username")


def _normalize_channel_url(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("@") and len(raw) > 1:
        return f"https://t.me/{raw[1:]}"
    if raw.lower().startswith(("t.me/", "telegram.me/")):
        return f"https://{raw}"
    if raw.lower().startswith(("http://", "https://")):
        return raw
    raise ConfigError("CHANNEL_URL يجب أن يبدأ بـ https://t.me/")


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in re.split(r"[,\s;]+", raw.strip()):
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError as exc:
            raise ConfigError(f"ADMIN_IDS يحتوي قيمة غير صالحة: {part!r}") from exc
    return frozenset(ids)


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    channel_id: int | str
    channel_url: str
    admin_ids: frozenset[int]
    max_text_length: int
    max_media_per_submission: int
    max_image_size_mb: int
    max_video_size_mb: int
    max_urls_per_submission: int
    submission_cooldown_seconds: int
    preview_delay_seconds: float
    draft_ttl_minutes: int
    database_url: str
    timezone: ZoneInfo
    log_level: str

    @property
    def max_image_size_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024

    @property
    def max_video_size_bytes(self) -> int:
        return self.max_video_size_mb * 1024 * 1024


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")

    bot_token = _required("BOT_TOKEN")
    if ":" not in bot_token:
        raise ConfigError("BOT_TOKEN يبدو غير صحيح — انسخه من @BotFather كما هو")

    tz_name = os.getenv("TIMEZONE", "Asia/Damascus").strip() or "Asia/Damascus"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError(f"TIMEZONE غير معروف: {tz_name!r} (تأكد من تثبيت tzdata)") from exc

    default_db = f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'data' / 'bot.db').as_posix()}"

    return Settings(
        bot_token=bot_token,
        channel_id=_parse_channel_id(_required("CHANNEL_ID")),
        channel_url=_normalize_channel_url(_required("CHANNEL_URL")),
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        max_text_length=_get_int("MAX_TEXT_LENGTH", 500, minimum=1),
        max_media_per_submission=_get_int("MAX_MEDIA_PER_SUBMISSION", 5, minimum=1),
        max_image_size_mb=_get_int("MAX_IMAGE_SIZE_MB", 10, minimum=1),
        max_video_size_mb=_get_int("MAX_VIDEO_SIZE_MB", 50, minimum=1),
        max_urls_per_submission=_get_int("MAX_URLS_PER_SUBMISSION", 10, minimum=1),
        submission_cooldown_seconds=_get_int("SUBMISSION_COOLDOWN_SECONDS", 10, minimum=0),
        preview_delay_seconds=_get_float("PREVIEW_DELAY_SECONDS", 1.5, minimum=0.2),
        draft_ttl_minutes=_get_int("DRAFT_TTL_MINUTES", 30, minimum=1),
        database_url=os.getenv("DATABASE_URL", "").strip() or default_db,
        timezone=tz,
        log_level=(os.getenv("LOG_LEVEL", "INFO").strip() or "INFO").upper(),
    )
