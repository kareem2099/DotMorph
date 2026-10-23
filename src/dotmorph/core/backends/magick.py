"""ImageMagick for what Pillow can't read: SVG, PSD, XCF, HEIC, JPEG XL.

ImageMagick only rasterises to a temporary PNG; Pillow writes the final format, so
quality settings match everywhere and distro policy.xml limits on PDF don't bite.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image

from ..common import (
    ConversionError,
    Job,
    finalize,
    last_error_line,
    out_dir,
    resized_size,
    run_tool,
    workdir,
)
from ..registry import Backend, Requirement

IM_NAMES = {"svg": "SVG", "psd": "PSD", "xcf": "XCF", "heic": "HEIC", "heif": "HEIF",
            "jxl": "JXL"}
TARGETS = {"png", "jpg", "webp", "avif", "gif", "bmp", "tiff", "ico", "pdf"}
MAGICK = Requirement("magick", {"apt": "imagemagick", "dnf": "ImageMagick",
                                "pacman": "imagemagick", "zypper": "ImageMagick"},
                     "SVG, PSD, XCF, HEIC, JPEG XL")


def _exe() -> str | None:
    exe = shutil.which("magick")
    if exe:
        return exe
    legacy = shutil.which("convert")  # ImageMagick 6
    if legacy:
        try:
            ver = subprocess.run([legacy, "-version"], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if "ImageMagick" in ver.stdout:
            return legacy
    return None


@lru_cache(maxsize=1)
def _formats() -> dict[str, str]:
    """IM format name -> mode string like 'rw+'."""
    exe = _exe()
    if not exe:
        return {}
    try:
        proc = subprocess.run(
            [exe, "-list", "format"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    found = {}
    for line in proc.stdout.splitlines():
        m = re.match(r"^\s*([A-Z0-9-]+)\*?\s+\S+\s+([r-][w-][+-])", line)
        if m:
            found[m.group(1)] = m.group(2)
    return found


class MagickBackend(Backend):
    name = "imagemagick"
    description = "SVG, PSD, XCF, HEIC, JPEG XL -> any image format or PDF"
    requirements = (MAGICK,)

    def available(self) -> bool:
        return _exe() is not None

    def clear_cache(self) -> None:
        _formats.cache_clear()

    def potential_pairs(self) -> dict[str, set[str]]:
        return {src: set(TARGETS) for src in IM_NAMES}

    def pairs(self) -> dict[str, set[str]]:
        modes = _formats()
        from .pillow import writable

        targets = TARGETS & set(writable())
        return {src: set(targets) for src, im in IM_NAMES.items()
                if modes.get(im, "-").startswith("r")}

    def run(self, job: Job) -> list[Path]:
        from .pillow import save_image

        src, target, opts, ctx = job.src, job.action, job.opts, job.ctx
        exe = _exe()
        if exe is None:
            raise ConversionError("ImageMagick not found")
        fmt = src.suffix.lower().lstrip(".")
        out = out_dir(src, opts)
        with workdir(out) as tmpdir:
            raster = tmpdir / "render.png"
            cmd = [exe, "-density", str(opts.vector_dpi), "-background", "none"]
            if fmt == "xcf":
                cmd += [str(src), "-layers", "merge"]
            elif fmt in ("psd", "heic", "heif"):
                cmd += [f"{src}[0]"]  # flattened composite / primary image
            else:
                cmd += [str(src)]
            cmd += [f"PNG32:{raster}"]
            code, err = run_tool(cmd, ctx, timeout=opts.timeout)
            if code != 0 or not raster.exists():
                raise ConversionError(f"ImageMagick failed: {last_error_line(err)}")
            ctx.progress(0.7)

            name = f"{src.stem}.{target}"
            tmp = tmpdir / name
            with Image.open(raster) as im:
                im.load()
                if opts.resize:
                    im = im.resize(resized_size(opts.resize, *im.size), Image.Resampling.LANCZOS)
                save_image(im, tmp, target, opts)
            ctx.progress(1)
            return [finalize(tmp, out / name, opts.overwrite)]
