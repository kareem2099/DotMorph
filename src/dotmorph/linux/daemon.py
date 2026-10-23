"""`dotmorph daemon`: keep Qt and the QML menu loaded, show it on request.

Also installs itself as an XDG autostart entry, so it is there after every login.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .. import __version__
from . import ipc
from .paths import config_home, desktop_exec, launcher

AUTOSTART_NAME = "dotmorph-daemon.desktop"


def autostart_file() -> Path:
    return config_home() / "autostart" / AUTOSTART_NAME


def install_autostart() -> Path:
    path = autostart_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=DotMorph daemon\n"
        "Comment=Keeps the DotMorph wheel ready so it opens instantly\n"
        f"Exec={desktop_exec('daemon')}\n"
        "Icon=dotmorph\n"
        "Terminal=false\n"
        "NoDisplay=true\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-GNOME-Autostart-Delay=3\n"
    )
    return path


def remove_autostart() -> bool:
    path = autostart_file()
    if path.exists():
        path.unlink()
        return True
    return False


def start_detached() -> None:
    subprocess.Popen(
        [*launcher(), "daemon"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def serve(theme: str | None = None, reduce_motion: bool | None = None) -> int:
    """Run the daemon in the foreground until `dotmorph daemon --stop`."""
    if ipc.daemon_running():
        print("DotMorph daemon is already running.", file=sys.stderr)
        return 1

    from ..ui.window import Menu, prepare_platform

    prepare_platform()
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
    except ImportError:
        print("The daemon needs PySide6:  pip install 'dotmorph[gui]'", file=sys.stderr)
        return 2

    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # sockets need its loop
    path = str(ipc.socket_path())
    QLocalServer.removeServer(path)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(path):
        print(f"cannot listen on {path}: {server.errorString()}", file=sys.stderr)
        return 1
    menu = Menu([], theme=theme, reduce_motion=reduce_motion, persistent=True)
    menu.start_docked()  # the edge tab, if the wheel was docked last time

    def handle(message: dict) -> dict:
        cmd = message.get("cmd")
        if cmd == "ping":
            return {"ok": True, "pid": os.getpid(), "version": __version__,
                    "visible": bool(menu.window.isVisible())}
        if cmd == "open":
            files = [str(f) for f in message.get("files", [])]
            menu.summon(files, message.get("theme"), message.get("reduce_motion"))
            return {"ok": True}
        if cmd == "reload":
            menu.reload()
            return {"ok": True}
        if cmd == "quit":
            from PySide6.QtCore import QTimer

            QTimer.singleShot(50, menu.app.quit)
            return {"ok": True}
        return {"ok": False, "error": f"unknown command {cmd!r}"}

    def on_connection() -> None:
        while server.hasPendingConnections():
            sock: QLocalSocket = server.nextPendingConnection()
            buffer = bytearray()

            def on_ready(sock=sock, buffer=buffer) -> None:
                buffer.extend(bytes(sock.readAll()))
                if b"\n" not in buffer:
                    return
                line = bytes(buffer).split(b"\n", 1)[0]
                try:
                    reply = handle(json.loads(line))
                except (ValueError, TypeError) as exc:
                    reply = {"ok": False, "error": str(exc)}
                sock.write((json.dumps(reply) + "\n").encode())
                sock.flush()
                sock.disconnectFromServer()

            sock.readyRead.connect(on_ready)
            sock.disconnected.connect(sock.deleteLater)
            if sock.bytesAvailable():  # the request may already be waiting
                on_ready()

    server.newConnection.connect(on_connection)
    print(f"DotMorph daemon {__version__} ready on {path}", flush=True)
    code = menu.app.exec()
    server.close()
    QLocalServer.removeServer(path)
    menu.shutdown()
    return code
