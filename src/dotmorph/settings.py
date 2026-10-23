"""Settings remembered between runs: ~/.config/dotmorph/settings.json.

Used by the wheel, the settings window and the desktop integration. The CLI stays explicit
(same flags, same result) and only reads `language` for its notifications.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .core.common import ConversionError, Options, parse_resize

DPI_CHOICES = (0, 72, 150, 300)  # 0 = automatic (PDF 150, SVG original size)
RESIZE_CHOICES = ("", "75%", "50%", "25%")
THEMES = ("dark", "light", "glass")
LANGUAGES = ("auto", "en", "ar")
NOTIFY = ("long", "always", "never")  # long: only after jobs the menu can't show


def settings_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base and Path(base).is_absolute() else Path.home() / ".config"
    return root / "dotmorph" / "settings.json"


@dataclass
class Settings:
    # conversion options (the wheel's options panel)
    quality: int = 90
    dpi: int = 0
    resize: str = ""
    strip: bool = False
    # look and feel
    theme: str = "dark"
    reduce_motion: bool = False
    language: str = "auto"
    notify: str = "long"
    output_dir: str = ""  # empty: next to the source file
    # the wheel's contents
    pinned: list[str] = field(default_factory=list)  # shown first
    hidden: list[str] = field(default_factory=list)  # never shown
    quick_actions: list[str] = field(default_factory=list)  # file-manager menu; empty = all
    # edge dock
    dock_side: str = ""  # "left" / "right" when the wheel lives on a screen edge
    dock_y: float = 0.5  # where on that edge, as a fraction of the screen height

    def clean(self) -> Settings:
        self.quality = min(100, max(1, int(self.quality)))
        self.dpi = max(0, min(1200, int(self.dpi)))
        self.resize = str(self.resize or "")
        if self.resize:
            try:
                parse_resize(self.resize)
            except ConversionError:
                self.resize = ""
        self.strip = bool(self.strip)
        self.theme = self.theme if self.theme in THEMES else "dark"
        self.reduce_motion = bool(self.reduce_motion)
        self.language = self.language if self.language in LANGUAGES else "auto"
        self.notify = self.notify if self.notify in NOTIFY else "long"
        self.output_dir = str(self.output_dir or "")
        self.pinned = _names(self.pinned)
        self.hidden = [n for n in _names(self.hidden) if n not in self.pinned]
        self.quick_actions = _names(self.quick_actions)
        self.dock_side = self.dock_side if self.dock_side in ("left", "right") else ""
        self.dock_y = min(1.0, max(0.0, float(self.dock_y)))
        return self

    def options(self) -> Options:
        out = Path(self.output_dir).expanduser() if self.output_dir else None
        return Options(out_dir=out, quality=self.quality, dpi=self.dpi or None,
                       resize=self.resize or None, strip=self.strip)

    def arrange(self, targets: list[str]) -> list[str]:
        """Wheel order: pinned targets first (in pinned order), hidden ones removed."""
        pinned = [t for t in self.pinned if t in targets]
        rest = [t for t in targets if t not in pinned and t not in self.hidden]
        return pinned + rest

    def summary(self) -> str:
        """Short text for what differs from the defaults, e.g. 'Q75 · 50% · no metadata'."""
        from .i18n import tr

        parts = []
        if self.quality != 90:
            parts.append(f"Q{self.quality}")
        if self.dpi:
            parts.append(f"{self.dpi} dpi")
        if self.resize:
            parts.append(self.resize)
        if self.strip:
            parts.append(tr("no metadata"))
        return " · ".join(parts)


def _names(value) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: list[str] = []
    for item in value:
        name = str(item).strip().lower()
        if name and name not in seen:
            seen.append(name)
    return seen


def load() -> Settings:
    try:
        raw = json.loads(settings_path().read_text())
    except (OSError, ValueError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    known = {f.name for f in fields(Settings)}
    try:
        return Settings(**{k: v for k, v in raw.items() if k in known}).clean()
    except (TypeError, ValueError):
        return Settings()


def save(settings: Settings) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(settings.clean()), indent=2, ensure_ascii=False) + "\n")
    except OSError:
        pass  # a read-only home must not break converting
