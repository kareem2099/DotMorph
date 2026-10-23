"""Tiny JSON-lines protocol over a Unix socket between `dotmorph FILE` and the daemon.

The client side is plain stdlib (no Qt import), so handing files to a running daemon takes
milliseconds instead of the ~1 s it costs to start Qt.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
from pathlib import Path

from .paths import runtime_dir

_MAX_SUN_PATH = 100  # sockaddr_un.sun_path is 108 bytes on Linux


def socket_path() -> Path:
    path = runtime_dir() / "dotmorph.sock"
    if len(os.fsencode(path)) <= _MAX_SUN_PATH:
        return path
    # Unusually long XDG_RUNTIME_DIR: use a short private dir, unique per runtime dir.
    short = Path(f"/tmp/dotmorph-{os.getuid()}")
    short.mkdir(mode=0o700, exist_ok=True)
    digest = hashlib.sha1(os.fsencode(path)).hexdigest()[:10]
    return short / f"{digest}.sock"


def request(message: dict, timeout: float = 2.0) -> dict | None:
    """Send one request; returns the reply, or None when no daemon answers."""
    path = socket_path()
    if not path.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(path))
            sock.sendall((json.dumps(message) + "\n").encode())
            with sock.makefile("r", encoding="utf-8") as reader:
                line = reader.readline()
        return json.loads(line) if line else None
    except (OSError, ValueError):
        return None


def daemon_running() -> dict | None:
    reply = request({"cmd": "ping"}, timeout=1.0)
    return reply if reply and reply.get("ok") else None
