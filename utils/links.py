"""URL detection, validation and platform recognition."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlsplit

from .text import clean_text

MAX_URL_LENGTH = 2048

PLATFORM_DOMAINS: dict[str, tuple[str, ...]] = {
    "Facebook": ("facebook.com", "fb.com", "fb.watch", "fb.me"),
    "Instagram": ("instagram.com", "instagr.am"),
    "TikTok": ("tiktok.com",),
    "YouTube": ("youtube.com", "youtu.be"),
    "Threads": ("threads.net", "threads.com"),
    "X": ("x.com", "twitter.com"),
}

_DOMAIN_TO_PLATFORM: dict[str, str] = {
    domain: platform for platform, domains in PLATFORM_DOMAINS.items() for domain in domains
}
_KNOWN_DOMAINS = "|".join(
    re.escape(d) for d in sorted(_DOMAIN_TO_PLATFORM, key=len, reverse=True)
)

# 1) anything starting with http(s):// or www.
# 2) bare links of the supported platforms that include a path (e.g. youtu.be/abc)
_URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"'«»]+"
    r"|(?<![\w@./-])(?:[a-z0-9-]+\.)*(?:" + _KNOWN_DOMAINS + r")/[^\s<>\"'«»]*",
    re.IGNORECASE,
)
_HOST_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9-]{1,63}\.)+[a-z][a-z0-9-]{1,62}$")
_TRAILING = ".,;:!?)]}»\"'،؛؟…*_"


@dataclass(frozen=True, slots=True)
class LinkInfo:
    url: str
    platform: str | None  # None => valid URL but unsupported platform
    host: str


@dataclass(slots=True)
class ExtractionResult:
    links: list[LinkInfo] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    cleaned_text: str = ""

    @property
    def supported(self) -> list[LinkInfo]:
        return [link for link in self.links if link.platform is not None]

    @property
    def unsupported(self) -> list[LinkInfo]:
        return [link for link in self.links if link.platform is None]


def _strip_trailing(url: str) -> str:
    while url and url[-1] in _TRAILING:
        if url[-1] == ")" and url.count("(") >= url.count(")"):
            break
        url = url[:-1]
    return url


def normalize_url(raw: str) -> str | None:
    """Return a clean http(s) URL, or None when the value is not a valid URL."""
    candidate = _strip_trailing(raw.strip())
    if not candidate or len(candidate) > MAX_URL_LENGTH or re.search(r"\s", candidate):
        return None
    if not re.match(r"(?i)^https?://", candidate):
        candidate = "https://" + candidate
    try:
        parts = urlsplit(candidate)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not host:
        return None
    if not _HOST_RE.match(host.lower()):
        return None
    return candidate


def get_host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def detect_platform(url: str) -> str | None:
    """Map a URL to one of the six supported platforms (suffix match on the host)."""
    host = get_host(url)
    if not host:
        return None
    for domain, platform in _DOMAIN_TO_PLATFORM.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return None


def extract_links(text: str, extra_urls: Iterable[str] = ()) -> ExtractionResult:
    """Find every URL in ``text`` (plus ``extra_urls`` such as hidden text-link
    entities). Returns the links, the invalid candidates, and the text with all
    URLs removed (URLs never count toward the text length limit)."""
    result = ExtractionResult()
    seen: set[str] = set()

    def register(raw: str) -> None:
        normalized = normalize_url(raw)
        if normalized is None:
            result.invalid.append(raw[:100])
            return
        if normalized in seen:
            return
        seen.add(normalized)
        result.links.append(
            LinkInfo(url=normalized, platform=detect_platform(normalized), host=get_host(normalized))
        )

    for match in _URL_RE.finditer(text):
        register(match.group(0))
    for raw in extra_urls:
        register(raw)

    result.cleaned_text = clean_text(_URL_RE.sub(" ", text))
    return result
