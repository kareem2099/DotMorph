"""English / Arabic user-interface text.

Source strings are English and double as keys; `tr()` returns the Arabic text when the
language is Arabic and falls back to English for anything not translated. Format names
(PNG, MP4, ...), commands and engine error messages stay English on purpose.
"""

from __future__ import annotations

import os

RTL_LANGUAGES = {"ar"}

AR: dict[str, str] = {
    # categories and tools
    "Image": "صور",
    "Video": "فيديو",
    "Audio": "صوت",
    "Docs": "مستندات",
    "Tools": "أدوات",
    "Compress": "ضغط",
    "Rotate": "تدوير",
    "Strip meta": "مسح البيانات",
    "Mute": "كتم الصوت",
    "Merge PDF": "دمج PDF",
    # the wheel
    "%1 options": "%1 اختيارات",
    "pick a format": "اختر الصيغة",
    "click to convert": "اضغط للتحويل",
    "converting": "جاري التحويل",
    "Cancel": "إلغاء",
    "click": "اضغط",
    "Drop files here": "اسحب الملفات هنا",
    "Drop it": "ارمها هنا",
    "Unsupported": "غير مدعوم",
    "No common format for these files": "لا توجد صيغة مشتركة لهذه الملفات",
    "%1 files": "%1 ملفات",
    "Done · %1 file(s)": "تم · %1 ملف",
    "%1 failed: %2": "فشل %1: %2",
    "Cancelled": "تم الإلغاء",
    "Cancelled · %1 file(s) kept": "تم الإلغاء · تم الاحتفاظ بـ %1 ملف",
    "no metadata": "بدون بيانات وصفية",
    # options panel
    "Options": "الخيارات",
    "Reset": "إعادة ضبط",
    "QUALITY  (JPG / WEBP / AVIF)": "الجودة  (JPG / WEBP / AVIF)",
    "RESOLUTION  (PDF / SVG)": "الدقة  (PDF / SVG)",
    "SIZE": "الحجم",
    "Auto": "تلقائي",
    "Original": "الأصلي",
    "Remove metadata": "مسح البيانات الوصفية",
    "EXIF, GPS, tags": "EXIF، GPS، الوسوم",
    "Done": "تم",
    "All settings…": "كل الإعدادات…",
    # notifications
    "Converted": "تم التحويل",
    "Converted %1 files": "تم تحويل %1 ملفات",
    "Conversion failed": "فشل التحويل",
    "%1 conversions failed": "فشل %1 تحويلات",
    "Converted %1 file(s), %2 failed": "تم تحويل %1 ملف، وفشل %2",
    " and %1 more": " و%1 غيرها",
    "Open folder": "فتح المجلد",
    # settings window: navigation
    "DotMorph Settings": "إعدادات DotMorph",
    "General": "عام",
    "Wheel": "الدائرة",
    "Shortcut": "الاختصار",
    "Integrations": "التكامل",
    "Watch folders": "مراقبة المجلدات",
    "About": "حول",
    # general
    "Appearance": "المظهر",
    "Theme": "السمة",
    "Dark": "داكن",
    "Light": "فاتح",
    "Glass": "زجاجي",
    "Reduce motion": "تقليل الحركة",
    "No animations in the wheel": "بدون حركة في الدائرة",
    "Language": "اللغة",
    "System": "النظام",
    "Notifications": "الإشعارات",
    "Long jobs": "المهام الطويلة",
    "Always": "دائمًا",
    "Never": "أبدًا",
    "When a conversion finishes": "عند انتهاء التحويل",
    "Save converted files": "حفظ الملفات المحوّلة",
    "Next to the original": "بجانب الأصلي",
    "In a folder": "في مجلد",
    "Choose folder…": "اختر مجلدًا…",
    "Default options": "الخيارات الافتراضية",
    "Quality": "الجودة",
    "Resolution (PDF / SVG)": "الدقة (PDF / SVG)",
    "Size": "الحجم",
    # wheel page
    "Your formats": "صيغك",
    "Click a format: once to pin it (shown first), twice to hide it, again to reset.": (
        "اضغط على صيغة: مرة لتثبيتها (تظهر أولًا)، ومرتين لإخفائها، ومرة أخرى للإرجاع."
    ),
    "Pinned": "مثبتة",
    "Hidden": "مخفية",
    "Clear": "مسح",
    # shortcut page
    "Global shortcut": "اختصار عام",
    "Opens the wheel with the files you copied in your file manager.": (
        "يفتح الدائرة بالملفات التي نسختها في مدير الملفات."
    ),
    "Current shortcut": "الاختصار الحالي",
    "Not set": "غير مضبوط",
    "Record a new shortcut": "سجّل اختصارًا جديدًا",
    "Press the keys now…": "اضغط الأزرار الآن…",
    "Use a modifier (Super, Ctrl, Alt) with a key.": "استخدم مفتاح تعديل مع زر: Super، Ctrl، Alt.",
    "Remove shortcut": "إزالة الاختصار",
    "Shortcut saved": "تم حفظ الاختصار",
    "Not supported on this desktop": "غير مدعوم على سطح المكتب هذا",
    # integrations page
    "Background daemon": "الخدمة في الخلفية",
    "Opens the wheel instantly and keeps the edge dock at login": (
        "تفتح الدائرة فورًا وتُبقي الشريط الجانبي بعد تسجيل الدخول"
    ),
    "Running": "تعمل",
    "Stopped": "متوقفة",
    "File manager menus": "قوائم مدير الملفات",
    "Right-click actions in Nautilus, Thunar, Dolphin and Nemo": (
        "أوامر الزر الأيمن في Nautilus، Thunar، Dolphin، Nemo"
    ),
    "Quick actions in the menu": "الأوامر السريعة في القائمة",
    "Edge dock": "الشريط الجانبي",
    "Docked on the left edge": "مثبت على الحافة اليسرى",
    "Docked on the right edge": "مثبت على الحافة اليمنى",
    "Not docked: drag the wheel to a screen edge": "غير مثبت: اسحب الدائرة إلى حافة الشاشة",
    "Undock": "إلغاء التثبيت",
    "Shell completion": "الإكمال التلقائي",
    "Install": "تثبيت",
    "Installed": "مثبت",
    # watch page
    "New files in these folders are converted automatically.": (
        "الملفات الجديدة في هذه المجلدات تتحول تلقائيًا."
    ),
    "No watched folders yet": "لا توجد مجلدات مراقبة بعد",
    "Add a folder": "أضف مجلدًا",
    "Folder": "المجلد",
    "Convert to": "حوّل إلى",
    "Only these formats (optional)": "هذه الصيغ فقط (اختياري)",
    "Start watching": "ابدأ المراقبة",
    "Remove": "إزالة",
    "Active": "نشط",
    "Inactive": "غير نشط",
    # tools page
    "Conversion engines": "محركات التحويل",
    "%1 of %2 conversions available": "%1 من %2 تحويل متاح",
    "Ready": "جاهز",
    "Missing": "ناقص",
    "Copy install command": "انسخ أمر التثبيت",
    "Copied": "تم النسخ",
    "Refresh": "تحديث",
    # about page
    "Radial-menu file converter for Linux": "محوّل ملفات لنظام لينكس بقائمة دائرية",
    "Version %1": "الإصدار %1",
    "Part of DotSuite": "جزء من DotSuite",
    "Website": "الموقع",
    "Changelog": "سجل التغييرات",
    "Source code": "الكود المصدري",
    "Settings file": "ملف الإعدادات",
    "Free and open source under Apache 2.0. No telemetry, nothing leaves your computer.": (
        "مجاني ومفتوح المصدر برخصة Apache 2.0. بدون تتبع، ولا شيء يغادر جهازك."
    ),
}

CATALOGS = {"en": {}, "ar": AR}

_current: str | None = None


def system_language() -> str:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "ar" if value.lower().startswith("ar") else "en"
    return "en"


def resolve(setting: str | None) -> str:
    """'auto' / 'en' / 'ar' -> 'en' or 'ar'."""
    if setting in CATALOGS:
        return setting
    return system_language()


def current() -> str:
    global _current
    if _current is None:
        from .settings import load

        _current = resolve(load().language)
    return _current


def set_language(setting: str | None) -> str:
    global _current
    _current = resolve(setting)
    return _current


def tr(text: str, *args: object) -> str:
    """Translate, then fill %1, %2, ... like Qt's arg()."""
    out = CATALOGS.get(current(), {}).get(text, text)
    for i, value in enumerate(args, start=1):
        out = out.replace(f"%{i}", str(value))
    return out


def is_rtl(lang: str | None = None) -> bool:
    return (lang or current()) in RTL_LANGUAGES
