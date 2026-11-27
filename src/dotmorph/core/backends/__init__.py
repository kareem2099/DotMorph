"""All conversion backends, in priority order (first one able to do a conversion wins)."""

from __future__ import annotations

from .ffmpeg import FFmpegBackend
from .ghostscript import GhostscriptBackend
from .magick import MagickBackend
from .ocr import OcrBackend
from .office import OfficeBackend
from .pandoc import PandocBackend
from .pillow import PillowBackend
from .poppler import PopplerBackend
from .svg import SvgBackend
from .whisper import WhisperBackend

ALL = [
    PillowBackend(),
    PopplerBackend(),
    GhostscriptBackend(),
    SvgBackend(),
    MagickBackend(),
    FFmpegBackend(),
    WhisperBackend(),
    OcrBackend(),
    OfficeBackend(),
    PandocBackend(),
]

__all__ = ["ALL"]
