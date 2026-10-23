"""The menu window: Qt app + bridge + QML engine, shared by one-shot runs and the daemon."""

from __future__ import annotations

import os
import sys
from pathlib import Path

QML_MAIN = Path(__file__).parent / "qml" / "main.qml"


def prepare_platform() -> None:
    """The menu must open where we want and stay on top: X11 (or XWayland) can do that."""
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    # Qt asks the desktop portal for an app id; under XWayland that harmlessly fails with
    # "Failed to register with host portal". Keep the terminal quiet.
    rules = os.environ.get("QT_LOGGING_RULES", "")
    if "qt.qpa.services" not in rules:
        os.environ["QT_LOGGING_RULES"] = ";".join(filter(None, [rules, "qt.qpa.services=false"]))


class Menu:
    def __init__(
        self,
        files: list[str],
        *,
        theme: str | None = None,
        reduce_motion: bool | None = None,
        persistent: bool = False,
    ) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuick import QQuickWindow  # noqa: F401  (root wraps as QQuickWindow)

        from .bridge import Bridge
        from .dock import Dock
        from .i18n_qt import I18n

        self.app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        self.app.setApplicationName("DotMorph")
        self.app.setOrganizationName("DotSuite")
        self.app.setDesktopFileName("dotmorph")
        self.app.setWindowIcon(QIcon(str(Path(__file__).parent / "icons" / "dotmorph.svg")))
        self.app.setQuitOnLastWindowClosed(not persistent)

        self.bridge = Bridge(files, theme=theme, reduce_motion=reduce_motion,
                             persistent=persistent)
        self.app.aboutToQuit.connect(self.bridge.cancel)
        self.dock = Dock(self.bridge)
        self.i18n = I18n(self.bridge.settings.language)
        self.i18n.changed.connect(self.bridge.relabel)
        self.engine = QQmlApplicationEngine()
        self.engine.rootContext().setContextProperty("bridge", self.bridge)
        self.engine.rootContext().setContextProperty("dock", self.dock)
        self.engine.rootContext().setContextProperty("i18n", self.i18n)
        self.engine.load(QUrl.fromLocalFile(str(QML_MAIN)))
        if not self.engine.rootObjects():
            raise RuntimeError("could not load the QML menu")
        self.window = self.engine.rootObjects()[0]
        self.dock.attach(self.window)
        self.dock.dismissed.connect(self._dismiss)

    def _dismiss(self) -> None:
        if self.bridge.persistent:
            self.window.hide()
            self.bridge.menuHidden()
        else:
            self.app.quit()

    def start_docked(self) -> bool:
        """Daemon start: show the edge tab right away if the wheel lives on an edge."""
        if not self.dock.restore(open_wheel=False):
            return False
        self.window.show()
        self.bridge.menuShown()
        return True

    def place(self) -> None:
        """Open in the saved edge dock, else centre on the pointer (X11) or on the screen
        (Wayland: the pointer position is unknown)."""
        from PySide6.QtGui import QCursor

        if self.dock.restore(open_wheel=True):
            return

        win = self.window
        pos = QCursor.pos()
        screen = self.app.screenAt(pos) or self.app.primaryScreen()
        area = screen.availableGeometry()
        wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland"
        if wayland or (pos.x() == 0 and pos.y() == 0):
            x = area.left() + (area.width() - win.width()) // 2
            y = area.top() + (area.height() - win.height()) // 2
        else:
            x = min(max(pos.x() - win.width() // 2, area.left()), area.right() - win.width())
            y = min(max(pos.y() - win.height() // 2, area.top()), area.bottom() - win.height())
        win.setX(x)
        win.setY(y)

    def summon(self, files: list[str], theme: str | None = None,
               reduce_motion: bool | None = None) -> None:
        """Daemon: load new files and pop the (hidden) menu up again."""
        self.i18n.setLanguage(_saved_language())  # the settings window may have changed it
        if self.dock.docked:
            self.dock.peek()  # open the half wheel out of the edge
            if not self.window.isVisible():
                self.window.show()
            self.bridge.summon(files, theme, reduce_motion)
            return
        self.place()
        self.bridge.summon(files, theme, reduce_motion)

    def reload(self) -> None:
        """Daemon: the settings window saved something; apply it now."""
        self.bridge.reload_settings()
        self.i18n.setLanguage(self.bridge.settings.language)
        if not self.bridge.settings.dock_side and self.dock.docked:
            self.dock.forget()
        elif self.bridge.settings.dock_side and not self.dock.docked:
            self.start_docked()

    def shutdown(self) -> None:
        import shiboken6
        from PySide6.QtCore import QThreadPool

        # Stop any running job, then tear QML down while `bridge` still exists.
        self.bridge.cancel()
        QThreadPool.globalInstance().waitForDone(5000)
        for obj in self.engine.rootObjects():
            shiboken6.delete(obj)
        del self.engine


def _saved_language() -> str:
    from ..settings import load

    return load().language


def run_once(files: list[str], *, theme: str | None, reduce_motion: bool | None) -> int:
    prepare_platform()
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print("The GUI needs PySide6:  pip install 'dotmorph[gui]'", file=sys.stderr)
        return 2
    try:
        menu = Menu(files, theme=theme, reduce_motion=reduce_motion)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    menu.place()
    menu.window.requestActivate()
    code = menu.app.exec()
    menu.shutdown()
    return code
