"""Files copied in a file manager (Ctrl+C), read from the clipboard.

Tried in order: wl-paste (Wayland), xclip / xsel (X11 and XWayland). File managers put
`text/uri-list` (and GNOME's `x-special/gnome-copied-files`) on the clipboard.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse


def parse_uri_list(text: str) -> list[Path]:
    paths: list[Path] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line in ("copy", "cut"):
            continue
        if line.startswith("file://"):
            parsed = urlparse(line)
            if parsed.netloc not in ("", "localhost"):
                continue
            paths.append(Path(unquote(parsed.path)))
        elif line.startswith("/"):
            paths.append(Path(line))
    return [p for p in paths if p.is_file()]


def _run(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def _commands() -> list[list[str]]:
    cmds: list[list[str]] = []
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        for mime in ("text/uri-list", "x-special/gnome-copied-files"):
            cmds.append(["wl-paste", "--no-newline", "--type", mime])
    if os.environ.get("DISPLAY"):
        if shutil.which("xclip"):
            for mime in ("text/uri-list", "x-special/gnome-copied-files"):
                cmds.append(["xclip", "-selection", "clipboard", "-t", mime, "-o"])
        if shutil.which("xsel"):
            cmds.append(["xsel", "--clipboard", "--output"])
    return cmds


def files_from_clipboard() -> list[Path]:
    for cmd in _commands():
        files = parse_uri_list(_run(cmd))
        if files:
            return files
    return []
