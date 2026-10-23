"""Desktop notifications with an "Open folder" button.

Uses notify-send (libnotify). The button handler runs in a small detached shell so the
caller (CLI, file-manager action, GUI) returns at once. "Open folder" asks the file
manager to select the new files (org.freedesktop.FileManager1.ShowItems) and falls back
to xdg-open on the folder.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

ICON = "dotmorph"

_SCRIPT = r"""
action=$(notify-send -a DotMorph -i "$1" -A open="$6" -- "$2" "$3" 2>/dev/null)
[ "$action" = open ] || exit 0
gdbus call --session --dest org.freedesktop.FileManager1 \
  --object-path /org/freedesktop/FileManager1 \
  --method org.freedesktop.FileManager1.ShowItems "$4" "" >/dev/null 2>&1 \
  || xdg-open "$5" >/dev/null 2>&1
"""


@lru_cache(maxsize=1)
def _supports_actions() -> bool:
    exe = shutil.which("notify-send")
    if not exe:
        return False
    try:
        out = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "--action" in out


def message(outputs: Sequence[Path], errors: Sequence[str]) -> tuple[str, str]:
    """(summary, body) for a finished job, in the user's language."""
    from ..i18n import tr

    if errors and not outputs:
        summary = (tr("Conversion failed") if len(errors) == 1
                   else tr("%1 conversions failed", len(errors)))
        return summary, errors[0]
    if errors:
        return tr("Converted %1 file(s), %2 failed", len(outputs), len(errors)), errors[0]
    if len(outputs) == 1:
        return tr("Converted"), outputs[0].name
    names = ", ".join(p.name for p in outputs[:3])
    more = tr(" and %1 more", len(outputs) - 3) if len(outputs) > 3 else ""
    return tr("Converted %1 files", len(outputs)), names + more


def show_items_arg(paths: Sequence[Path]) -> str:
    """GVariant text for ShowItems' string array (URIs are %-encoded: no quotes inside)."""
    return "[" + ", ".join(f"'{p.resolve().as_uri()}'" for p in paths[:20]) + "]"


def notify(outputs: Sequence[Path], errors: Sequence[str] = ()) -> bool:
    """Show a notification; returns False when no notification daemon tool is available."""
    exe = shutil.which("notify-send")
    if not exe:
        return False
    from ..i18n import tr

    outputs = [Path(p) for p in outputs]
    summary, body = message(outputs, errors)
    try:
        if outputs and _supports_actions():
            folder = str(outputs[0].resolve().parent)
            subprocess.Popen(
                ["sh", "-c", _SCRIPT, "dotmorph-notify", ICON, summary, body,
                 show_items_arg(outputs), folder, tr("Open folder")],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            icon = ICON if outputs else "dialog-error"
            subprocess.Popen(
                [exe, "-a", "DotMorph", "-i", icon, "--", summary, body],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except OSError:
        return False
    return True
