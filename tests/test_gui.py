"""Load the real QML menu offscreen and drive it: catches QML errors and wiring bugs."""

import os

import pytest
from conftest import make_png, make_video, needs

pytest.importorskip("PySide6.QtQuick")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickItem, QQuickWindow  # noqa: E402, F401
from PySide6.QtTest import QTest  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture
def menu(app):
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    from dotmorph.ui.window import Menu

    made = []
    warnings = []

    def handler(kind, _context, text):
        if kind != QtMsgType.QtDebugMsg and "qml" in text.lower():
            warnings.append(text)

    previous = qInstallMessageHandler(handler)

    def load(files, **kw):
        m = Menu([str(f) for f in files], reduce_motion=True, **kw)
        made.append(m)
        wheel = m.window.findChild(QQuickItem, "wheel")
        wait(150)
        return m.bridge, m.window, wheel, warnings

    yield load
    qInstallMessageHandler(previous)
    for m in made:
        m.bridge.cancel()
        import shiboken6

        for obj in m.engine.rootObjects():
            shiboken6.delete(obj)


def prop(item, name):
    """Read a QML property, unwrapping JS arrays/objects into Python lists/dicts."""
    value = item.property(name)
    return value.toVariant() if hasattr(value, "toVariant") else value


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_image_menu_has_category_ring_and_keyboard(menu, tmp_path):
    bridge, win, wheel, warnings = menu([make_png(tmp_path / "a.png")])
    assert [c["id"] for c in prop(wheel, "cats")] == ["image", "document", "tools"]
    assert prop(wheel, "flat") is False

    QTest.keyClick(win, Qt.Key_Right)  # select first category: Image
    wait(50)
    assert prop(wheel, "openCat") == 0
    QTest.keyClick(win, Qt.Key_Return)  # into its fan
    QTest.keyClick(win, Qt.Key_Right)
    wait(50)
    assert prop(wheel, "hoverOuter") == 1
    assert prop(wheel, "hoveredTarget")["id"] == "webp"
    assert not warnings


def test_few_targets_use_a_flat_ring(menu, tmp_path):
    pdf = tmp_path / "doc.pdf"
    from conftest import make_pdf

    make_pdf(pdf)
    bridge, win, wheel, warnings = menu([pdf])
    if len(bridge.sectors) > 6:
        pytest.skip("more PDF tools installed than expected")
    assert prop(wheel, "flat") is True
    assert not warnings


def test_convert_from_keyboard_shows_done(menu, tmp_path):
    bridge, win, wheel, warnings = menu([make_png(tmp_path / "a.png")])
    results = []
    bridge.finished.connect(results.append)
    QTest.keyClick(win, Qt.Key_1)  # Image
    QTest.keyClick(win, Qt.Key_2)  # second target in the fan: WEBP
    for _ in range(200):  # up to 10 s for the conversion on a slow runner
        if results:
            break
        wait(50)
    assert results == [True]
    assert (tmp_path / "a.webp").exists()
    wait(50)
    assert prop(wheel, "phase") == "done"
    assert not warnings


@needs("ffmpeg")
def test_video_menu_shortcut_category_and_theme(menu, tmp_path):
    bridge, win, wheel, warnings = menu([make_video(tmp_path / "c.mp4")], theme="glass")
    cats = {c["id"]: len(c["items"]) for c in prop(wheel, "cats")}
    assert cats["image"] == 1  # GIF only: shown as a direct shortcut
    index = [c["id"] for c in prop(wheel, "cats")].index("image")
    wheel.setProperty("hoverInner", index)
    wait(30)
    assert prop(wheel, "hoveredTarget")["id"] == "gif"
    assert prop(wheel, "fanItems") == []
    assert not warnings


def test_dragging_moves_the_window_and_never_converts(menu, tmp_path):
    from PySide6.QtCore import QPoint

    bridge, win, wheel, warnings = menu([make_png(tmp_path / "a.png")])
    start = (win.x(), win.y())
    c = 280
    QTest.mousePress(win, Qt.LeftButton, Qt.NoModifier, QPoint(c, c - 110))  # on a sector
    QTest.mouseMove(win, QPoint(c + 40, c - 80))
    QTest.mouseRelease(win, Qt.LeftButton, Qt.NoModifier, QPoint(c + 40, c - 80))
    wait(100)
    assert (win.x(), win.y()) != start
    assert not bridge.busy and win.isVisible()
    assert list(tmp_path.iterdir()) == [tmp_path / "a.png"]  # nothing converted
    assert not warnings


def test_options_panel_applies_to_conversions(menu, tmp_path):
    from PIL import Image

    bridge, win, wheel, warnings = menu([make_png(tmp_path / "a.png", size=(40, 20))])
    QTest.keyClick(win, Qt.Key_O)
    wait(50)
    assert prop(wheel, "optionsOpen") is True
    bridge.setOption("resize", "50%")
    bridge.setOption("quality", 60)
    assert bridge.optionsSummary == "Q60 \u00b7 50%"
    QTest.keyClick(win, Qt.Key_Escape)  # closes the panel, not the window
    wait(50)
    assert prop(wheel, "optionsOpen") is False and win.isVisible()

    results = []
    bridge.finished.connect(results.append)
    bridge.convertTo("webp")
    for _ in range(200):  # up to 10 s for the conversion on a slow runner
        if results:
            break
        wait(50)
    with Image.open(tmp_path / "a.webp") as im:
        assert im.size == (20, 10)
    from dotmorph import settings

    assert settings.load().resize == "50%"  # remembered for next time
    assert not warnings


def test_held_hotkey_does_not_restart_the_open_animation(app, tmp_path):
    """A held Super+Shift+M repeats every ~30 ms; each repeat used to re-open the wheel."""
    import shiboken6

    from dotmorph.ui.window import Menu

    a = make_png(tmp_path / "a.png")
    menu = Menu([], persistent=True, reduce_motion=True)
    shown = []
    menu.bridge.summoned.connect(lambda: shown.append(1))
    try:
        assert menu.bridge.summon([str(a)]) is True
        for _ in range(10):  # key repeat
            assert menu.bridge.summon([str(a)]) is False
        assert len(shown) == 1
        menu.bridge._last_summon = 0  # later, with other files, while still open:
        b = make_png(tmp_path / "b.png")
        assert menu.bridge.summon([str(b)]) is True
        assert len(shown) == 1 and menu.bridge.fileLabel == "b.png"  # updated, not re-opened
        menu.bridge.menuHidden()
        menu.bridge._last_summon = 0
        assert menu.bridge.summon([str(b)]) is True and len(shown) == 2  # hidden: opens again
    finally:
        menu.bridge.cancel()
        for obj in menu.engine.rootObjects():
            shiboken6.delete(obj)


# ---- edge dock ------------------------------------------------------------------------


def test_wheel_touching_an_edge_docks_and_peeks(app, tmp_path):
    import shiboken6

    from dotmorph import settings
    from dotmorph.ui.dock import PEEK_W, TAB_W, WHEEL_R
    from dotmorph.ui.window import Menu

    m = Menu([str(make_png(tmp_path / "a.png"))], reduce_motion=True)
    try:
        m.place()
        area = m.window.screen().availableGeometry()
        m.window.setX(area.left() + 100)  # disc well inside the screen: stays free
        m.dock.dragEnded()
        assert m.dock.mode == "free"

        m.window.setX(area.left() - (m.window.width() // 2 - WHEEL_R))  # disc touches left
        m.dock.dragEnded()
        assert m.dock.mode == "docked" and m.dock.side == "left"
        assert m.window.width() == TAB_W and m.window.x() == area.left()
        assert settings.load().dock_side == "left"

        m.dock.peek()
        wait(30)
        wheel = m.window.findChild(QQuickItem, "wheel")
        assert m.dock.mode == "peek" and m.window.width() == PEEK_W
        assert prop(wheel, "half") is True

        m.dock.collapse()
        y_tab = m.window.y()
        m.dock.slide(40)
        m.dock.slideEnded()
        assert m.window.y() == y_tab + 40  # moved down along the edge
        assert settings.load().dock_y > 0.5

        m.dock.undock()
        assert m.dock.mode == "free" and m.window.width() == 560
        assert settings.load().dock_side == ""
    finally:
        m.bridge.cancel()
        for obj in m.engine.rootObjects():
            shiboken6.delete(obj)


def test_saved_dock_is_restored_and_escape_folds_instead_of_quitting(app, tmp_path):
    import shiboken6

    from dotmorph import settings
    from dotmorph.ui.window import Menu

    s = settings.load()
    s.dock_side, s.dock_y = "right", 0.5
    settings.save(s)
    m = Menu([str(make_png(tmp_path / "a.png"))], reduce_motion=True)
    try:
        m.place()  # opening with files: the half wheel out of the right edge
        wait(50)
        area = m.window.screen().availableGeometry()
        assert m.dock.mode == "peek"
        assert m.window.x() + m.window.width() - 1 == area.right()
        wheel = m.window.findChild(QQuickItem, "wheel")
        assert prop(wheel, "mirrored") is True
        QTest.keyClick(m.window, Qt.Key_Escape)
        wait(100)
        assert m.dock.mode == "docked" and m.window.isVisible()
        m.bridge.resetOptions()  # resetting conversion options keeps the dock
        assert settings.load().dock_side == "right"
    finally:
        m.bridge.cancel()
        for obj in m.engine.rootObjects():
            shiboken6.delete(obj)


def test_half_wheel_hit_testing_on_both_sides(app, tmp_path):
    import math

    import shiboken6

    from dotmorph import settings
    from dotmorph.ui.window import Menu

    for side in ("left", "right"):
        s = settings.load()
        s.dock_side = side
        settings.save(s)
        m = Menu([str(make_png(tmp_path / "a.png"))], reduce_motion=True)
        try:
            m.place()
            wait(50)
            wheel = m.window.findChild(QQuickItem, "wheel")
            cx, cy = prop(wheel, "cx"), prop(wheel, "cy")
            # a point in the inner ring near the top of the open half -> the first item
            angle = math.radians(20 if side == "left" else 340)
            x, y = cx + 110 * math.sin(angle), cy - 110 * math.cos(angle)
            from PySide6.QtCore import QPoint

            QTest.mouseMove(m.window, QPoint(int(x), int(y)))
            wait(30)
            assert prop(wheel, "hoverInner") == 0, side
            # the closed half (behind the screen edge) is never hit
            back = math.radians(270 if side == "left" else 90)
            QTest.mouseMove(m.window, QPoint(int(cx + 110 * math.sin(back)),
                                             int(cy - 110 * math.cos(back))))
            wait(30)
            assert prop(wheel, "hoverInner") == -1
        finally:
            m.bridge.cancel()
            for obj in m.engine.rootObjects():
                shiboken6.delete(obj)
