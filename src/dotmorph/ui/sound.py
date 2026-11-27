"""UI sounds: short and soft, and silent whenever the user or the desktop says so.

libcanberra (the desktop's event-sound library, loaded through ctypes like librsvg) plays them
as "event" sounds, so the system's alert-volume slider applies. Without it pw-play or paplay
run in the background; without either nothing plays, and that is never an error.

Off switches, any of which wins: Settings -> Sounds, `--mute` for one run, DOTMORPH_SOUND=0,
and GNOME's "event sounds" switch (org.gnome.desktop.sound event-sounds).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import math
import os
import shutil
import subprocess
import time
from pathlib import Path

SOUNDS = Path(__file__).parent / "sounds"
EVENTS = ("bloom", "tick", "click", "chime", "thud", "snap", "cancel")
GAP = {"tick": 0.06}  # hover ticks at most this often (seconds)
DEFAULT_GAP = 0.08  # any one sound: a double trigger plays once


def sound_file(name: str) -> Path:
    return SOUNDS / f"{name}.oga"


_desktop: tuple[float, bool] | None = None  # (checked at, allowed)
DESKTOP_RECHECK = 30.0  # seconds: the daemon notices the switch without a restart


def desktop_allows() -> bool:
    """False when GNOME's "event sounds" switch is off. Unknown desktops: allowed."""
    global _desktop
    now = time.monotonic()
    if _desktop is not None and now - _desktop[0] < DESKTOP_RECHECK:
        return _desktop[1]
    allowed = True
    if exe := shutil.which("gsettings"):
        try:
            out = subprocess.run([exe, "get", "org.gnome.desktop.sound", "event-sounds"],
                                 capture_output=True, text=True, timeout=2)
            allowed = out.stdout.strip() != "false"
        except (OSError, subprocess.TimeoutExpired):
            pass
    _desktop = (now, allowed)
    return allowed


def forget_desktop() -> None:
    global _desktop
    _desktop = None


class Canberra:
    """The few libcanberra calls DotMorph needs. `lib` is the loaded library (or a test fake)."""

    def __init__(self, lib) -> None:
        self.lib = lib
        ctx = ctypes.c_void_p()
        if lib.ca_context_create(ctypes.byref(ctx)) != 0 or not ctx:
            raise OSError("ca_context_create failed")
        self.ctx = ctx
        lib.ca_context_change_props(ctx, b"application.name", b"DotMorph",
                                    b"application.id", b"io.github.kareem2099.DotMorph",
                                    b"application.icon_name", b"dotmorph", None)

    @classmethod
    def load(cls) -> Canberra | None:
        name = ctypes.util.find_library("canberra") or "libcanberra.so.0"
        try:
            lib = ctypes.CDLL(name)
            lib.ca_context_create.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
            lib.ca_context_create.restype = ctypes.c_int
            lib.ca_context_play.restype = ctypes.c_int
            lib.ca_context_change_props.restype = ctypes.c_int
            return cls(lib)
        except (OSError, AttributeError):
            return None

    def play(self, path: Path, volume_db: float, event: str) -> bool:
        code = self.lib.ca_context_play(
            self.ctx, ctypes.c_uint32(1),
            b"media.filename", os.fsencode(path),
            b"event.id", f"dotmorph-{event}".encode(),
            b"media.role", b"event",
            b"canberra.volume", f"{volume_db:.1f}".encode(),
            b"canberra.cache-control", b"volatile",
            None)
        return code == 0


class Player:
    """Plays an event's sound with the saved settings; never blocks, never raises."""

    def __init__(self, settings=None, *, canberra: Canberra | None | bool = True) -> None:
        # anything with .sound, .sound_volume and .sound_ticks, or a function returning it
        self._settings = settings
        self.muted = False  # --mute for this run
        self._canberra = canberra  # True: load on first use
        self._last: dict[str, float] = {}
        self._procs: list[subprocess.Popen] = []

    @property
    def settings(self):
        return self._settings() if callable(self._settings) else self._settings

    def enabled(self, name: str) -> bool:
        s = self.settings
        if self.muted or os.environ.get("DOTMORPH_SOUND", "1") in ("0", "off", "no", "false"):
            return False
        if s is not None and (not s.sound or s.sound_volume <= 0):
            return False
        if name == "tick" and (s is None or not s.sound_ticks):
            return False
        return name in EVENTS and desktop_allows()

    def play(self, name: str, *, force: bool = False) -> str | None:
        """Returns how it played ("canberra", "pw-play", "paplay") or None (silent).
        `force`: the settings window's test button, which plays even if sounds are off."""
        if not force and not self.enabled(name):
            return None
        now = time.monotonic()
        if now - self._last.get(name, -1e9) < GAP.get(name, DEFAULT_GAP):
            return None
        self._last[name] = now
        path = sound_file(name)
        if not path.exists():
            return None
        s = self.settings
        volume = max(1, min(100, s.sound_volume if s is not None else 70))
        try:
            return self._via_canberra(path, volume, name) or self._via_player(path, volume)
        except Exception:  # a sound must never break the wheel
            return None

    def _via_canberra(self, path: Path, volume: int, name: str) -> str | None:
        if self._canberra is True:
            self._canberra = Canberra.load()
        if not self._canberra:
            return None
        db = 20 * math.log10(volume / 100)
        return "canberra" if self._canberra.play(path, db, name) else None

    def _via_player(self, path: Path, volume: int) -> str | None:
        self._procs = [p for p in self._procs if p.poll() is None]  # reap finished ones
        if len(self._procs) >= 4:
            return None
        if exe := shutil.which("pw-play"):
            cmd = [exe, f"--volume={volume / 100:.2f}", str(path)]
        elif exe := shutil.which("paplay"):
            cmd = [exe, f"--volume={int(65536 * volume / 100)}",
                   "--property=media.role=event", str(path)]
        else:
            return None
        self._procs.append(subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL))
        return Path(exe).name


def qt_sound(player: Player):
    """The `sound` object QML calls: sound.play("chime")."""
    from PySide6.QtCore import QObject, Slot

    class Sound(QObject):
        @Slot(str)
        def play(self, name: str) -> None:
            player.play(name)

    return Sound()
