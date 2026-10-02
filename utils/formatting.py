"""Rendering of messages (HTML parse mode — everything dynamic is escaped)."""
from __future__ import annotations

import html
from datetime import datetime, timezone, tzinfo
from typing import TYPE_CHECKING, Any, Iterable

from .. import texts
from ..database.models import Submission, SubmissionStatus, User
from ..schemas import MEDIA_PHOTO, MEDIA_VIDEO, StatsData
from .text import shorten

if TYPE_CHECKING:  # pragma: no cover
    from ..services.drafts import Draft

SEP = "━━━━━━━━━━━━━━"

_STATUS_LABELS = {
    SubmissionStatus.NEW.value: "🟡 جديدة",
    SubmissionStatus.REVIEWED.value: "✅ تمت المراجعة",
    SubmissionStatus.PUBLISHED.value: "📢 منشورة",
    SubmissionStatus.REJECTED.value: "❌ مرفوضة",
}
_STATUS_EMOJI = {
    SubmissionStatus.NEW.value: "🟡",
    SubmissionStatus.REVIEWED.value: "✅",
    SubmissionStatus.PUBLISHED.value: "📢",
    SubmissionStatus.REJECTED.value: "❌",
}


def status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status)


def status_emoji(status: str) -> str:
    return _STATUS_EMOJI.get(status, "•")


def format_dt(moment: datetime | None, tz: tzinfo) -> str:
    """Stored values are naive UTC; show them in the configured timezone."""
    if moment is None:
        return "—"
    return moment.replace(tzinfo=timezone.utc).astimezone(tz).strftime("%d/%m/%Y - %H:%M")


def describe_media(items: Iterable[Any]) -> str | None:
    photos = videos = 0
    for item in items:
        if item.media_type == MEDIA_PHOTO:
            photos += 1
        elif item.media_type == MEDIA_VIDEO:
            videos += 1
    parts: list[str] = []
    if photos:
        parts.append(f"{photos} صورة" if photos == 1 else f"{photos} صور")
    if videos:
        parts.append(f"{videos} فيديو" if videos == 1 else f"{videos} فيديوهات")
    return " + ".join(parts) or None


def user_mention(user: User) -> str:
    if user.username:
        return f"@{html.escape(user.username)}"
    name = " ".join(p for p in (user.first_name, user.last_name) if p) or "مستخدم"
    return f'<a href="tg://user?id={user.telegram_id}">{html.escape(name)}</a>'


def user_plain_label(user: User) -> str:
    """Plain (non-HTML) label for keyboard buttons."""
    if user.username:
        return f"@{user.username}"
    return shorten(user.first_name or "مستخدم", 18)


def _link_line(platform: str, url: str, *, linked: bool) -> str:
    shown = html.escape(shorten(url, 80))
    if linked:
        return f'• {html.escape(platform)}: <a href="{html.escape(url, quote=True)}">{shown}</a>'
    return f"🔗 {html.escape(platform)}: {shown}"


# ── معاينة المستخدم ──────────────────────────────────────
def render_preview(draft: "Draft") -> str:
    lines = ["📋 <b>معاينة المحتوى</b>", ""]
    if draft.text:
        escaped = html.escape(draft.text)
        lines.append(f"💬 النص:\n{escaped}" if "\n" in draft.text else f"💬 النص: {escaped}")
    for link in draft.urls:
        lines.append(_link_line(link.platform, link.url, linked=False))
    media = describe_media(draft.media)
    if media:
        lines.append(f"🖼 المرفقات: {media}")
    lines.append("")
    lines.append("➕ تقدر تضيف عناصر أكثر قبل التأكيد.")
    return "\n".join(lines)


# ── بطاقة الأدمن ─────────────────────────────────────────
def render_submission_card(
    sub: Submission,
    tz: tzinfo,
    *,
    position: tuple[int, int] | None = None,
    media_failed: bool = False,
) -> str:
    title = "📩 محتوى جديد" if sub.status == SubmissionStatus.NEW.value else "📩 محتوى"
    lines = [SEP, f"{title} #{sub.id}"]
    if position:
        lines.append(f"📍 {position[0]} من {position[1]}")
    lines += [
        f"👤 المستخدم: {user_mention(sub.user)}",
        f"🆔 ID: <code>{sub.user.telegram_id}</code>",
        f"🕐 التاريخ: {format_dt(sub.created_at, tz)}",
        "💬 النص:",
        html.escape(sub.text) if sub.text else "— بدون نص —",
    ]
    if sub.urls:
        lines.append("🔗 الروابط:")
        lines += [_link_line(u.platform, u.url, linked=True) for u in sub.urls]
    else:
        lines.append("🔗 الروابط: —")
    lines.append(f"🖼 المرفقات: {describe_media(sub.media) or '—'}")
    lines.append(f"📌 الحالة: {status_label(sub.status)}")
    if sub.reviewed_at is not None:
        by = f" (<code>{sub.reviewed_by}</code>)" if sub.reviewed_by else ""
        lines.append(f"🕓 آخر مراجعة: {format_dt(sub.reviewed_at, tz)}{by}")
    if media_failed:
        lines.append(texts.MEDIA_FAILED)
    lines.append(SEP)
    return "\n".join(lines)


def render_panel(new_count: int) -> str:
    return f"{texts.ADMIN_PANEL_TITLE}\n\n🆕 رسائل جديدة: {new_count}"


def render_list_header(page: int, pages: int, total: int) -> str:
    return f"📚 <b>الرسائل</b>\nصفحة {page} / {pages}\nالإجمالي: {total}"


def render_stats(stats: StatsData) -> str:
    return "\n".join(
        [
            "📊 <b>الإحصائيات</b>",
            "",
            f"👥 إجمالي المستخدمين: {stats.total_users}",
            f"📩 إجمالي Submissions: {stats.total_submissions}",
            f"🆕 الجديدة: {stats.new}",
            f"✅ تمت مراجعتها: {stats.reviewed}",
            f"❌ المرفوضة: {stats.rejected}",
            f"📢 المنشورة: {stats.published}",
            f"📅 Submissions اليوم: {stats.today}",
            f"📅 Submissions هذا الأسبوع (آخر 7 أيام): {stats.week}",
        ]
    )
