"""Images through Pillow: PNG, JPG, WebP, AVIF, GIF, BMP, TIFF, ICO (+ HEIC with pillow-heif).

Keeps animation (GIF / WebP / APNG / AVIF), EXIF orientation, ICC colour profiles and,
unless asked to strip it, EXIF metadata.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

from ..common import (
    Context,
    ConversionError,
    Job,
    Options,
    finalize,
    keep_smaller,
    out_dir,
    resized_size,
    workdir,
)
from ..formats import TOOLS, normalize_ext
from ..registry import Backend, Requirement

PIL_NAMES = {
    "png": "PNG",
    "jpg": "JPEG",
    "webp": "WEBP",
    "avif": "AVIF",
    "gif": "GIF",
    "bmp": "BMP",
    "tiff": "TIFF",
    "ico": "ICO",
    "tga": "TGA",
    "pdf": "PDF",
    "heic": "HEIF",
    "heif": "HEIF",
}
READ_ORDER = ("png", "jpg", "webp", "avif", "gif", "bmp", "tiff", "ico", "tga", "heic", "heif")
WRITE_ORDER = ("png", "jpg", "webp", "avif", "gif", "bmp", "tiff", "ico", "pdf")
ANIMATED = {"gif", "webp", "png", "avif"}
COMPRESSIBLE = {"jpg", "png", "webp", "avif"}
EXIF_TARGETS = {"jpg", "webp", "png", "avif", "tiff"}
KEEP_ON_STRIP = {"icc_profile", "transparency", "duration", "loop", "dpi"}

_ERRORS = (OSError, ValueError, SyntaxError, Image.DecompressionBombError)


@lru_cache(maxsize=1)
def _heif_ready() -> bool:
    try:
        import pillow_heif  # type: ignore[import-not-found]
    except ImportError:
        return False
    pillow_heif.register_heif_opener()
    return True


@lru_cache(maxsize=1)
def readable() -> tuple[str, ...]:
    _heif_ready()
    Image.init()
    return tuple(e for e in READ_ORDER if PIL_NAMES[e] in Image.OPEN)


@lru_cache(maxsize=1)
def writable() -> tuple[str, ...]:
    Image.init()
    return tuple(e for e in WRITE_ORDER if PIL_NAMES[e] in Image.SAVE)


# ---- helpers shared with other backends ------------------------------------------------


def flatten(im: Image.Image, background=(255, 255, 255)) -> Image.Image:
    """Drop alpha by compositing on white (JPEG, BMP and PDF have no transparency)."""
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        out = Image.new("RGB", rgba.size, background)
        out.paste(rgba, mask=rgba.getchannel("A"))
        return out
    return im if im.mode == "RGB" else im.convert("RGB")


def _rgb_or_rgba(im: Image.Image) -> Image.Image:
    if im.mode in ("RGB", "RGBA"):
        return im
    has_alpha = im.mode in ("LA", "PA") or "transparency" in im.info
    return im.convert("RGBA" if has_alpha else "RGB")


def _quantize(im: Image.Image) -> Image.Image:
    if im.mode == "P":
        return im
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        return im.convert("RGBA").quantize(256, method=Image.Quantize.FASTOCTREE)
    return im.convert("RGB").quantize(256, method=Image.Quantize.MEDIANCUT)


def save_image(
    im: Image.Image,
    dest: Path,
    target: str,
    opts: Options,
    *,
    exif: bytes | None = None,
    compress: bool = False,
) -> None:
    """Save one still image in `target` format with sensible per-format settings."""
    params: dict = {}
    icc = im.info.get("icc_profile")
    if icc and target in EXIF_TARGETS:
        params["icc_profile"] = icc
    if exif and target in EXIF_TARGETS:
        params["exif"] = exif
    q = opts.quality

    if target == "jpg":
        quality = min(q, 72) if compress else q
        flatten(im).save(dest, "JPEG", quality=quality, optimize=True, progressive=True, **params)
    elif target == "webp":
        _rgb_or_rgba(im).save(
            dest, "WEBP", quality=min(q, 70) if compress else q, method=6 if compress else 4,
            **params,
        )
    elif target == "avif":
        _rgb_or_rgba(im).save(dest, "AVIF", quality=min(q, 50) if compress else q, **params)
    elif target == "png":
        if compress:
            im = _quantize(im)
        elif im.mode not in ("RGB", "RGBA", "L", "LA", "P", "I", "I;16"):
            im = im.convert("RGBA")
        im.save(dest, "PNG", optimize=True, **params)
    elif target == "gif":
        im = im if im.mode in ("P", "L") else _rgb_or_rgba(im)
        im.save(dest, "GIF", optimize=True)
    elif target == "bmp":
        flatten(im).save(dest, "BMP")
    elif target == "tiff":
        im.save(dest, "TIFF", compression="tiff_lzw", **params)
    elif target == "ico":
        im.convert("RGBA").save(dest, "ICO")
    elif target == "pdf":
        flatten(im).save(dest, "PDF", resolution=float(opts.page_dpi))
    elif target == "tga":
        _rgb_or_rgba(im).save(dest, "TGA")
    else:
        raise ConversionError(f"cannot write {target}")


def strip_info(im: Image.Image) -> Image.Image:
    im.info = {k: v for k, v in im.info.items() if k in KEEP_ON_STRIP}
    return im


def open_upright(path: Path) -> Image.Image:
    """Open a still image, applying its EXIF orientation."""
    _heif_ready()
    with Image.open(path) as im:
        im.load()
        return ImageOps.exif_transpose(im)


# ---- the backend ----------------------------------------------------------------------


class PillowBackend(Backend):
    name = "pillow"
    description = "Images: PNG, JPG, WebP, AVIF, GIF, BMP, TIFF, ICO, image -> PDF"
    requirements = ()
    extras = (Requirement("py:pillow_heif", {"pip": "pillow-heif"}, "HEIC / HEIF photos (iPhone)"),)

    def clear_cache(self) -> None:
        readable.cache_clear()
        writable.cache_clear()

    def potential_pairs(self) -> dict[str, set[str]]:
        read, write = readable(), set(writable())
        pairs: dict[str, set[str]] = {}
        for src in read:
            actions = {t for t in write if t != src} | {"merge-pdf"}
            if src in write:
                actions |= {"resize-50", "rotate-90", "strip"}
            if src in COMPRESSIBLE:
                actions.add("compress")
            pairs[src] = actions
        return pairs

    def run(self, job: Job) -> list[Path]:
        src, action, opts, ctx = job.src, job.action, job.opts, job.ctx
        tool = TOOLS.get(action)
        source_ext = src.suffix.lower().lstrip(".")
        target = action if tool is None else normalize_ext(source_ext)
        name = f"{src.stem}{tool.suffix if tool else ''}.{target}"
        out = out_dir(src, opts)
        transform = _transform(action, opts)
        strip = opts.strip or action == "strip"

        _heif_ready()
        with workdir(out) as tmpdir:
            tmp = tmpdir / name
            try:
                with Image.open(src) as im:
                    frames = getattr(im, "n_frames", 1)
                    if frames > 1 and target in ANIMATED:
                        _save_animated(im, tmp, target, opts, transform, strip, ctx)
                    elif action == "strip" and target == "jpg" and _orientation(im) in (0, 1):
                        strip_info(im)  # re-use the JPEG tables: no visible quality loss
                        im.save(tmp, "JPEG", quality="keep", optimize=True)
                    else:
                        im.load()
                        upright = ImageOps.exif_transpose(im)
                        if strip:
                            strip_info(upright)
                        exif = None if strip else upright.info.get("exif")
                        save_image(
                            transform(upright), tmp, target, opts,
                            exif=exif, compress=action == "compress",
                        )
            except Image.UnidentifiedImageError as exc:
                raise ConversionError("not a readable image (corrupt or wrong extension)") from exc
            except _ERRORS as exc:
                raise ConversionError(f"cannot read image: {exc}") from exc
            if action == "compress":
                keep_smaller(tmp, src)
            ctx.progress(1)
            return [finalize(tmp, out / name, opts.overwrite)]

    def run_batch(
        self, srcs: Sequence[Path], action: str, opts: Options, ctx: Context
    ) -> list[Path]:
        if action != "merge-pdf":
            return super().run_batch(srcs, action, opts, ctx)
        out = out_dir(srcs[0], opts)
        name = f"{srcs[0].stem}{TOOLS['merge-pdf'].suffix}.pdf"
        pages: list[Image.Image] = []
        try:
            for i, path in enumerate(srcs):
                ctx.check()
                pages.append(flatten(_resize(open_upright(path), opts)))
                ctx.progress((i + 1) / (len(srcs) + 1))
        except _ERRORS as exc:
            raise ConversionError(f"cannot read image: {exc}") from exc
        with workdir(out) as tmpdir:
            tmp = tmpdir / name
            pages[0].save(
                tmp, "PDF", save_all=True, append_images=pages[1:], resolution=float(opts.page_dpi)
            )
            ctx.progress(1)
            return [finalize(tmp, out / name, opts.overwrite)]


def _orientation(im: Image.Image) -> int:
    try:
        return int(im.getexif().get(0x0112, 0))
    except Exception:
        return 0


def _resize(im: Image.Image, opts: Options) -> Image.Image:
    if not opts.resize:
        return im
    return im.resize(resized_size(opts.resize, *im.size), Image.Resampling.LANCZOS)


def _transform(action: str, opts: Options) -> Callable[[Image.Image], Image.Image]:
    def apply(im: Image.Image) -> Image.Image:
        im = _resize(im, opts)
        if action == "resize-50":
            im = im.resize(
                (max(1, im.width // 2), max(1, im.height // 2)), Image.Resampling.LANCZOS
            )
        elif action == "rotate-90":
            im = im.transpose(Image.Transpose.ROTATE_270)  # clockwise
        return im

    return apply


def _save_animated(
    im: Image.Image,
    dest: Path,
    target: str,
    opts: Options,
    transform: Callable[[Image.Image], Image.Image],
    strip: bool,
    ctx: Context,
) -> None:
    total = getattr(im, "n_frames", 1)
    frames: list[Image.Image] = []
    durations: list[int] = []
    for i, frame in enumerate(ImageSequence.Iterator(im)):
        ctx.check()
        durations.append(int(frame.info.get("duration", im.info.get("duration", 100)) or 100))
        frames.append(transform(frame.convert("RGBA")))
        ctx.progress(0.8 * (i + 1) / total)

    params: dict = {
        "save_all": True,
        "append_images": frames[1:],
        "duration": durations,
        "loop": im.info.get("loop", 0),
    }
    if not strip and im.info.get("exif") and target in EXIF_TARGETS:
        params["exif"] = im.info["exif"]
    if target == "gif":
        params.update(disposal=2, optimize=False)
    elif target in ("webp", "avif"):
        params["quality"] = opts.quality
    frames[0].save(dest, PIL_NAMES[target], **params)
