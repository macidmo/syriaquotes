"""In-memory drafts: a submission being assembled before the user confirms it.

A draft is what turns many separate Telegram messages (text, several photos,
album items, links) into ONE submission. It is kept in memory only; nothing is
written to the database until the user presses "confirm".
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from ..schemas import MEDIA_PHOTO, MEDIA_VIDEO, MediaData, UrlData


@dataclass(eq=False)
class Draft:
    user_id: int
    chat_id: int
    text_parts: list[str] = field(default_factory=list)
    urls: list[UrlData] = field(default_factory=list)
    media: list[MediaData] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    version: int = 0  # bumped on every accepted change (used to debounce the preview)
    preview_message_id: int | None = None
    prompt_message_id: int | None = None
    confirming: bool = False
    last_activity: float = field(default_factory=time.monotonic)
    _notified: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    @property
    def text(self) -> str:
        return "\n".join(self.text_parts)

    @property
    def photo_count(self) -> int:
        return sum(1 for m in self.media if m.media_type == MEDIA_PHOTO)

    @property
    def video_count(self) -> int:
        return sum(1 for m in self.media if m.media_type == MEDIA_VIDEO)

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def should_notify(self, key: str, window: float = 3.0) -> bool:
        """Rate-limit repeated error replies (e.g. when an album exceeds a limit)."""
        now = time.monotonic()
        if now - self._notified.get(key, -window) < window:
            return False
        self._notified[key] = now
        return True


class DraftStore:
    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._drafts: dict[int, Draft] = {}

    def _expired(self, draft: Draft) -> bool:
        return time.monotonic() - draft.last_activity > self._ttl

    def start(self, user_id: int, chat_id: int) -> Draft:
        """Begin a fresh draft (replacing any previous one)."""
        draft = Draft(user_id=user_id, chat_id=chat_id)
        self._drafts[user_id] = draft
        return draft

    def get(self, user_id: int) -> Draft | None:
        draft = self._drafts.get(user_id)
        if draft is None:
            return None
        if self._expired(draft):
            self._drafts.pop(user_id, None)
            return None
        return draft

    def has(self, user_id: int) -> bool:
        return self.get(user_id) is not None

    def discard(self, user_id: int) -> Draft | None:
        return self._drafts.pop(user_id, None)

    def purge_expired(self) -> int:
        stale = [uid for uid, d in self._drafts.items() if self._expired(d)]
        for uid in stale:
            self._drafts.pop(uid, None)
        return len(stale)
