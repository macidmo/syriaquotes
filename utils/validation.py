"""Validation rules for incoming content."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .. import texts
from ..schemas import MEDIA_PHOTO, MEDIA_VIDEO
from .links import detect_platform, normalize_url

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings
    from ..services.drafts import Draft

ALLOWED_VIDEO_MIME = {"video/mp4", "video/quicktime"}


def check_video_format(mime_type: str | None) -> str | None:
    """Telegram may omit the mime type; only reject when it is known and unsupported."""
    if mime_type and mime_type.lower() not in ALLOWED_VIDEO_MIME:
        return texts.VIDEO_FORMAT
    return None


def check_file_size(media_type: str, file_size: int | None, settings: "Settings") -> str | None:
    size = file_size or 0
    if media_type == MEDIA_PHOTO and size > settings.max_image_size_bytes:
        return texts.IMAGE_TOO_BIG
    if media_type == MEDIA_VIDEO and size > settings.max_video_size_bytes:
        return texts.VIDEO_TOO_BIG
    return None


def validate_draft(draft: "Draft", settings: "Settings") -> str | None:
    """Full re-validation right before saving. Returns an Arabic error or None."""
    if not draft.text and not draft.urls and not draft.media:
        return texts.EMPTY_SUBMISSION
    if len(draft.text) > settings.max_text_length:
        return texts.text_too_long(settings.max_text_length)
    if len(draft.media) > settings.max_media_per_submission:
        return texts.too_many_media(settings.max_media_per_submission)
    if len(draft.urls) > settings.max_urls_per_submission:
        return texts.too_many_urls(settings.max_urls_per_submission)
    for media in draft.media:
        error = check_file_size(media.media_type, media.file_size, settings)
        if error:
            return error
    for link in draft.urls:
        if normalize_url(link.url) is None or detect_platform(link.url) is None:
            return texts.INVALID_URL
    return None
