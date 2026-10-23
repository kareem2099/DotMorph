"""Format catalog: extensions, categories, tool actions and menu order.

Which conversions actually work depends on the tools installed; that live matrix lives in
`registry.py`. `targets_for` / `common_targets` are re-exported here for convenience.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = ("image", "video", "audio", "document", "tools")

ALIASES = {
    "jpeg": "jpg",
    "jpe": "jpg",
    "jfif": "jpg",
    "tif": "tiff",
    "htm": "html",
    "xhtml": "html",
    "markdown": "md",
    "mpg": "mpeg",
    "oga": "ogg",
    "text": "txt",
}

_CATALOG = {
    "image": "png jpg webp avif gif bmp tiff ico heic heif svg psd xcf tga jxl",
    "video": "mp4 mkv webm mov avi m4v flv wmv mpeg ts 3gp",
    "audio": "mp3 wav flac ogg opus m4a aac wma",
    "document": "pdf docx doc odt rtf txt md html rst org epub pptx ppt odp xlsx xls ods csv ps",
}
FORMATS: dict[str, str] = {
    ext: category for category, exts in _CATALOG.items() for ext in exts.split()
}

IMAGE_FORMATS = {e for e, c in FORMATS.items() if c == "image"}
VIDEO_FORMATS = {e for e, c in FORMATS.items() if c == "video"}
AUDIO_FORMATS = {e for e, c in FORMATS.items() if c == "audio"}


@dataclass(frozen=True)
class Tool:
    label: str
    suffix: str  # added to the output name: photo-compressed.jpg
    batch: bool = False  # many inputs -> one output


TOOLS: dict[str, Tool] = {
    "compress": Tool("Compress", "-compressed"),
    "resize-50": Tool("50%", "-resized"),
    "rotate-90": Tool("Rotate", "-rotated"),
    "strip": Tool("Strip meta", "-clean"),
    "mute": Tool("Mute", "-muted"),
    "merge-pdf": Tool("Merge PDF", "-merged", batch=True),
}

# Menu order: most wanted first. Anything not listed goes last, alphabetically.
_RANK = (
    "png jpg webp pdf avif gif mp4 mkv webm mov avi mp3 m4a ogg opus flac wav "
    "docx odt md html txt epub xlsx ods csv pptx odp bmp tiff ico m4v "
    "compress resize-50 rotate-90 strip mute merge-pdf"
).split()
RANK = {name: i for i, name in enumerate(_RANK)}


def normalize_ext(value: str) -> str:
    """'.JPEG' -> 'jpg'."""
    ext = value.strip().lower().lstrip(".")
    return ALIASES.get(ext, ext)


def source_format(path: Path) -> str:
    return normalize_ext(path.suffix)


def category_of(action: str) -> str:
    """Category of a target: the format's own, or 'tools'."""
    return "tools" if action in TOOLS else FORMATS.get(action, "other")


def label_of(action: str) -> str:
    tool = TOOLS.get(action)
    return tool.label if tool else action.upper()


def is_batch(action: str) -> bool:
    tool = TOOLS.get(action)
    return bool(tool and tool.batch)


def sort_actions(actions: Iterable[str], source: str = "") -> list[str]:
    """Same-category targets first (MP4 -> MKV before MP4 -> MP3), then the rest, then tools."""
    home = "image" if source == "pdf" else FORMATS.get(source)  # PDF -> PNG is the classic

    def key(action: str) -> tuple[int, int, str]:
        group = 2 if action in TOOLS else (0 if FORMATS.get(action) == home else 1)
        return group, RANK.get(action, len(RANK)), action

    return sorted(set(actions), key=key)


def targets_for(path: Path) -> list[str]:
    from .registry import actions_for

    return actions_for(source_format(path))


def common_targets(paths: Iterable[Path]) -> list[str]:
    """Targets valid for every file (order follows the first file).

    Batch tools such as merge-pdf only appear when there is more than one file."""
    paths = list(paths)
    result: list[str] | None = None
    for path in paths:
        options = targets_for(path)
        result = options if result is None else [t for t in result if t in options]
    result = result or []
    if len(paths) < 2:
        result = [t for t in result if not is_batch(t)]
    return result
