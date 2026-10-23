"""`dotmorph hotkey`: a global shortcut that opens the wheel with the copied files.

The desktop owns global shortcuts (that's the only thing that works on Wayland too), so
we register a custom shortcut with it:
  * GNOME / Budgie / Cinnamon-like: gsettings custom-keybindings (appended, others kept)
  * Xfce: xfconf-query xfce4-keyboard-shortcuts
Other desktops get printed instructions.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
from dataclasses import dataclass

from .paths import shell_command

DEFAULT_GNOME = "<Super><Shift>m"
DEFAULT_XFCE = "<Super><Shift>m"
MEDIA_KEYS = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = f"{MEDIA_KEYS}.custom-keybinding"
OUR_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/dotmorph/"
SEARCH_SCHEMAS = (
    "org.gnome.desktop.wm.keybindings",
    "org.gnome.shell.keybindings",
    "org.gnome.mutter.keybindings",
    "org.gnome.mutter.wayland.keybindings",
    MEDIA_KEYS,
)


class HotkeyError(Exception):
    pass


@dataclass
class Result:
    desktop: str
    binding: str
    message: str


def desktop() -> str:
    current = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if any(name in current for name in ("gnome", "unity", "budgie", "pantheon")):
        return "gnome"
    if "xfce" in current:
        return "xfce"
    if "kde" in current:
        return "kde"
    return current or "unknown"


def command() -> str:
    return shell_command("--clipboard")


def _gsettings(*args: str) -> str:
    proc = subprocess.run(["gsettings", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise HotkeyError(proc.stderr.strip() or f"gsettings {' '.join(args)} failed")
    return proc.stdout.strip()


def _gvariant_list(text: str) -> list[str]:
    text = text.strip()
    if text.startswith("@as"):
        text = text[3:].strip()
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def _normal(binding: str) -> str:
    return binding.lower().replace("<primary>", "<control>").replace("<ctrl>", "<control>")


def gnome_conflicts(binding: str) -> list[str]:
    """Other shortcuts already using `binding` (keys of other apps / the shell)."""
    wanted = _normal(binding)
    hits: list[str] = []
    for schema in SEARCH_SCHEMAS:
        try:
            listing = _gsettings("list-recursively", schema)
        except HotkeyError:
            continue
        for line in listing.splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and wanted in _normal(parts[2]):
                hits.append(f"{parts[0]} {parts[1]}")
    for path in _gvariant_list(_gsettings("get", MEDIA_KEYS, "custom-keybindings")):
        if path == OUR_PATH:
            continue
        try:
            other = _gsettings("get", f"{CUSTOM_SCHEMA}:{path}", "binding").strip("'")
        except HotkeyError:
            continue
        if _normal(other) == wanted:
            name = _gsettings("get", f"{CUSTOM_SCHEMA}:{path}", "name").strip("'")
            hits.append(f"custom shortcut {name!r}")
    return hits


def install_gnome(binding: str = DEFAULT_GNOME, force: bool = False) -> Result:
    conflicts = gnome_conflicts(binding)
    if conflicts and not force:
        raise HotkeyError(f"{binding} is already used by: {', '.join(conflicts)}. "
                          "Pick another with --key, or pass --force.")
    paths = _gvariant_list(_gsettings("get", MEDIA_KEYS, "custom-keybindings"))
    if OUR_PATH not in paths:
        paths.append(OUR_PATH)
        _gsettings("set", MEDIA_KEYS, "custom-keybindings", str(paths))
    schema = f"{CUSTOM_SCHEMA}:{OUR_PATH}"
    _gsettings("set", schema, "name", "DotMorph")
    _gsettings("set", schema, "command", command())
    _gsettings("set", schema, "binding", binding)
    return Result("gnome", binding, f"GNOME shortcut {binding} -> DotMorph")


def remove_gnome() -> bool:
    paths = _gvariant_list(_gsettings("get", MEDIA_KEYS, "custom-keybindings"))
    if OUR_PATH not in paths:
        return False
    paths.remove(OUR_PATH)
    _gsettings("set", MEDIA_KEYS, "custom-keybindings", str(paths))
    _gsettings("reset-recursively", f"{CUSTOM_SCHEMA}:{OUR_PATH}")
    return True


def _xfconf(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", *args],
                          capture_output=True, text=True, check=False)


def install_xfce(binding: str = DEFAULT_XFCE, force: bool = False) -> Result:
    prop = f"/commands/custom/{binding}"
    existing = _xfconf("-p", prop)
    if existing.returncode == 0 and "dotmorph" not in existing.stdout and not force:
        raise HotkeyError(f"{binding} is already used by: {existing.stdout.strip()}. "
                          "Pick another with --key, or pass --force.")
    proc = _xfconf("-p", prop, "-n", "-t", "string", "-s", command())
    if proc.returncode != 0:
        raise HotkeyError(proc.stderr.strip() or "xfconf-query failed")
    return Result("xfce", binding, f"Xfce shortcut {binding} -> DotMorph")


def remove_xfce() -> bool:
    listing = _xfconf("-l", "-v")
    removed = False
    for line in listing.stdout.splitlines():
        prop, _, value = line.partition(" ")
        if prop.startswith("/commands/custom/") and "dotmorph" in value and "--clipboard" in value:
            _xfconf("-p", prop, "-r")
            removed = True
    return removed


def install(binding: str | None = None, force: bool = False) -> Result:
    de = desktop()
    if de == "gnome" and shutil.which("gsettings"):
        return install_gnome(binding or DEFAULT_GNOME, force)
    if de == "xfce" and shutil.which("xfconf-query"):
        return install_xfce(binding or DEFAULT_XFCE, force)
    raise HotkeyError(
        f"Can't set shortcuts automatically on {de!r}. Add one in your desktop's keyboard "
        f"settings that runs:\n  {command()}"
    )


def installed() -> str | None:
    """The binding DotMorph is registered under, if any."""
    try:
        de = desktop()
        if de == "gnome" and shutil.which("gsettings"):
            if OUR_PATH in _gvariant_list(_gsettings("get", MEDIA_KEYS, "custom-keybindings")):
                return _gsettings("get", f"{CUSTOM_SCHEMA}:{OUR_PATH}", "binding").strip("'")
        if de == "xfce" and shutil.which("xfconf-query"):
            for line in _xfconf("-l", "-v").stdout.splitlines():
                prop, _, value = line.partition(" ")
                if prop.startswith("/commands/custom/") and "--clipboard" in value:
                    return prop.rsplit("/", 1)[-1]
    except HotkeyError:
        return None
    return None


def remove() -> bool:
    de = desktop()
    if de == "gnome" and shutil.which("gsettings"):
        return remove_gnome()
    if de == "xfce" and shutil.which("xfconf-query"):
        return remove_xfce()
    return False
