"""Inline keyboards."""
from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .database.models import Submission, SubmissionStatus
from .utils.formatting import status_emoji, user_plain_label


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── المستخدم ─────────────────────────────────────────────
def gate(channel_url: str) -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="📢 اشترك بالقناة", url=channel_url)],
            [_btn("✅ تحقق من الاشتراك", "sub:check")],
        ]
    )


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [[_btn("✍️ إرسال محتوى", "sub:new")]]
    if is_admin:
        rows.append([_btn("🛠 لوحة الإدارة", "adm:home")])
    return _markup(rows)


def cancel() -> InlineKeyboardMarkup:
    return _markup([[_btn("❌ إلغاء", "sub:cancel")]])


def preview() -> InlineKeyboardMarkup:
    return _markup([[_btn("✅ تأكيد وإرسال", "sub:confirm"), _btn("❌ إلغاء", "sub:cancel")]])


def after_submit() -> InlineKeyboardMarkup:
    return _markup([[_btn("✍️ إرسال محتوى جديد", "sub:new")]])


# ── الأدمن ───────────────────────────────────────────────
def admin_panel() -> InlineKeyboardMarkup:
    return _markup(
        [
            [_btn("📩 الرسائل الجديدة", "adm:new:0")],
            [_btn("📚 كل الرسائل", "adm:all:1")],
            [_btn("📊 الإحصائيات", "adm:stats")],
            [_btn("🔄 تحديث", "adm:refresh"), _btn("🔙 رجوع", "adm:exit")],
        ]
    )


def back_to_panel() -> InlineKeyboardMarkup:
    return _markup([[_btn("🔙 رجوع", "adm:home")]])


def stats_keyboard() -> InlineKeyboardMarkup:
    return _markup([[_btn("🔄 تحديث", "adm:stats"), _btn("🔙 رجوع", "adm:home")]])


def submission_actions(
    sub_id: int, status: str, ctx: str, *, has_prev: bool = False, has_next: bool = False
) -> InlineKeyboardMarkup:
    """ctx = 'n<offset>' (new-queue) or 'a<page>' (all-list); it tells the
    handlers where to return after an action."""
    kind, num = ctx[0], int(ctx[1:])
    actions: list[InlineKeyboardButton] = []
    if status != SubmissionStatus.REVIEWED.value:
        actions.append(_btn("✅ تمت المراجعة", f"adm:rev:{sub_id}:{ctx}"))
    if status != SubmissionStatus.REJECTED.value:
        actions.append(_btn("❌ رفض", f"adm:rej:{sub_id}:{ctx}"))
    actions.append(_btn("🗑 حذف", f"adm:del:{sub_id}:{ctx}"))

    rows: list[list[InlineKeyboardButton]] = [actions]
    if kind == "n":
        nav: list[InlineKeyboardButton] = []
        if has_prev:
            nav.append(_btn("◀️ السابق", f"adm:new:{num - 1}"))
        if has_next:
            nav.append(_btn("▶️ التالي", f"adm:new:{num + 1}"))
        if nav:
            rows.append(nav)
        rows.append([_btn("🔙 رجوع", "adm:home")])
    else:
        rows.append([_btn("🔙 رجوع", f"adm:all:{num}")])
    return _markup(rows)


def confirm_delete(sub_id: int, ctx: str) -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                _btn("🗑 نعم، احذف", f"adm:delok:{sub_id}:{ctx}"),
                _btn("❌ إلغاء", f"adm:view:{sub_id}:{ctx}"),
            ]
        ]
    )


def after_delete(ctx: str) -> InlineKeyboardMarkup:
    kind, num = ctx[0], int(ctx[1:])
    if kind == "n":
        return _markup([[_btn("▶️ متابعة", f"adm:new:{num}"), _btn("🔙 رجوع", "adm:home")]])
    return _markup([[_btn("🔙 رجوع", f"adm:all:{num}")]])


def submissions_list(subs: Sequence[Submission], page: int, pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for sub in subs:
        label = f"#{sub.id} {user_plain_label(sub.user)} {status_emoji(sub.status)} {sub.status}"
        rows.append([_btn(label, f"adm:view:{sub.id}:a{page}")])

    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(_btn("◀️", f"adm:all:{page - 1}"))
    nav.append(_btn(f"{page}/{pages}", "adm:noop"))
    if page < pages:
        nav.append(_btn("▶️", f"adm:all:{page + 1}"))
    rows.append(nav)
    rows.append([_btn("🔙 رجوع", "adm:home")])
    return _markup(rows)
