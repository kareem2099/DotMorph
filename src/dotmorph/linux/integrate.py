"""`dotmorph integrate`: right-click actions in file managers, "Open with", app icon.

Installs (all per user, nothing needs root):
  * ~/.local/share/applications/dotmorph.desktop   app entry + "Open with DotMorph"
  * ~/.local/share/icons/hicolor/scalable/apps/dotmorph.svg
  * Nautilus  ~/.local/share/nautilus/scripts/DotMorph/*      (Scripts submenu)
  * Nemo      ~/.local/share/nemo/actions/dotmorph-*.nemo_action
  * Dolphin   ~/.local/share/kio/servicemenus/dotmorph.desktop
  * Thunar    entries merged into ~/.config/Thunar/uca.xml (other actions are kept)

Every file written is recorded in a manifest so `--remove` takes away exactly that.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from ..core import registry
from ..core.formats import ALIASES
from .paths import config_home, data_home, desktop_exec, shell_command

ICON_SRC = Path(__file__).resolve().parent.parent / "ui" / "icons" / "dotmorph.svg"
THUNAR_ID = "dotmorph-"
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


@dataclass(frozen=True)
class Quick:
    target: str
    label: str


QUICK = (
    Quick("png", "To PNG"),
    Quick("jpg", "To JPG"),
    Quick("webp", "To WebP"),
    Quick("pdf", "To PDF"),
    Quick("mp4", "To MP4"),
    Quick("mp3", "To MP3"),
    Quick("gif", "To GIF"),
    Quick("compress", "Compress"),
)

# Every catalog format -> its freedesktop MIME types (what file managers use for "Open with").
# Written out instead of asking Python's mimetypes: that answer depends on the Python version
# and on /etc/mime.types, so generated launchers differed between machines (and it maps .ts
# to Qt Linguist files).
MIME = {
    "png": ["image/png"], "jpg": ["image/jpeg"], "webp": ["image/webp"],
    "avif": ["image/avif"], "gif": ["image/gif"], "bmp": ["image/bmp"],
    "tiff": ["image/tiff"], "ico": ["image/vnd.microsoft.icon"],
    "heic": ["image/heic"], "heif": ["image/heif"], "svg": ["image/svg+xml"],
    "psd": ["image/vnd.adobe.photoshop"], "xcf": ["image/x-xcf"], "tga": ["image/x-tga"],
    "jxl": ["image/jxl"],
    "mp4": ["video/mp4"], "mkv": ["video/x-matroska"], "webm": ["video/webm"],
    "mov": ["video/quicktime"], "avi": ["video/x-msvideo", "video/vnd.avi"],
    "m4v": ["video/x-m4v"], "flv": ["video/x-flv"], "wmv": ["video/x-ms-wmv"],
    "mpeg": ["video/mpeg"], "ts": ["video/mp2t"], "3gp": ["video/3gpp"],
    "mp3": ["audio/mpeg"], "wav": ["audio/x-wav", "audio/vnd.wave"], "flac": ["audio/flac"],
    "ogg": ["audio/ogg", "audio/x-vorbis+ogg"], "opus": ["audio/x-opus+ogg"],
    "m4a": ["audio/mp4"], "aac": ["audio/aac"], "wma": ["audio/x-ms-wma"],
    "pdf": ["application/pdf"],
    "docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    "doc": ["application/msword"], "odt": ["application/vnd.oasis.opendocument.text"],
    "rtf": ["application/rtf", "text/rtf"], "txt": ["text/plain"],
    "md": ["text/markdown"], "html": ["text/html"], "rst": ["text/x-rst"],
    "org": ["text/org"], "epub": ["application/epub+zip"],
    "pptx": ["application/vnd.openxmlformats-officedocument.presentationml.presentation"],
    "ppt": ["application/vnd.ms-powerpoint"],
    "odp": ["application/vnd.oasis.opendocument.presentation"],
    "xlsx": ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
    "xls": ["application/vnd.ms-excel"],
    "ods": ["application/vnd.oasis.opendocument.spreadsheet"],
    "csv": ["text/csv"], "ps": ["application/postscript"],
}


def manifest_path() -> Path:
    return data_home() / "dotmorph" / "installed.json"


def mime_types(every: bool = False) -> list[str]:
    """MIME types DotMorph opens: what works here, or (packages) every known format."""
    from ..core.formats import FORMATS

    exts = FORMATS if every else registry.matrix()
    return sorted({mime for ext in exts for mime in MIME.get(ext, [])})


def sources_for(target: str) -> list[str]:
    return [src for src, actions in registry.matrix().items() if target in actions]


def extensions_for(target: str) -> list[str]:
    """Source extensions including aliases (.jpeg, .tif, ...) so file managers match them."""
    srcs = sources_for(target)
    aliases = [alias for alias, ext in ALIASES.items() if ext in srcs]
    return srcs + aliases


def available_quick(chosen: list[str] | None = None) -> list[Quick]:
    """Quick actions that can run here; limited to the user's choice (settings) if any."""
    if chosen is None:
        from ..settings import load

        chosen = load().quick_actions
    return [q for q in QUICK if sources_for(q.target) and (not chosen or q.target in chosen)]


# ---- writers ------------------------------------------------------------------------


def _write(path: Path, text: str, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if executable:
        path.chmod(0o755)
    return path


def desktop_entry(command: str | None = None, every: bool = False) -> str:
    """The app launcher. `command`: Exec program for packages ("dotmorph"); by default the
    absolute path of this install, so it works without PATH changes."""
    run = (lambda *a: " ".join([command, *a])) if command else desktop_exec
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=DotMorph\n"
        "GenericName=File Converter\n"
        "Comment=Convert images, PDF, video, audio and documents from a radial menu\n"
        "Comment[ar]=حوّل الصور وPDF والفيديو والصوت والمستندات من قائمة دائرية\n"
        f"Exec={run('%F')}\n"
        "Icon=dotmorph\n"
        "Terminal=false\n"
        "StartupNotify=false\n"
        "Categories=Utility;FileTools;\n"
        "Keywords=convert;converter;pdf;png;jpg;webp;mp4;mp3;compress;\n"
        f"MimeType={';'.join(mime_types(every))};\n"
        "Actions=settings;\n"
        "\n"
        "[Desktop Action settings]\n"
        "Name=Settings\n"
        "Name[ar]=الإعدادات\n"
        f"Exec={run('settings')}\n"
    )


def settings_entry(command: str | None = None) -> str:
    """A separate launcher so "DotMorph Settings" shows up in the app grid and search."""
    run = (lambda *a: " ".join([command, *a])) if command else desktop_exec
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=DotMorph Settings\n"
        "Name[ar]=إعدادات DotMorph\n"
        "Comment=Theme, language, shortcut, file-manager menus and watch folders\n"
        f"Exec={run('settings')}\n"
        "Icon=dotmorph\n"
        "Terminal=false\n"
        "Categories=Settings;\n"
        "Keywords=dotmorph;converter;settings;preferences;\n"
    )


def nautilus_scripts() -> dict[str, str]:
    """name -> script body. Nautilus passes the selection as newline-separated paths."""
    def script(*args: str) -> str:
        return (
            "#!/bin/sh\n"
            "# Installed by `dotmorph integrate`; removed by `dotmorph integrate --remove`.\n"
            "set -f\n"
            "IFS='\n'\n"
            f"exec {shell_command(*args)} $NAUTILUS_SCRIPT_SELECTED_FILE_PATHS\n"
        )

    scripts = {"Open the wheel": script()}
    for q in available_quick():
        scripts[q.label] = script("convert", "--to", q.target, "--notify", "-q")
    return scripts


def nemo_actions() -> dict[str, str]:
    actions = {
        "dotmorph-wheel": (
            "[Nemo Action]\nName=Convert with DotMorph…\nComment=Open the DotMorph wheel\n"
            f"Exec={desktop_exec('%F')}\nIcon-Name=dotmorph\nSelection=notnone\n"
            "Extensions=any;\n"
        )
    }
    for q in available_quick():
        exts = ";".join(extensions_for(q.target))
        actions[f"dotmorph-{q.target}"] = (
            f"[Nemo Action]\nName=DotMorph: {q.label}\n"
            f"Exec={desktop_exec('convert', '--to', q.target, '--notify', '-q', '%F')}\n"
            f"Icon-Name=dotmorph\nSelection=notnone\nExtensions={exts};\n"
        )
    return actions


def dolphin_menu() -> str:
    quick = available_quick()
    ids = ["wheel"] + [q.target for q in quick]
    lines = [
        "[Desktop Entry]",
        "Type=Service",
        "MimeType=all/allfiles;",
        "X-KDE-ServiceTypes=KonqPopupMenu/Plugin",
        "X-KDE-Submenu=DotMorph",
        "Icon=dotmorph",
        f"Actions={';'.join(ids)};",
        "",
        "[Desktop Action wheel]",
        "Name=Open the wheel…",
        "Icon=dotmorph",
        f"Exec={desktop_exec('%F')}",
    ]
    for q in quick:
        lines += [
            "",
            f"[Desktop Action {q.target}]",
            f"Name={q.label}",
            "Icon=dotmorph",
            f"Exec={desktop_exec('convert', '--to', q.target, '--notify', '-q', '%F')}",
        ]
    return "\n".join(lines) + "\n"


def _thunar_action(uid: str, name: str, command: str, patterns: str, submenu: str) -> ET.Element:
    action = ET.Element("action")
    for tag, text in (("icon", "dotmorph"), ("name", name), ("submenu", submenu),
                      ("unique-id", uid), ("command", command),
                      ("description", "DotMorph"), ("range", ""), ("patterns", patterns)):
        ET.SubElement(action, tag).text = text
    for kind in ("image-files", "video-files", "audio-files", "text-files", "other-files"):
        ET.SubElement(action, kind)
    return action


def _thunar_patterns(exts: list[str]) -> str:
    return ";".join(f"*.{e};*.{e.upper()}" for e in exts)


def update_thunar(path: Path, install: bool) -> bool:
    """Add (or remove) our actions in uca.xml, keeping everything else. Returns True if
    the file changed."""
    if path.exists():
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except ET.ParseError:
            return False  # never clobber a file we can't read
    elif not install:
        return False
    else:
        root = ET.Element("actions")
        tree = ET.ElementTree(root)

    changed = False
    for action in list(root.findall("action")):
        uid = action.findtext("unique-id") or ""
        if uid.startswith(THUNAR_ID):
            root.remove(action)
            changed = True
    if install:
        root.append(_thunar_action(
            f"{THUNAR_ID}wheel", "Convert with DotMorph…", shell_command("%F"), "*", ""
        ))
        for q in available_quick():
            root.append(_thunar_action(
                f"{THUNAR_ID}{q.target}", q.label,
                shell_command("convert", "--to", q.target, "--notify", "-q", "%F"),
                _thunar_patterns(extensions_for(q.target)), "DotMorph",
            ))
        changed = True
    if changed:
        ET.indent(tree)
        path.parent.mkdir(parents=True, exist_ok=True)
        tree.write(path, encoding="UTF-8", xml_declaration=True)
    return changed


# ---- install / remove -----------------------------------------------------------------


def install() -> list[Path]:
    remove(quiet=True)  # start clean so renamed quick actions don't linger
    data = data_home()
    written: list[Path] = []
    written.append(_write(data / "applications" / "dotmorph.desktop", desktop_entry()))
    written.append(_write(data / "applications" / "dotmorph-settings.desktop", settings_entry()))
    icon = data / "icons" / "hicolor" / "scalable" / "apps" / "dotmorph.svg"
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ICON_SRC, icon)
    written.append(icon)
    written += _png_icons(data / "icons" / "hicolor")

    for name, body in nautilus_scripts().items():
        written.append(_write(data / "nautilus" / "scripts" / "DotMorph" / name, body, True))
    for name, body in nemo_actions().items():
        written.append(_write(data / "nemo" / "actions" / f"{name}.nemo_action", body))
    written.append(_write(data / "kio" / "servicemenus" / "dotmorph.desktop",
                          dolphin_menu(), True))

    thunar = config_home() / "Thunar" / "uca.xml"
    update_thunar(thunar, install=True)

    manifest = manifest_path()
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"files": [str(p) for p in written],
                                    "thunar": str(thunar)}, indent=2))
    _refresh_caches()
    return written + [thunar]


def remove(quiet: bool = False) -> list[Path]:
    manifest = manifest_path()
    removed: list[Path] = []
    if manifest.exists():
        try:
            info = json.loads(manifest.read_text())
        except ValueError:
            info = {}
        for raw in info.get("files", []):
            path = Path(raw)
            if path.is_file() or path.is_symlink():
                path.unlink()
                removed.append(path)
        manifest.unlink()
    scripts_dir = data_home() / "nautilus" / "scripts" / "DotMorph"
    if scripts_dir.is_dir() and not any(scripts_dir.iterdir()):
        scripts_dir.rmdir()
    thunar = config_home() / "Thunar" / "uca.xml"
    if update_thunar(thunar, install=False):
        removed.append(thunar)
    if removed and not quiet:
        _refresh_caches()
    return removed


def _png_icons(hicolor: Path) -> list[Path]:
    """PNG sizes for panels and docks that don't scale SVG (rendered with librsvg)."""
    from ..core.backends.svg import render

    written = []
    for size in PNG_SIZES:
        dest = hicolor / f"{size}x{size}" / "apps" / "dotmorph.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            render(ICON_SRC, dest, scale=size / 256)
        except Exception:  # no librsvg: the SVG icon still works almost everywhere
            return written
        written.append(dest)
    return written


def _refresh_caches() -> None:
    data = data_home()
    for cmd in (["update-desktop-database", str(data / "applications")],
                ["gtk-update-icon-cache", "-q", "-t", "-f", str(data / "icons" / "hicolor")]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, capture_output=True, check=False)
