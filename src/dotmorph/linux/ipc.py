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


class DaemonBusy(Exception):
    """The daemon accepted the request but didn't answer in time: it's alive, just slow (a
    busy machine can take seconds to show the wheel). Not the same as "no daemon"."""


def exchange(message: dict, timeout: float = 2.0) -> dict | None:
    """Send one request. Returns the reply, or None when no daemon is there to take it;
    raises DaemonBusy when one took it but didn't reply within `timeout`."""
    path = socket_path()
    if not path.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(path))
            sock.sendall((json.dumps(message) + "\n").encode())
            with sock.makefile("r", encoding="utf-8") as reader:
                try:
                    line = reader.readline()
                except TimeoutError as exc:
                    raise DaemonBusy(message.get("cmd", "")) from exc
        return json.loads(line) if line else None
    except DaemonBusy:
        raise
    except (OSError, ValueError):
        return None


def request(message: dict, timeout: float = 2.0) -> dict | None:
    """Send one request; returns the reply, or None when no daemon answers in time."""
    try:
        return exchange(message, timeout)
    except DaemonBusy:
        return None


def daemon_running() -> dict | None:
    reply = request({"cmd": "ping"}, timeout=1.0)
    return reply if reply and reply.get("ok") else None
