"""`dotmorph settings`: the settings window and the Python side of it.

Every change is saved to settings.json right away and the running daemon is asked to
reload, so the wheel follows along (theme, language, formats, dock) without a restart.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from .. import __version__, settings
from ..core import registry
from ..core.formats import TOOLS, category_of, label_of
from ..i18n import tr

QML = Path(__file__).parent / "qml" / "SettingsWindow.qml"

# QML name -> settings field
FIELDS = {
    "theme": "theme",
    "reduceMotion": "reduce_motion",
    "language": "language",
    "notify": "notify",
    "outputDir": "output_dir",
    "quality": "quality",
    "dpi": "dpi",
    "resize": "resize",
    "strip": "strip",
    "quickActions": "quick_actions",
}


def _ping_daemon() -> None:
    from ..linux import ipc

    ipc.request({"cmd": "reload"}, timeout=0.5)


class SettingsBackend(QObject):
    changed = Signal()
    statusChanged = Signal()

    def __init__(self, i18n=None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._i18n = i18n
        self._s = settings.load()
        self._status: dict = {}
        if i18n is not None:
            i18n.changed.connect(self.changed)  # translated labels
        self.refresh()

    def _save(self) -> None:
        settings.save(self._s)
        self._s = settings.load()
        self.changed.emit()
        _ping_daemon()

    # ---- settings values ----------------------------------------------------------------
    def _get(name):  # noqa: N805  (property factory)
        return lambda self: getattr(self._s, FIELDS[name])

    theme = Property(str, _get("theme"), notify=changed)
    reduceMotion = Property(bool, _get("reduceMotion"), notify=changed)
    language = Property(str, _get("language"), notify=changed)
    notify = Property(str, _get("notify"), notify=changed)
    outputDir = Property(str, _get("outputDir"), notify=changed)
    quality = Property(int, _get("quality"), notify=changed)
    dpi = Property(int, _get("dpi"), notify=changed)
    resize = Property(str, _get("resize"), notify=changed)
    strip = Property(bool, _get("strip"), notify=changed)
    quickActions = Property("QVariantList", _get("quickActions"), notify=changed)
    del _get

    @Slot(str, "QVariant")
    def set(self, name: str, value) -> None:
        field = FIELDS.get(name)
        if field is None:
            return
        if hasattr(value, "toVariant"):
            value = value.toVariant()
        if field == "output_dir" and isinstance(value, str) and value.startswith("file://"):
            from PySide6.QtCore import QUrl

            value = QUrl(value).toLocalFile()
        setattr(self._s, field, value)
        self._save()
        if field == "language" and self._i18n is not None:
            self._i18n.setLanguage(self._s.language)
        if field == "quick_actions" and self._status.get("menus"):
            from ..linux import integrate

            integrate.install()

    # ---- the wheel's formats: pinned / hidden ----------------------------------------------
    @Property("QVariantList", notify=changed)
    def formats(self) -> list[dict]:
        from ..completions import _targets

        out = []
        for target in _targets():
            state = ("pinned" if target in self._s.pinned
                     else "hidden" if target in self._s.hidden else "")
            out.append({"id": target, "label": tr(label_of(target)),
                        "category": category_of(target), "state": state})
        return out

    @Slot(str)
    def cycleFormat(self, target: str) -> None:
        """normal -> pinned -> hidden -> normal."""
        if target in self._s.pinned:
            self._s.pinned.remove(target)
            self._s.hidden.append(target)
        elif target in self._s.hidden:
            self._s.hidden.remove(target)
        else:
            self._s.pinned.append(target)
        self._save()

    @Slot()
    def clearFormats(self) -> None:
        self._s.pinned, self._s.hidden = [], []
        self._save()

    @Property("QVariantList", notify=changed)
    def quickChoices(self) -> list[dict]:
        from ..linux import integrate

        return [{"id": q.target, "label": tr(label_of(q.target)) if q.target in TOOLS else
                 q.target.upper()} for q in integrate.available_quick(chosen=[])]

    # ---- status: integrations, watch, engines ---------------------------------------------
    @Slot()
    def refresh(self) -> None:
        from ..completions import install_path
        from ..linux import daemon, hotkey, integrate, ipc, watch

        registry.refresh()
        now, every = registry.potential_count()
        shell = Path(os.environ.get("SHELL", "bash")).name
        shell = shell if shell in ("bash", "zsh", "fish") else "bash"
        self._status = {
            "daemon": bool(ipc.daemon_running()),
            "autostart": daemon.autostart_file().exists(),
            "menus": integrate.manifest_path().exists(),
            "hotkey": hotkey.installed() or "",
            "desktop": hotkey.desktop(),
            "shell": shell,
            "completions": install_path(shell).exists(),
            "now": now,
            "every": every,
            "watch": [
                {"name": p.stem, "desc": watch.describe(p), "active": _unit_active(p.name)}
                for p in watch.installed_services()
            ],
            "backends": [_backend_info(b) for b in registry.backends()],
        }
        self.statusChanged.emit()

    def _st(key):  # noqa: N805
        return lambda self: self._status.get(key)

    daemonRunning = Property(bool, _st("daemon"), notify=statusChanged)
    autostart = Property(bool, _st("autostart"), notify=statusChanged)
    menusInstalled = Property(bool, _st("menus"), notify=statusChanged)
    hotkey = Property(str, _st("hotkey"), notify=statusChanged)
    desktop = Property(str, _st("desktop"), notify=statusChanged)
    shell = Property(str, _st("shell"), notify=statusChanged)
    completionsInstalled = Property(bool, _st("completions"), notify=statusChanged)
    conversionsNow = Property(int, _st("now"), notify=statusChanged)
    conversionsAll = Property(int, _st("every"), notify=statusChanged)
    watchServices = Property("QVariantList", _st("watch"), notify=statusChanged)
    backends = Property("QVariantList", _st("backends"), notify=statusChanged)
    del _st

    @Property(bool, notify=statusChanged)
    def hotkeySupported(self) -> bool:
        return self._status.get("desktop") in ("gnome", "xfce")

    @Property(str, notify=changed)
    def dockSide(self) -> str:
        return self._s.dock_side

    # ---- actions --------------------------------------------------------------------------
    @Slot(str, result=str)
    def setHotkey(self, binding: str) -> str:
        """Returns '' when saved, else the reason (taken, unsupported desktop)."""
        from ..linux import hotkey

        try:
            hotkey.install(binding)
        except hotkey.HotkeyError as exc:
            return str(exc)
        self.refresh()
        return ""

    @Slot()
    def removeHotkey(self) -> None:
        from ..linux import hotkey

        try:
            hotkey.remove()
        except hotkey.HotkeyError:
            pass
        self.refresh()

    @Slot(bool)
    def setDaemon(self, on: bool) -> None:
        from ..linux import daemon, ipc

        if on:
            daemon.install_autostart()
            if not ipc.daemon_running():
                daemon.start_detached()
                _wait_for(ipc.daemon_running)
        else:
            ipc.request({"cmd": "quit"})
            daemon.remove_autostart()
            _wait_for(lambda: not ipc.daemon_running())
        self.refresh()

    @Slot(bool)
    def setMenus(self, on: bool) -> None:
        from ..linux import integrate

        integrate.install() if on else integrate.remove()
        self.refresh()

    @Slot()
    def undock(self) -> None:
        self._s.dock_side = ""
        self._save()

    @Slot()
    def installCompletions(self) -> None:
        from .. import completions
        from ..cli import _parser

        completions.install(self._status.get("shell", "bash"), _parser())
        self.refresh()

    @Slot(str, str, str, result=str)
    def addWatch(self, folder: str, target: str, sources: str) -> str:
        from ..core.common import ConversionError
        from ..linux import watch

        if folder.startswith("file://"):
            from PySide6.QtCore import QUrl

            folder = QUrl(folder).toLocalFile()
        path = Path(folder).expanduser()
        if not path.is_dir():
            return f"not a folder: {folder}"
        srcs = {s.strip() for s in sources.replace(" ", ",").split(",") if s.strip()}
        try:
            watch.Watcher([path], target, srcs)  # validates the combination
        except ConversionError as exc:
            return str(exc)
        args = [str(path.resolve()), "--to", target]
        if srcs:
            args += ["--from", ",".join(sorted(srcs))]
        watch.install_service(args, [path], target)
        self.refresh()
        return ""

    @Slot(str)
    def removeWatch(self, name: str) -> None:
        from ..linux import watch

        watch.remove_service(name)
        self.refresh()

    @Property("QVariantList", constant=True)
    def watchTargets(self) -> list[str]:
        from ..completions import _targets

        return [t for t in _targets() if t != "merge-pdf"]

    @Slot(str)
    def copy(self, text: str) -> None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(text)

    @Slot()
    def openSettingsFile(self) -> None:
        path = settings.settings_path()
        settings.save(self._s)  # make sure it exists
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    # ---- about ----------------------------------------------------------------------------
    @Property(str, constant=True)
    def version(self) -> str:
        return __version__

    @Property(str, constant=True)
    def settingsPath(self) -> str:
        return str(settings.settings_path())


def _wait_for(check, seconds: float = 4.0) -> None:
    import time

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.15)


def _unit_active(name: str) -> bool:
    if not shutil.which("systemctl"):
        return False
    try:
        proc = subprocess.run(["systemctl", "--user", "is-active", name],
                              capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.stdout.strip() == "active"


def _backend_info(backend) -> dict:
    ready = backend.available() and bool(backend.pairs())
    return {
        "name": backend.name,
        "description": backend.description,
        "ready": ready,
        "missing": [{"name": r.name, "install": r.install}
                    for r in backend.requirements if not r.present()],
        "extras": [{"name": r.name, "purpose": r.purpose, "present": r.present(),
                    "install": r.install} for r in backend.extras],
    }


def run() -> int:
    from ..ui.window import prepare_platform

    prepare_platform()
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError:
        print("The settings window needs PySide6:  pip install 'dotmorph[gui]'", file=sys.stderr)
        return 2
    from .i18n_qt import I18n

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    app.setApplicationName("DotMorph")
    app.setDesktopFileName("dotmorph-settings")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "icons" / "dotmorph.svg")))
    i18n = I18n(settings.load().language)
    backend = SettingsBackend(i18n)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("i18n", i18n)
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(QML)))
    if not engine.rootObjects():
        return 1
    code = app.exec()
    import shiboken6

    for obj in engine.rootObjects():
        shiboken6.delete(obj)
    del engine
    return code
