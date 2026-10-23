"""SVG through librsvg + cairo, called directly with ctypes.

librsvg is the SVG renderer of GNOME / GTK, so it is already on practically every Linux
desktop, and it gets text, letter-spacing, strokes and gradients right where ImageMagick's
built-in renderer does not. PDF output stays vector (cairo PDF surface); raster output is
rendered at `vector_dpi` (96 = original size) and saved by Pillow.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import threading
from functools import lru_cache
from pathlib import Path

from PIL import Image

from ..common import ConversionError, Job, finalize, out_dir, resized_size, workdir
from ..registry import Backend, Requirement

TARGETS = {"png", "jpg", "webp", "avif", "gif", "bmp", "tiff", "ico", "pdf"}
RSVG = Requirement("lib:rsvg-2", {"apt": "librsvg2-2", "dnf": "librsvg2", "pacman": "librsvg",
                                 "zypper": "librsvg-2-2"}, "accurate SVG rendering")
CAIRO_FORMAT_ARGB32 = 0
PX_TO_PT = 72 / 96

_lock = threading.Lock()  # librsvg/cairo are fine per handle, but fonts setup is shared


class _GError(ctypes.Structure):
    _fields_ = [("domain", ctypes.c_uint32), ("code", ctypes.c_int), ("message", ctypes.c_char_p)]


class _Rect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double),
                ("width", ctypes.c_double), ("height", ctypes.c_double)]


class _Dimensions(ctypes.Structure):
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int),
                ("em", ctypes.c_double), ("ex", ctypes.c_double)]


class _Libs:
    def __init__(self) -> None:
        def load(name: str, fallback: str) -> ctypes.CDLL:
            return ctypes.CDLL(ctypes.util.find_library(name) or fallback)

        self.rsvg = load("rsvg-2", "librsvg-2.so.2")
        self.cairo = load("cairo", "libcairo.so.2")
        self.gobject = load("gobject-2.0", "libgobject-2.0.so.0")
        self.glib = load("glib-2.0", "libglib-2.0.so.0")
        vp, d, i = ctypes.c_void_p, ctypes.c_double, ctypes.c_int
        perr = ctypes.POINTER(ctypes.POINTER(_GError))

        r = self.rsvg
        r.rsvg_handle_new_from_file.restype = vp
        r.rsvg_handle_new_from_file.argtypes = [ctypes.c_char_p, perr]
        r.rsvg_handle_set_dpi.argtypes = [vp, d]
        r.rsvg_handle_get_intrinsic_size_in_pixels.restype = i
        r.rsvg_handle_get_intrinsic_size_in_pixels.argtypes = [vp, ctypes.POINTER(d),
                                                               ctypes.POINTER(d)]
        r.rsvg_handle_get_dimensions.argtypes = [vp, ctypes.POINTER(_Dimensions)]
        r.rsvg_handle_render_document.restype = i
        r.rsvg_handle_render_document.argtypes = [vp, vp, ctypes.POINTER(_Rect), perr]

        c = self.cairo
        c.cairo_image_surface_create.restype = vp
        c.cairo_image_surface_create.argtypes = [i, i, i]
        c.cairo_pdf_surface_create.restype = vp
        c.cairo_pdf_surface_create.argtypes = [ctypes.c_char_p, d, d]
        c.cairo_create.restype = vp
        c.cairo_create.argtypes = [vp]
        c.cairo_status.restype = i
        c.cairo_status.argtypes = [vp]
        c.cairo_surface_write_to_png.restype = i
        c.cairo_surface_write_to_png.argtypes = [vp, ctypes.c_char_p]
        for fn in ("cairo_destroy", "cairo_surface_finish", "cairo_surface_destroy"):
            getattr(c, fn).argtypes = [vp]
        self.gobject.g_object_unref.argtypes = [vp]
        self.glib.g_error_free.argtypes = [ctypes.POINTER(_GError)]

    def take_error(self, err: ctypes.POINTER(_GError), what: str) -> ConversionError:
        message = what
        if err:
            raw = err.contents.message
            message = f"{what}: {raw.decode(errors='replace')}" if raw else what
            self.glib.g_error_free(err)
        return ConversionError(message)


@lru_cache(maxsize=1)
def _libs() -> _Libs | None:
    try:
        return _Libs()
    except (OSError, AttributeError):  # library missing, or librsvg older than 2.52
        return None


def render(src: Path, dest: Path, *, scale: float = 1.0, pdf: bool = False) -> tuple[int, int]:
    """Render `src` to a PNG (or vector PDF) at `dest`. Returns the CSS pixel size."""
    libs = _libs()
    if libs is None:
        raise ConversionError("librsvg not available")
    rsvg, cairo = libs.rsvg, libs.cairo
    with _lock:
        err = ctypes.POINTER(_GError)()
        handle = rsvg.rsvg_handle_new_from_file(str(src).encode(), ctypes.byref(err))
        if not handle:
            raise libs.take_error(err, "not a valid SVG")
        try:
            rsvg.rsvg_handle_set_dpi(handle, 96.0)
            w, h = ctypes.c_double(), ctypes.c_double()
            if not rsvg.rsvg_handle_get_intrinsic_size_in_pixels(
                handle, ctypes.byref(w), ctypes.byref(h)
            ):  # only a viewBox: fall back to librsvg's own estimate
                dims = _Dimensions()
                rsvg.rsvg_handle_get_dimensions(handle, ctypes.byref(dims))
                w.value, h.value = float(dims.width), float(dims.height)
            if w.value <= 0 or h.value <= 0:
                raise ConversionError("SVG has no size")

            if pdf:
                out_w, out_h = w.value * PX_TO_PT, h.value * PX_TO_PT
                surface = cairo.cairo_pdf_surface_create(str(dest).encode(), out_w, out_h)
            else:
                out_w, out_h = max(1, round(w.value * scale)), max(1, round(h.value * scale))
                if out_w * out_h > 400_000_000:
                    raise ConversionError("output would be too large; lower --dpi")
                surface = cairo.cairo_image_surface_create(CAIRO_FORMAT_ARGB32, out_w, out_h)
            cr = cairo.cairo_create(surface)
            try:
                viewport = _Rect(0, 0, out_w, out_h)
                err = ctypes.POINTER(_GError)()
                if not rsvg.rsvg_handle_render_document(
                    handle, cr, ctypes.byref(viewport), ctypes.byref(err)
                ):
                    raise libs.take_error(err, "librsvg could not render this SVG")
                if pdf:
                    cairo.cairo_surface_finish(surface)
                elif cairo.cairo_surface_write_to_png(surface, str(dest).encode()) != 0:
                    raise ConversionError("cairo could not write the PNG")
            finally:
                cairo.cairo_destroy(cr)
                cairo.cairo_surface_destroy(surface)
        finally:
            libs.gobject.g_object_unref(handle)
    return round(w.value), round(h.value)


class SvgBackend(Backend):
    name = "librsvg"
    description = "SVG -> PNG, JPG, WebP, ... and vector PDF (accurate text & strokes)"
    requirements = (RSVG,)

    def available(self) -> bool:
        return _libs() is not None

    def potential_pairs(self) -> dict[str, set[str]]:
        return {"svg": set(TARGETS)}

    def pairs(self) -> dict[str, set[str]]:
        if not self.available():
            return {}
        from .pillow import writable

        return {"svg": (TARGETS & set(writable())) | {"pdf"}}

    def run(self, job: Job) -> list[Path]:
        from .pillow import save_image

        src, target, opts, ctx = job.src, job.action, job.opts, job.ctx
        out = out_dir(src, opts)
        name = f"{src.stem}.{target}"
        with workdir(out) as tmpdir:
            tmp = tmpdir / name
            if target == "pdf":
                render(src, tmp, pdf=True)
            else:
                raster = tmpdir / "render.png"
                render(src, raster, scale=opts.vector_dpi / 96)
                ctx.progress(0.7)
                with Image.open(raster) as im:
                    im.load()
                    if opts.resize:
                        im = im.resize(resized_size(opts.resize, *im.size),
                                       Image.Resampling.LANCZOS)
                    save_image(im, tmp, target, opts)
            ctx.progress(1)
            return [finalize(tmp, out / name, opts.overwrite)]
