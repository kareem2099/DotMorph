"""Phase 4: saved settings, English/Arabic, the settings window and its backend."""

import os

import pytest
from conftest import make_png

from dotmorph import i18n, settings
from dotmorph.linux import notify

# ---- settings and i18n (no Qt) --------------------------------------------------------


def test_new_settings_are_cleaned_and_arranged():
    s = settings.Settings(theme="neon", language="xx", notify="loud", quality=0,
                          pinned=["WEBP", "webp", "mp4"], hidden=["ico", "mp4"]).clean()
    assert (s.theme, s.language, s.notify, s.quality) == ("dark", "auto", "long", 1)
    assert s.pinned == ["webp", "mp4"] and s.hidden == ["ico"]  # pinned wins over hidden
    assert s.arrange(["png", "ico", "mp4", "webp", "gif"]) == ["webp", "mp4", "png", "gif"]


def test_output_folder_goes_into_options(tmp_path):
    s = settings.Settings(output_dir=str(tmp_path / "out"))
    assert s.options().out_dir == tmp_path / "out"
    assert settings.Settings().options().out_dir is None


def test_translations_and_language_detection(monkeypatch):
    assert i18n.resolve("ar") == "ar" and i18n.resolve("en") == "en"
    monkeypatch.setenv("LANGUAGE", "ar_EG.UTF-8")
    assert i18n.resolve("auto") == "ar"
    i18n.set_language("ar")
    assert i18n.tr("Compress") == "ضغط"
    assert i18n.trn("Done · %1 files", 3) == "تم · 3 ملفات"
    assert i18n.tr("Something not translated") == "Something not translated"
    assert i18n.is_rtl()
    assert notify.message([], ["x: boom"])[0] == "فشل التحويل"
    i18n.set_language("en")
    assert i18n.tr("Compress") == "Compress" and not i18n.is_rtl()


# ---- Qt: wheel follows the settings --------------------------------------------------

pytest.importorskip("PySide6.QtQuick")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402, F401


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_bridge_uses_saved_theme_formats_and_language(app, tmp_path):
    from dotmorph.ui.bridge import Bridge

    settings.save(settings.Settings(theme="glass", language="ar", pinned=["webp"], hidden=["gif"]))
    i18n.set_language("ar")
    bridge = Bridge([str(make_png(tmp_path / "a.png"))])
    ids = [s["id"] for s in bridge.sectors]
    assert ids[0] == "webp" and "gif" not in ids
    assert bridge.theme == "glass"
    assert next(s for s in bridge.sectors if s["id"] == "compress")["label"] == "ضغط"
    assert Bridge([], theme="light").theme == "light"  # --theme still wins


def test_settings_backend_saves_and_switches_language(app, tmp_path, monkeypatch):
    from dotmorph.linux import hotkey, watch
    from dotmorph.ui.i18n_qt import I18n
    from dotmorph.ui.settings_window import SettingsBackend

    monkeypatch.setattr(watch.shutil, "which", lambda name: None)  # no real systemctl
    i18n_obj = I18n("en")
    backend = SettingsBackend(i18n_obj)
    backend.set("theme", "light")
    backend.set("quality", 70)
    backend.set("language", "ar")
    saved = settings.load()
    assert (saved.theme, saved.quality, saved.language) == ("light", 70, "ar")
    assert i18n_obj.rtl and i18n_obj.strings["Compress"] == "ضغط"

    backend.cycleFormat("webp")
    assert settings.load().pinned == ["webp"]
    backend.cycleFormat("webp")
    assert settings.load().hidden == ["webp"] and settings.load().pinned == []
    backend.cycleFormat("webp")
    assert settings.load().hidden == []
    states = {f["id"]: f["state"] for f in backend.formats}
    assert "png" in states and "merge-pdf" in states

    folder = tmp_path / "Downloads"
    folder.mkdir()
    assert backend.addWatch(str(folder), "webp", "png, jpg") == ""
    assert [w["desc"] for w in backend.watchServices][0].endswith("to webp")
    assert "cannot convert" in backend.addWatch(str(folder), "webp", "mp3")
    backend.removeWatch(backend.watchServices[0]["name"])
    assert backend.watchServices == []

    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
    backend.refresh()
    assert not backend.hotkeySupported
    assert "--clipboard" in backend.setHotkey("<Super>m")
    assert isinstance(hotkey.desktop(), str)
    assert any(b["name"] == "pillow" and b["ready"] for b in backend.backends)
    i18n.set_language("en")


def test_settings_window_loads_every_page_in_every_language(app):
    from dotmorph.ui.i18n_qt import I18n
    from dotmorph.ui.settings_window import QML, SettingsBackend

    for lang in i18n.LANGUAGES:
        settings.save(settings.Settings(language=lang))
        i18n_obj = I18n(lang)
        backend = SettingsBackend(i18n_obj)
        engine = QQmlApplicationEngine()
        warnings: list[str] = []
        engine.warnings.connect(lambda ws, out=warnings: out.extend(w.toString() for w in ws))
        engine.rootContext().setContextProperty("i18n", i18n_obj)
        engine.rootContext().setContextProperty("backend", backend)
        engine.load(QUrl.fromLocalFile(str(QML)))
        win = engine.rootObjects()[0]
        assert win.property("title") == i18n.tr("DotMorph Settings")
        for page in range(7):
            win.setProperty("page", page)
            wait(40)
        assert not warnings, warnings
        import shiboken6

        shiboken6.delete(win)
    i18n.set_language("en")


def test_integration_installs_settings_launcher_and_png_icons(tmp_path):
    from dotmorph.linux import integrate

    written = integrate.install()
    names = {p.name for p in written}
    assert "dotmorph-settings.desktop" in names
    entry = next(p for p in written if p.name == "dotmorph.desktop").read_text()
    assert "Actions=settings;" in entry and "[Desktop Action settings]" in entry
    pngs = [p for p in written if p.suffix == ".png"]
    from dotmorph.core.backends.svg import SvgBackend

    if SvgBackend().available():
        assert len(pngs) == len(integrate.PNG_SIZES)
    integrate.remove()
    assert not any(p.exists() for p in written if p.name != "uca.xml")


def _items(item, name):
    """Visual descendants called `name` (Repeater delegates aren't QObject children)."""
    for child in item.childItems():
        if child.objectName() == name:
            yield child
        yield from _items(child, name)


def _wheel_labels(lang, files):
    """Load the real wheel in `lang` and open every category: (label, size, width, room)."""
    from PySide6.QtQuick import QQuickItem

    from dotmorph.ui.bridge import Bridge
    from dotmorph.ui.dock import Dock
    from dotmorph.ui.i18n_qt import I18n
    from dotmorph.ui.window import QML_MAIN

    settings.save(settings.Settings(language=lang, reduce_motion=True))
    i18n_obj = I18n(lang)
    bridge = Bridge([str(f) for f in files])
    dock = Dock(bridge)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("dock", dock)
    engine.rootContext().setContextProperty("i18n", i18n_obj)
    engine.load(QUrl.fromLocalFile(str(QML_MAIN)))
    root = engine.rootObjects()[0]
    wheel = root.findChild(QQuickItem, "wheel")
    seen = []
    for cat in range(-1, len(wheel.property("cats").toVariant() or [])):
        wheel.setProperty("openCat", cat)
        wait(30)
        for sector in _items(wheel, "ringSector"):
            room = sector.property("labelRoom")
            for name in ("sectorLabel", "sectorSub"):
                text = next(_items(sector, name), None)
                if text is not None and text.property("text"):
                    seen.append((text.property("text"), text.property("font").pixelSize(),
                                 text.property("implicitWidth"), room))
    import shiboken6

    shiboken6.delete(root)
    return seen


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_wheel_labels_fit_their_sectors(app, tmp_path, lang):
    """Long translations ("Komprimieren", "Объединить PDF") shrink instead of overlapping."""
    from PIL import Image

    pdfs = [tmp_path / "a.pdf", tmp_path / "b.pdf"]  # two PDFs: "Merge PDF" in the wheel
    for pdf in pdfs:
        Image.new("RGB", (80, 80), "white").save(pdf)
    seen = _wheel_labels(lang, [make_png(tmp_path / "a.png")]) + _wheel_labels(lang, pdfs)
    assert any(size for _, size, _, _ in seen)
    for text, size, width, room in seen:
        assert width <= room + 2, (lang, text, width, room)
        assert size >= 9, (lang, text, size)  # shrunk, but still readable
    i18n.set_language("en")
