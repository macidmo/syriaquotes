"""All user-facing Arabic strings live here (easy to edit / translate)."""
from __future__ import annotations

SUPPORTED_PLATFORMS = "Facebook, Instagram, TikTok, YouTube, Threads, X"

# ── الاشتراك الإجباري ─────────────────────────────────────
GATE_TEXT = "🔒 حتى تقدر تستخدم البوت، لازم تشترك بالقناة أولاً."
NOT_SUBSCRIBED = "❌ لسا ما اشتركت بالقناة.\nاشترك أولاً ثم اضغط تحقق من الاشتراك."
VERIFIED = "✅ تم التحقق من اشتراكك."

# ── عام ──────────────────────────────────────────────────
UNKNOWN_MESSAGE = "🤔 ما فهمت رسالتك.\nاضغط على الزر تحت لإرسال محتوى، أو اكتب /start."
STALE_BUTTON = "⚠️ هذا الزر لم يعد صالحاً. اكتب /start للبدء من جديد."
UNEXPECTED_ERROR = "⚠️ صار خطأ غير متوقع. جرب مرة ثانية."
HELP_FOOTER = "لإلغاء أي عملية إرسال اكتب /cancel"


def welcome(max_text_length: int) -> str:
    return (
        "👋 أهلاً فيك!\n"
        "ابعت فكرتك أو المحتوى يلي بدك تشاركه.\n\n"
        f"📝 النص: حتى {max_text_length} حرف\n"
        "🖼 الصور: مدعومة\n"
        "🎥 الفيديوهات: مدعومة\n"
        f"🔗 الروابط: {SUPPORTED_PLATFORMS}"
    )


# ── إرسال المحتوى ────────────────────────────────────────
def submission_prompt(max_text_length: int, max_media: int) -> str:
    return (
        "✍️ ابعت محتواك هلق:\n\n"
        f"📝 نص (حتى {max_text_length} حرف)\n"
        f"🖼 صور / 🎥 فيديوهات (حتى {max_media} ملفات)\n"
        f"🔗 روابط: {SUPPORTED_PLATFORMS}\n\n"
        "بتقدر تبعت كل شي برسائل متتالية أو كألبوم، وبعدها رح تظهرلك معاينة للتأكيد."
    )


def text_too_long(max_len: int) -> str:
    return f"❌ النص طويل جداً.\nالحد الأقصى هو {max_len} حرف."


def too_many_media(limit: int) -> str:
    return f"❌ لا يمكنك إرسال أكثر من {limit} ملفات ضمن نفس المحتوى."


def too_many_urls(limit: int) -> str:
    return f"❌ لا يمكنك إرسال أكثر من {limit} روابط ضمن نفس المحتوى."


def unsupported_links(hosts: list[str]) -> str:
    listed = "\n".join(f"• {h}" for h in hosts)
    return (
        "⚠️ في روابط من منصات غير مدعومة ولم يتم حفظها:\n"
        f"{listed}\n\n"
        f"المنصات المدعومة: {SUPPORTED_PLATFORMS}"
    )


INVALID_URL = "⚠️ في رابط غير صحيح تم تجاهله."
IMAGE_TOO_BIG = "❌ حجم الصورة أكبر من الحد المسموح."
VIDEO_TOO_BIG = "❌ حجم الفيديو أكبر من الحد المسموح."
VIDEO_FORMAT = "❌ صيغة الفيديو غير مدعومة.\nالمسموح: MP4 و MOV."
UNSUPPORTED_CONTENT = (
    "❌ نوع الملف غير مدعوم.\n"
    "المسموح: صور (JPEG, PNG, WEBP) وفيديوهات (MP4, MOV)، "
    "أرسلها كصورة أو فيديو عادي وليس كملف."
)
EMPTY_SUBMISSION = "❌ ما أرسلت أي محتوى.\nابعت نص أو صورة أو فيديو أو رابط أولاً."
COOLDOWN = "⏳ استنى شوي قبل إرسال محتوى جديد."
SESSION_EXPIRED = "⌛ انتهت جلسة الإرسال. اضغط «إرسال محتوى» للبدء من جديد."
SAVE_FAILED = "❌ صار خطأ أثناء حفظ المحتوى. جرب مرة ثانية بعد شوي."
CANCELLED = "❌ تم إلغاء عملية الإرسال."
NOTHING_TO_CANCEL = "ℹ️ ما في عملية إرسال حالياً."
SUCCESS = (
    "✅ تم استلام محتواك بنجاح!\n"
    "شكراً لمشاركتك ❤️\n"
    "سيتم مراجعة المحتوى من قبل الإدارة."
)

# ── الإدارة ──────────────────────────────────────────────
ADMIN_DENIED = "⛔ غير مصرح لك."
ADMIN_PANEL_TITLE = "🛠 <b>لوحة الإدارة</b>"
NO_NEW = "📭 ما في رسائل جديدة."
NO_SUBMISSIONS = "📭 ما في رسائل بعد."
NOT_FOUND = "⚠️ هذه الرسالة غير موجودة (ربما تم حذفها)."
MESSAGE_UNAVAILABLE = "⚠️ الرسالة لم تعد متاحة، افتح /admin من جديد."
DELETE_CONFIRM = "⚠️ هل أنت متأكد من حذف هذه الرسالة؟"
DELETED = "✅ تم حذف المحتوى."
REVIEWED_TOAST = "✅ تمت المراجعة"
REJECTED_TOAST = "❌ تم الرفض"
MEDIA_FAILED = "⚠️ تعذر عرض بعض المرفقات."
