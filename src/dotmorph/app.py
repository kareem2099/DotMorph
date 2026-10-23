"""Entry point: CLI subcommands, or the radial menu GUI (through the daemon when it runs)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .ui.window import QML_MAIN  # noqa: F401  (kept for tests and tools)

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

        reply = ipc.request({"cmd": "open", "files": files, "theme": args.theme,
                             "reduce_motion": args.reduce_motion})
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
