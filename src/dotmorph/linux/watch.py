"""`dotmorph watch`: convert files as they land in a folder (inotify, no polling).

    dotmorph watch ~/Downloads --from heic,png --to jpg
    dotmorph watch ~/Screenshots --to webp --install     # as a systemd user service

Reacts to IN_CLOSE_WRITE (a file finished writing) and IN_MOVED_TO (browsers write
`x.part` then rename it). Its own outputs never trigger it again.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import os
import select
import shutil
import struct
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..core import registry
from ..core.common import ConversionError, Options
from ..core.converter import convert
from ..core.formats import TOOLS, normalize_ext, source_format
from .paths import config_home, shell_command

IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE_SELF = 0x00000400
IN_ISDIR = 0x40000000
IN_Q_OVERFLOW = 0x00004000
_EVENT = struct.Struct("iIII")
SETTLE = 0.6  # seconds a file must stay quiet before we touch it


class _Inotify:
    def __init__(self) -> None:
        self.libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        self.fd = self.libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")
        self.dirs: dict[int, Path] = {}

    def add(self, path: Path, mask: int) -> None:
        wd = self.libc.inotify_add_watch(self.fd, os.fsencode(path), mask)
        if wd < 0:
            err = ctypes.get_errno()
            raise OSError(err, f"cannot watch {path}: {os.strerror(err)}")
        self.dirs[wd] = path

    def read(self, timeout: float) -> list[tuple[Path, int]]:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return []
        try:
            data = os.read(self.fd, 64 * 1024)
        except BlockingIOError:
            return []
        events = []
        offset = 0
        while offset + _EVENT.size <= len(data):
            wd, mask, _cookie, length = _EVENT.unpack_from(data, offset)
            offset += _EVENT.size
            raw = data[offset:offset + length].rstrip(b"\0")
            offset += length
            base = self.dirs.get(wd)
            if base is not None:
                events.append((base / os.fsdecode(raw) if raw else base, mask))
            elif mask & IN_Q_OVERFLOW:
                events.append((Path(), mask))
        return events

    def close(self) -> None:
        os.close(self.fd)


@dataclass
class Watcher:
    dirs: Sequence[Path]
    target: str
    sources: set[str] = field(default_factory=set)  # empty: everything that can go to target
    opts: Options = field(default_factory=Options)
    recursive: bool = False
    notify: bool = False
    log: Callable[[str], None] = print
    stop: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        self.target = normalize_ext(self.target)
        self.sources = {normalize_ext(s) for s in self.sources}
        if not self.sources:
            self.sources = {src for src, acts in registry.matrix().items() if self.target in acts}
        bad = [s for s in self.sources if self.target not in registry.actions_for(s)]
        if bad:
            raise ConversionError(f"cannot convert {', '.join(sorted(bad))} to {self.target}")
        if not self.sources:
            raise ConversionError(f"nothing can be converted to {self.target}")

    def wanted(self, path: Path) -> bool:
        name = path.name
        if name.startswith(".") or any(p.startswith(".dotmorph-") for p in path.parts):
            return False  # hidden files and our own scratch dirs
        if source_format(path) not in self.sources:
            return False
        tool = TOOLS.get(self.target)
        if tool and path.stem.endswith(tool.suffix):
            return False  # our own "-compressed" output: don't loop
        return path.is_file()

    def run(self) -> None:
        ino = _Inotify()
        mask = IN_CLOSE_WRITE | IN_MOVED_TO | IN_DELETE_SELF | (IN_CREATE if self.recursive else 0)
        try:
            for root in self.dirs:
                root = Path(root).expanduser().resolve()
                if not root.is_dir():
                    raise ConversionError(f"not a folder: {root}")
                ino.add(root, mask)
                if self.recursive:
                    for sub in root.rglob("*"):
                        if sub.is_dir() and not sub.name.startswith("."):
                            ino.add(sub, mask)
            names = ", ".join(sorted(self.sources))
            self.log(f"watching {', '.join(str(d) for d in self.dirs)}: {names} -> {self.target}")
            pending: dict[Path, float] = {}
            while not self.stop.is_set():
                for path, ev in ino.read(0.25):
                    if ev & IN_ISDIR:
                        if self.recursive and ev & (IN_CREATE | IN_MOVED_TO):
                            ino.add(path, mask)
                        continue
                    if ev & (IN_CLOSE_WRITE | IN_MOVED_TO):
                        pending[path] = time.monotonic()
                now = time.monotonic()
                for path in [p for p, t in pending.items() if now - t >= SETTLE]:
                    del pending[path]
                    if self.wanted(path):
                        self.handle(path)
        finally:
            ino.close()

    def handle(self, path: Path) -> None:
        try:
            outputs = convert(path, self.target, self.opts)
        except ConversionError as exc:
            self.log(f"FAIL  {path.name}: {exc}")
            if self.notify:
                from .notify import notify

                notify([], [f"{path.name}: {exc}"])
            return
        for out in outputs:
            self.log(f"ok    {path.name} -> {out}")
        if self.notify:
            from .notify import notify

            notify(outputs)


# ---- systemd user service -------------------------------------------------------------


def _unit_dir() -> Path:
    return config_home() / "systemd" / "user"


def unit_name(dirs: Sequence[Path], target: str) -> str:
    key = "|".join(str(Path(d).expanduser().resolve()) for d in dirs) + f"->{target}"
    return f"dotmorph-watch-{hashlib.sha1(key.encode()).hexdigest()[:8]}.service"


def install_service(args: Sequence[str], dirs: Sequence[Path], target: str,
                    start: bool = True) -> Path:
    """Write a user unit running `dotmorph watch <args>`; enable + start it."""
    name = unit_name(dirs, target)
    path = _unit_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Unit]\n"
        f"Description=DotMorph: convert new files in {', '.join(map(str, dirs))} to {target}\n"
        "After=graphical-session.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={shell_command('watch', *args)}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "Nice=10\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    if start and shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "enable", "--now", name], check=False)
    return path


def installed_services() -> list[Path]:
    folder = _unit_dir()
    return sorted(folder.glob("dotmorph-watch-*.service")) if folder.is_dir() else []


def remove_service(name: str, stop: bool = True) -> bool:
    if not name.endswith(".service"):
        name += ".service"
    path = _unit_dir() / name
    if not path.exists():
        return False
    if stop and shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "disable", "--now", name], check=False)
    path.unlink()
    if stop and shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    return True


def describe(path: Path) -> str:
    for line in path.read_text().splitlines():
        if line.startswith("Description="):
            return line.split("=", 1)[1]
    return ""

