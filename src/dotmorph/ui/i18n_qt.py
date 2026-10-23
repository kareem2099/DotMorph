"""The `i18n` object QML reads: translated strings, right-to-left, and the app font."""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot
from PySide6.QtGui import QFontDatabase, QGuiApplication

from .. import i18n

ARABIC_FONTS = ("Noto Kufi Arabic", "Noto Sans Arabic", "Noto Naskh Arabic UI", "Cairo")
_base_family: str | None = None  # the app font before any Arabic font was put in front


def apply_to_app(lang: str) -> None:
    """Layout direction and a proper Arabic font (DejaVu's Arabic glyphs look rough)."""
    app = QGuiApplication.instance()
    if app is None:
        return
    rtl = i18n.is_rtl(lang)
    direction = Qt.LayoutDirection
    app.setLayoutDirection(direction.RightToLeft if rtl else direction.LeftToRight)
    global _base_family
    font = app.font()
    if _base_family is None:
        _base_family = font.family()
    families = [_base_family]
    if rtl:
        installed = set(QFontDatabase.families())
        arabic = next((f for f in ARABIC_FONTS if f in installed), None)
        if arabic:
            families.insert(0, arabic)
    font.setFamilies(families)
    app.setFont(font)


class I18n(QObject):
    changed = Signal()

    def __init__(self, setting: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lang = i18n.set_language(setting) if setting else i18n.current()
        apply_to_app(self._lang)

    @Property("QVariantMap", notify=changed)
    def strings(self) -> dict[str, str]:
        return dict(i18n.CATALOGS.get(self._lang, {}))

    @Property(bool, notify=changed)
    def rtl(self) -> bool:
        return i18n.is_rtl(self._lang)

    @Property(str, notify=changed)
    def lang(self) -> str:
        return self._lang

    @Slot(str)
    def setLanguage(self, setting: str) -> None:
        lang = i18n.set_language(setting)
        if lang != self._lang:
            self._lang = lang
            apply_to_app(lang)
            self.changed.emit()
