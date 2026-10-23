"""Named bundles of options for `dotmorph convert --preset NAME`.

Explicit flags always win over the preset; the preset wins over the defaults.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    help: str
    to: str | None = None
    quality: int | None = None
    resize: str | None = None
    dpi: int | None = None
    strip: bool = False


PRESETS: dict[str, Preset] = {
    "web": Preset("WebP, fits 1920x1920, quality 80, no metadata",
                  to="webp", quality=80, resize="1920x1920", strip=True),
    "email": Preset("JPG, fits 1280x1280, quality 75, no metadata",
                    to="jpg", quality=75, resize="1280x1280", strip=True),
    "thumb": Preset("WebP thumbnail, fits 320x320", to="webp", quality=70,
                    resize="320x320", strip=True),
    "print": Preset("high resolution: PDF/SVG at 300 dpi, quality 95", dpi=300, quality=95),
    "share": Preset("smaller file in the same format, no metadata", to="compress", strip=True),
}
