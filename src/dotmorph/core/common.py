"""Shared plumbing for every backend: options, errors, progress/cancel, safe output files."""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path


class ConversionError(Exception):
    """A single file could not be converted."""


class MissingDependencyError(ConversionError):
    """An external tool (e.g. pdftoppm) is not installed."""


class Cancelled(ConversionError):
    """The user cancelled the job."""

    def __init__(self) -> None:
        super().__init__("cancelled")


@dataclass(frozen=True)
class Options:
    out_dir: Path | None = None  # default: next to the source file
    dpi: int | None = None  # rasterisation resolution; None = per-format default (below)
    quality: int = 90  # JPEG / WebP / AVIF quality (1-100)
    overwrite: bool = False  # otherwise "name (1).ext"
    resize: str | None = None  # "50%", "1920x1080" (fit inside) or "1280" (width)
    strip: bool = False  # drop EXIF / tags while converting
    timeout: float | None = None  # per external tool call, seconds

    @property
    def page_dpi(self) -> int:
        """PDF pages: 150 dpi reads well on screen without huge files."""
        return self.dpi or 150

    @property
    def vector_dpi(self) -> int:
        """SVG and other vector art: 96 dpi is 1 CSS pixel = 1 output pixel."""
        return self.dpi or 96


@dataclass
class Context:
    """Progress reporting and cancellation for one file."""

    on_progress: Callable[[float], None] | None = None
    cancel: threading.Event | None = None

    def progress(self, fraction: float) -> None:
        if self.on_progress:
            self.on_progress(min(1.0, max(0.0, fraction)))

    def check(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled()

    @property
    def cancelled(self) -> bool:
        return self.cancel is not None and self.cancel.is_set()


@dataclass
class Job:
    src: Path
    action: str
    opts: Options
    ctx: Context = field(default_factory=Context)


# ---- running external tools ---------------------------------------------------------


def last_error_line(text: str, fallback: str = "unknown error") -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else fallback


def _kill_group(proc: subprocess.Popen) -> None:
    # Partial output is thrown away anyway, so don't wait long for a graceful exit
    # (ffmpeg flushing its encoder on SIGTERM can take seconds).
    for sig, grace in ((signal.SIGTERM, 0.4), (signal.SIGKILL, 2)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue


def run_tool(
    cmd: Sequence[str],
    ctx: Context | None = None,
    *,
    timeout: float | None = None,
    on_line: Callable[[str], None] | None = None,
    on_tick: Callable[[], None] | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Run a command, honouring cancel and timeout. Returns (returncode, stderr).

    `on_line` receives stdout lines as they arrive (ffmpeg -progress), `on_tick` is called
    about ten times a second (used to watch output files appear).
    The tool runs in its own process group so helpers it spawns die with it.
    """
    ctx = ctx or Context()
    ctx.check()
    proc = subprocess.Popen(
        list(cmd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if on_line else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        cwd=cwd,
        env=env,
        start_new_session=True,
    )
    err_chunks: list[str] = []

    def pump_err() -> None:
        assert proc.stderr is not None
        for chunk in proc.stderr:
            err_chunks.append(chunk)
            if len(err_chunks) > 400:  # keep only the tail
                del err_chunks[:200]

    def pump_out() -> None:
        assert proc.stdout is not None and on_line is not None
        for line in proc.stdout:
            on_line(line.rstrip("\n"))

    threads = [threading.Thread(target=pump_err, daemon=True)]
    if on_line:
        threads.append(threading.Thread(target=pump_out, daemon=True))
    for t in threads:
        t.start()

    deadline = time.monotonic() + timeout if timeout else None
    while True:
        try:
            proc.wait(timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            pass
        if on_tick:
            on_tick()
        if ctx.cancelled:
            _kill_group(proc)
            raise Cancelled()
        if deadline and time.monotonic() > deadline:
            _kill_group(proc)
            raise ConversionError(f"{Path(cmd[0]).name} timed out after {timeout:.0f}s")

    for t in threads:
        t.join(timeout=2)
    return proc.returncode, "".join(err_chunks)


def require(tool: str, package_hint: str) -> str:
    exe = shutil.which(tool)
    if exe is None:
        raise MissingDependencyError(f"{tool} not found. {package_hint}")
    return exe


# ---- output files -------------------------------------------------------------------

_finalize_lock = threading.Lock()


def unique(path: Path, overwrite: bool) -> Path:
    if overwrite or not path.exists():
        return path
    n = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def out_dir(src: Path, opts: Options) -> Path:
    out = opts.out_dir or src.parent
    out.mkdir(parents=True, exist_ok=True)
    return out


@contextmanager
def workdir(out: Path) -> Iterator[Path]:
    """Hidden scratch dir inside the output dir: same filesystem, so the final move is a
    rename, big videos don't fill a tmpfs /tmp, and half-written files never show up."""
    with tempfile.TemporaryDirectory(prefix=".dotmorph-", dir=out) as tmp:
        yield Path(tmp)


def finalize(tmp: Path, dest: Path, overwrite: bool) -> Path:
    """Move a finished temp file to its final name. The name is picked under a lock so
    parallel jobs never claim the same 'name (1).ext'."""
    with _finalize_lock:
        final = unique(dest, overwrite)
        shutil.move(str(tmp), final)
    return final


def keep_smaller(tmp: Path, src: Path) -> None:
    """For 'compress': never hand back a file bigger than the original."""
    if tmp.stat().st_size >= src.stat().st_size:
        shutil.copyfile(src, tmp)


# ---- resize specs -------------------------------------------------------------------

_RESIZE = re.compile(r"^\s*(?:(\d+(?:\.\d+)?)\s*%|(\d+)\s*[xX×]\s*(\d+)|(\d+))\s*$")


def parse_resize(spec: str) -> tuple[str, float, int, int]:
    """'50%' -> ('pct', 50, 0, 0); '1920x1080' -> ('box', 0, 1920, 1080); '1280' -> ('w', ...)."""
    m = _RESIZE.match(spec or "")
    if not m:
        raise ConversionError(f"bad resize value {spec!r} (use 50%, 1920x1080 or 1280)")
    pct, bw, bh, w = m.groups()
    if pct:
        value = float(pct)
        if not 0 < value <= 1000:
            raise ConversionError("resize percent must be between 0 and 1000")
        return "pct", value, 0, 0
    if bw:
        return "box", 0.0, int(bw), int(bh)
    return "w", 0.0, int(w), 0


def resized_size(spec: str, width: int, height: int) -> tuple[int, int]:
    kind, pct, a, b = parse_resize(spec)
    if kind == "pct":
        scale = pct / 100
    elif kind == "box":
        scale = min(a / width, b / height)
    else:
        scale = a / width
    return max(1, round(width * scale)), max(1, round(height * scale))
