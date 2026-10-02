"""Small text helpers."""
from __future__ import annotations

import re

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(text: str) -> str:
    """Normalize whitespace/newlines and strip control characters."""
    text = _CONTROL_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def shorten(text: str, limit: int) -> str:
    """Truncate to ``limit`` characters, adding an ellipsis when cut."""
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"
