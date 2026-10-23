"""XDG locations and the command line that starts this very DotMorph install."""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value and Path(value).is_absolute() else Path.home() / default


def config_home() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def data_home() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share")


def runtime_dir() -> Path:
    value = os.environ.get("XDG_RUNTIME_DIR")
    if value and Path(value).is_dir():
        return Path(value)
    fallback = Path(f"/tmp/dotmorph-{os.getuid()}")
    fallback.mkdir(mode=0o700, exist_ok=True)
    return fallback


def launcher() -> list[str]:
    """argv that runs DotMorph from desktop files, scripts and services.

    Absolute, so it works even when the venv is not on PATH (file managers and systemd
    don't read your shell profile).

    Inside an AppImage the code runs from a temporary mount that changes on every start, so
    the stable path is the .AppImage file itself ($APPIMAGE)."""
    appimage = os.environ.get("APPIMAGE")
    if appimage and Path(appimage).is_file():
        return [appimage]
    script = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else None
    if script and script.name == "dotmorph" and script.is_file():
        return [str(script)]
    beside = Path(sys.executable).with_name("dotmorph")
    if beside.is_file():
        return [str(beside)]
    found = shutil.which("dotmorph")
    if found:
        return [str(Path(found).resolve())]
    return [sys.executable, "-m", "dotmorph"]


def shell_command(*args: str) -> str:
    """Launcher + args as one shell-quoted string (for scripts and systemd)."""
    return shlex.join([*launcher(), *args])


def desktop_exec(*args: str) -> str:
    """Launcher + args quoted for a .desktop Exec= line (field codes like %F pass through)."""

    def quote(arg: str) -> str:
        if arg.startswith("%") and len(arg) == 2:
            return arg
        if any(c in arg for c in ' \t\n"\'\\><~|&;$*?#()`'):
            escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
            escaped = escaped.replace("$", "\\$")
            return f'"{escaped}"'
        return arg.replace("%", "%%")

    return " ".join(quote(a) for a in [*launcher(), *args])
