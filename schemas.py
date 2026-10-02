"""Plain data containers shared between layers (no framework dependencies)."""
from __future__ import annotations

from dataclasses import dataclass

MEDIA_PHOTO = "photo"
MEDIA_VIDEO = "video"


@dataclass(frozen=True, slots=True)
class UrlData:
    url: str
    platform: str


@dataclass(frozen=True, slots=True)
class MediaData:
    telegram_file_id: str
    file_unique_id: str
    media_type: str
    file_size: int | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    caption: str | None = None
    message_id: int | None = None
    media_group_id: str | None = None


@dataclass(frozen=True, slots=True)
class StatsData:
    total_users: int
    total_submissions: int
    new: int
    reviewed: int
    published: int
    rejected: int
    today: int
    week: int
