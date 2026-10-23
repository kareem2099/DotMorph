"""Python <-> QML bridge. Conversions run on a thread pool so the UI never freezes."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QRunnable, QThreadPool, QUrl, Signal, Slot

from .. import settings
from ..core.converter import Options, convert_many, default_jobs
from ..core.formats import category_of, common_targets, label_of, source_format
from ..i18n import tr
from ..settings import THEMES

RENDERED = {"pdf", "svg", "ps", "psd", "xcf"}  # sources rasterised at a chosen dpi
NOTIFY_AFTER = 4.0  # seconds; quicker jobs are shown by the menu itself
SUMMON_DEBOUNCE = 0.6  # seconds; repeats of a held hotkey arrive faster than this


def to_path(value: str) -> Path:
    """Accept plain paths and file:// URLs (file managers and QML drops send both)."""
    s = str(value).strip().strip("'\"")
    if s.startswith("file://"):
        url = QUrl(s)
        local = url.toLocalFile()
        return Path(local.strip()) if local else Path(s[7:].strip())
    if s.startswith("file:"):
        url = QUrl(s)
        local = url.toLocalFile()
        return Path(local.strip()) if local else Path(s[5:].strip())
    return Path(s)


class _Job(QRunnable):
    def __init__(
        self, bridge: Bridge, paths: list[Path], target: str, cancel: threading.Event,
        opts: Options,
    ) -> None:
        super().__init__()
        self._opts = opts
        self._bridge = bridge
        self._paths = paths
        self._target = target
        self._cancel = cancel

    def run(self) -> None:
        try:
            result = convert_many(
                self._paths, self._target, self._opts,
                jobs=min(4, default_jobs()), cancel=self._cancel,
                on_fraction=self._bridge.jobProgress.emit,
            )
            outputs = [str(p) for p in result.outputs]
            errors = [f"{p.name}: {msg}" for p, msg in result.errors]
            if result.cancelled:
                errors.append("cancelled")
        except Exception as exc:  # never let a worker die silently
            outputs, errors = [], [str(exc)]
        try:
            self._bridge.jobFinished.emit(outputs, errors)
        except RuntimeError:  # the window was closed while we worked
            pass


class Bridge(QObject):
    sectorsChanged = Signal()
    statusChanged = Signal()
    busyChanged = Signal()
    progressChanged = Signal()
    jobProgress = Signal(float)  # 0..1, emitted from the worker thread
    jobFinished = Signal(list, list)  # outputs, errors (emitted from the worker thread)
    finished = Signal(bool)  # all files converted without error
    cancelled = Signal()  # the user stopped the job; the menu stays open
    themeChanged = Signal()
    optionsChanged = Signal()
    summoned = Signal()  # daemon: show the menu again (files already loaded)

    def __init__(
        self,
        files: list[str] | None = None,
        parent: QObject | None = None,
        *,
        theme: str | None = None,
        reduce_motion: bool | None = None,
        persistent: bool = False,
    ) -> None:
        super().__init__(parent)
        # explicit choices (--theme, env) win over the saved settings
        self._theme_override = theme if theme in THEMES else None
        self._motion_override = reduce_motion
        self._persistent = persistent
        self._hidden = persistent  # the daemon starts with the menu hidden
        self._started = 0.0
        self._last_summon = 0.0
        self._settings = settings.load()
        self._files: list[Path] = []
        self._sectors: list[dict[str, str]] = []
        self._label = "Drop files here"
        self._status = ""
        self._busy = False
        self._progress = 0.0
        self._cancel = threading.Event()
        self._pool = QThreadPool.globalInstance()
        self.jobFinished.connect(self._on_job_finished)
        self.jobProgress.connect(self._on_job_progress)
        self._set_files([to_path(f) for f in files or []])

    # ---- state exposed to QML -------------------------------------------------
    @Property(str, notify=themeChanged)
    def theme(self) -> str:
        return self._theme_override or self._settings.theme

    @Property(bool, notify=themeChanged)
    def reduceMotion(self) -> bool:
        if self._motion_override is not None:
            return self._motion_override
        return self._settings.reduce_motion

    # conversion options (the wheel's options panel), remembered between runs
    @Property(int, notify=optionsChanged)
    def quality(self) -> int:
        return self._settings.quality

    @Property(int, notify=optionsChanged)
    def dpi(self) -> int:
        return self._settings.dpi

    @Property(str, notify=optionsChanged)
    def resize(self) -> str:
        return self._settings.resize

    @Property(bool, notify=optionsChanged)
    def strip(self) -> bool:
        return self._settings.strip

    @Property(str, notify=optionsChanged)
    def optionsSummary(self) -> str:
        return self._settings.summary()

    @Property(bool, notify=sectorsChanged)
    def usesDpi(self) -> bool:
        """Is there a PDF/SVG/... among the files, where the render resolution matters?"""
        return any(source_format(p) in RENDERED for p in self._files)

    @Slot(str, "QVariant")
    def setOption(self, name: str, value) -> None:
        if name in ("quality", "dpi", "resize", "strip"):
            self.update_settings(**{name: value})
            self.optionsChanged.emit()

    def update_settings(self, **changes) -> None:
        """Change and save settings, starting from the file: the settings window may have
        changed other values in the meantime, and we must not write over them."""
        fresh = settings.load()
        for name, value in changes.items():
            setattr(fresh, name, value)
        settings.save(fresh)
        self._settings = fresh.clean()

    @Slot()
    def resetOptions(self) -> None:
        """'Reset' in the options panel: only the four conversion options."""
        defaults = settings.Settings()
        names = ("quality", "dpi", "resize", "strip")
        self.update_settings(**{n: getattr(defaults, n) for n in names})
        self.optionsChanged.emit()

    @Slot()
    def openSettings(self) -> None:
        """The full settings window, in its own process."""
        import subprocess

        from ..linux.paths import launcher

        subprocess.Popen(
            [*launcher(), "settings"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )

    def reload_settings(self) -> None:
        """Pick up changes made by the settings window (another process)."""
        old_theme, old_motion = self.theme, self.reduceMotion
        self._settings = settings.load()
        self.optionsChanged.emit()
        if (self.theme, self.reduceMotion) != (old_theme, old_motion):
            self.themeChanged.emit()

    @Slot()
    def relabel(self) -> None:
        """The language changed: rebuild the translated labels."""
        if not self._busy:
            self._set_files(list(self._files))

    @Property(bool, constant=True)
    def persistent(self) -> bool:
        """True in the daemon: closing hides the menu instead of quitting."""
        return self._persistent

    @Property(bool, notify=sectorsChanged)
    def hasFiles(self) -> bool:
        return len(self._files) > 0

    @Property("QVariantList", notify=sectorsChanged)
    def sectors(self) -> list[dict[str, str]]:
        return self._sectors

    @Property(str, notify=sectorsChanged)
    def fileLabel(self) -> str:
        return self._label

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(float, notify=progressChanged)
    def progress(self) -> float:
        return self._progress

    # ---- slots ---------------------------------------------------------------
    @Slot("QVariantList")
    def setFilesFromUrls(self, urls: list[str]) -> None:
        paths: list[Path] = []
        for u in urls:
            if not u:
                continue
            for line in str(u).splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    paths.append(to_path(line))
        self._set_files(paths)

    @Slot(str)
    def convertTo(self, target: str) -> None:
        if self._busy or not self._files:
            return
        self._cancel = threading.Event()
        self._on_job_progress(0.0)
        self._set_busy(True)
        self._set_status("")
        self._started = time.monotonic()
        self._pool.start(
            _Job(self, list(self._files), target, self._cancel, self._settings.options())
        )

    @Slot()
    def cancel(self) -> None:
        """Stop the running conversion (kills the external tool)."""
        self._cancel.set()

    @property
    def settings(self) -> settings.Settings:
        return self._settings

    def save_settings(self) -> None:
        settings.save(self._settings)

    @Slot()
    def menuHidden(self) -> None:
        self._hidden = True

    def menuShown(self) -> None:
        self._hidden = False

    def summon(
        self, files: list[str], theme: str | None = None, reduce_motion: bool | None = None
    ) -> bool:
        """Daemon: load files (unless a job is running) and ask QML to show the menu.

        Returns False when the request was ignored. A held-down hotkey repeats about every
        30 ms; restarting the open animation each time made the wheel shake.
        """
        now = time.monotonic()
        paths = [to_path(f) for f in files]
        visible = not self._hidden
        repeat = now - self._last_summon < SUMMON_DEBOUNCE
        self._last_summon = now
        if visible and (repeat or [p for p in paths if p.is_file()] == self._files):
            return False  # already showing these files: leave the wheel alone

        old = (self.theme, self.reduceMotion)
        if theme in THEMES:
            self._theme_override = theme
        if reduce_motion is not None:
            self._motion_override = reduce_motion
        self.reload_settings()
        if (self.theme, self.reduceMotion) != old:
            self.themeChanged.emit()
        if not self._busy:
            self._set_status("")
            self._set_files(paths)
        if visible:
            return True  # new files in the open wheel: the rings re-bloom, no re-open
        self._hidden = False
        self.summoned.emit()
        return True

    # ---- internals ---------------------------------------------------------------
    def _set_files(self, paths: list[Path]) -> None:
        self._files = [p for p in paths if p.is_file()]
        targets = self._settings.arrange(common_targets(self._files))
        self._sectors = [
            {"id": t, "label": tr(label_of(t)), "category": category_of(t)} for t in targets
        ]
        if not self._files:
            self._label, status = tr("Drop files here"), ""
        elif not targets:
            self._label, status = tr("Unsupported"), tr("No common format for these files")
        else:
            n = len(self._files)
            self._label = self._files[0].name if n == 1 else tr("%1 files", n)
            status = ""
        self.sectorsChanged.emit()
        self._set_status(status)

    def _set_status(self, text: str) -> None:
        if text != self._status:
            self._status = text
            self.statusChanged.emit()

    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busyChanged.emit()

    @Slot(float)
    def _on_job_progress(self, value: float) -> None:
        if abs(value - self._progress) >= 0.005 or value in (0.0, 1.0):
            self._progress = value
            self.progressChanged.emit()

    @Slot(list, list)
    def _on_job_finished(self, outputs: list[str], errors: list[str]) -> None:
        self._set_busy(False)
        if errors and errors[-1] == "cancelled":
            kept = tr("Cancelled · %1 file(s) kept", len(outputs))
            self._set_status(kept if outputs else tr("Cancelled"))
            self.cancelled.emit()
            return
        if errors:
            first = errors[0] if len(errors[0]) <= 80 else errors[0][:77] + "..."
            self._set_status(tr("%1 failed: %2", len(errors), first))
        else:
            self._set_status(tr("Done · %1 file(s)", len(outputs)))
        # Long jobs: the user has probably looked away, and the menu closes by itself.
        policy = self._settings.notify
        long_job = self._hidden or time.monotonic() - self._started > NOTIFY_AFTER
        if policy == "always" or (policy == "long" and long_job):
            from ..linux.notify import notify

            notify([Path(p) for p in outputs], errors)
        self.finished.emit(not errors)
