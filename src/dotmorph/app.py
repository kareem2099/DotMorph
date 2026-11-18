"""Entry point: CLI subcommands, or the radial menu GUI (through the daemon when it runs)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .ui.window import QML_MAIN  # noqa: F401  (kept for tests and tools)

# How long `dotmorph FILE` waits for a running daemon. It normally answers in ~0.1 s; on a
# machine under heavy load it can take several seconds, and giving up early used to open a
# second wheel next to the daemon's.
OPEN_TIMEOUT = 15.0

CLI_COMMANDS = {
    "convert", "formats", "doctor", "daemon", "integrate", "hotkey", "watch", "completions",
    "settings",
    "-h", "--help", "-V", "--version",
}


def _gui_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="dotmorph", add_help=False)
    # unset -> the saved settings decide (dotmorph settings)
    parser.add_argument("--theme", choices=("dark", "light", "glass"),
                        default=os.environ.get("DOTMORPH_THEME") or None)
    env_motion = os.environ.get("DOTMORPH_REDUCE_MOTION")
    parser.add_argument("--reduce-motion", action="store_true",
                        default=(env_motion not in ("", "0")) if env_motion is not None else None)
    parser.add_argument("--clipboard", action="store_true",
                        help="use the files copied in the file manager")
    parser.add_argument("--no-daemon", action="store_true",
                        help="open a new window even if the daemon runs")
    parser.add_argument("files", nargs="*")
    args, unknown = parser.parse_known_args(argv)
    args.files += unknown
    return args


def run_gui(argv: list[str]) -> int:
    args = _gui_args(argv)
    files = [str(Path(f).expanduser().absolute()) for f in args.files]
    if args.clipboard and not files:
        from .linux.clipboard import files_from_clipboard

        files = [str(p) for p in files_from_clipboard()]

    if not args.no_daemon:
        from .linux import ipc

        try:
            reply = ipc.exchange({"cmd": "open", "files": files, "theme": args.theme,
                                  "reduce_motion": args.reduce_motion}, timeout=OPEN_TIMEOUT)
        except ipc.DaemonBusy:
            # It has the files and will show the wheel when it catches up; a window of our
            # own now would mean two wheels on screen a moment later.
            print("dotmorph: the daemon is busy, the wheel will open in a moment",
                  file=sys.stderr)
            return 0
        if reply and reply.get("ok"):
            return 0

    from .ui.window import run_once

    return run_once(files, theme=args.theme, reduce_motion=args.reduce_motion)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in CLI_COMMANDS:
        from .cli import main as cli_main

        return cli_main(argv)
    return run_gui(argv)
