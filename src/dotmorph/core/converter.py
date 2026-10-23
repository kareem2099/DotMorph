"""Conversion engine entry points: pick a backend, run it, batch with progress and cancel."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from . import registry
from .common import (
    Cancelled,
    Context,
    ConversionError,
    Job,
    MissingDependencyError,
    Options,
)
from .formats import IMAGE_FORMATS, is_batch, normalize_ext, source_format

__all__ = [
    "BatchResult",
    "Cancelled",
    "ConversionError",
    "MissingDependencyError",
    "Options",
    "convert",
    "convert_many",
]


@dataclass
class BatchResult:
    outputs: list[Path] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors and not self.cancelled


def _unsupported(fmt: str, action: str) -> ConversionError:
    missing = registry.missing_for(fmt, action)
    if missing:
        tools = ", ".join(r.name for r in missing)
        return MissingDependencyError(
            f"{fmt} -> {action} needs {tools}. Install: {missing[0].install}"
        )
    return ConversionError(f"cannot convert {fmt or 'this file'} to {action}")


def convert(
    src: Path | str,
    target: str,
    opts: Options | None = None,
    *,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> list[Path]:
    """Convert one file. Returns the created files (a PDF can yield one per page).

    `target` is a format ("webp") or a tool ("compress", "resize-50", ...).
    """
    src = Path(src)
    opts = opts or Options()
    action = normalize_ext(target)

    if not src.is_file():
        raise ConversionError("file not found")
    fmt = source_format(src)
    backend = registry.backend_for(fmt, action)
    if backend is None:
        raise _unsupported(fmt, action)

    ctx = Context(on_progress, cancel)
    ctx.check()
    try:
        if is_batch(action):
            return backend.run_batch([src], action, opts, ctx)
        return backend.run(Job(src, action, opts, ctx))
    except Cancelled:
        raise
    except ConversionError as exc:  # tools love quoting the full path: keep the name only
        message = str(exc).replace(str(src.resolve()), src.name).replace(str(src), src.name)
        raise type(exc)(message) from exc


def _batch_backend(paths: Sequence[Path], action: str) -> registry.Backend:
    """merge-pdf over mixed files: a PDF-capable backend must take the lead."""
    formats = [source_format(p) for p in paths]
    lead = next((f for f in formats if f not in IMAGE_FORMATS), formats[0])
    for fmt in formats:
        if registry.backend_for(fmt, action) is None:
            raise _unsupported(fmt, action)
    backend = registry.backend_for(lead, action)
    assert backend is not None
    return backend


def default_jobs() -> int:
    return max(1, min(8, os.cpu_count() or 1))


def convert_many(
    paths: Sequence[Path | str],
    target: str,
    opts: Options | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    *,
    jobs: int = 1,
    cancel: threading.Event | None = None,
    on_fraction: Callable[[float], None] | None = None,
) -> BatchResult:
    """Convert several files; one failure never aborts the rest.

    on_progress(done, total) fires as each file finishes; on_fraction(0..1) gives smooth
    overall progress including partial work inside long files. `jobs` > 1 converts files
    in parallel (outputs keep the input order).
    """
    opts = opts or Options()
    action = normalize_ext(target)
    items = [Path(p) for p in paths]
    result = BatchResult()
    total = len(items)
    if total == 0:
        return result

    lock = threading.Lock()
    partial = [0.0] * total
    done = 0

    def report_fraction() -> None:
        if on_fraction:
            on_fraction(sum(partial) / total)

    if is_batch(action):
        try:
            missing = [p for p in items if not p.is_file()]
            if missing:
                raise ConversionError(f"file not found: {missing[0].name}")
            backend = _batch_backend(items, action)
            ctx = Context(lambda f: on_fraction and on_fraction(f), cancel)
            result.outputs.extend(backend.run_batch(items, action, opts, ctx))
        except Cancelled:
            result.cancelled = True
        except ConversionError as exc:
            result.errors.append((items[0], str(exc)))
        if on_progress:
            on_progress(total, total)
        return result

    per_file: list[list[Path]] = [[] for _ in items]
    errors: dict[int, str] = {}

    def work(index: int) -> None:
        nonlocal done

        def step(fraction: float) -> None:
            with lock:
                partial[index] = fraction
                report_fraction()

        try:
            per_file[index] = convert(items[index], action, opts, on_progress=step, cancel=cancel)
        except Cancelled:
            result.cancelled = True
        except ConversionError as exc:
            errors[index] = str(exc)
        except Exception as exc:  # a bug in one backend must not kill the batch
            errors[index] = f"unexpected error: {exc}"
        with lock:
            partial[index] = 1.0
            done += 1
            if on_progress:
                on_progress(done, total)
            report_fraction()

    if jobs <= 1 or total == 1:
        for i in range(total):
            if cancel is not None and cancel.is_set():
                result.cancelled = True
                break
            work(i)
    else:
        with ThreadPoolExecutor(max_workers=min(jobs, total), thread_name_prefix="dotmorph") as ex:
            futures = [ex.submit(_guarded, work, i, cancel) for i in range(total)]
            for future in as_completed(futures):
                if future.result():
                    result.cancelled = True

    for i, outputs in enumerate(per_file):
        result.outputs.extend(outputs)
        if i in errors:
            result.errors.append((items[i], errors[i]))
    return result


def _guarded(work: Callable[[int], None], index: int, cancel: threading.Event | None) -> bool:
    """Skip queued files once cancelled. Returns True if skipped."""
    if cancel is not None and cancel.is_set():
        return True
    work(index)
    return False


# ---- dry run --------------------------------------------------------------------------


@dataclass
class PlannedStep:
    src: Path
    backend: str = ""
    output: str = ""  # predicted name, e.g. "out/report-NNN.png" for multi-page PDFs
    error: str = ""


def plan(
    paths: Sequence[Path | str], target: str, opts: Options | None = None
) -> list[PlannedStep]:
    """What `convert_many` would do, without touching any file."""
    from .formats import TOOLS

    opts = opts or Options()
    action = normalize_ext(target)
    items = [Path(p) for p in paths]
    steps: list[PlannedStep] = []
    if is_batch(action):
        try:
            missing = [p for p in items if not p.is_file()]
            if missing:
                raise ConversionError(f"file not found: {missing[0].name}")
            backend = _batch_backend(items, action)
            out = opts.out_dir or items[0].parent
            name = f"{items[0].stem}{TOOLS[action].suffix}.pdf"
            return [PlannedStep(p, backend.name, str(out / name)) for p in items]
        except ConversionError as exc:
            return [PlannedStep(p, error=str(exc)) for p in items]

    for src in items:
        step = PlannedStep(src)
        fmt = source_format(src)
        if not src.is_file():
            step.error = "file not found"
        elif (backend := registry.backend_for(fmt, action)) is None:
            step.error = str(_unsupported(fmt, action))
        else:
            tool = TOOLS.get(action)
            ext = fmt if tool else action
            stem = f"{src.stem}{tool.suffix if tool else ''}"
            if fmt in ("pdf", "ps") and ext in ("png", "jpg", "webp"):
                stem += "[-NNN]"  # one file per page when there are several
            step.backend = backend.name
            step.output = str((opts.out_dir or src.parent) / f"{stem}.{ext}")
        steps.append(step)
    return steps
