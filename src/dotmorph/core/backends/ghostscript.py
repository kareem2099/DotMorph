"""Ghostscript: compress PDFs, merge PDFs (and images) into one, PostScript -> PDF.

Also renders PDF pages when poppler is missing.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Sequence
from pathlib import Path

from ..common import (
    Context,
    ConversionError,
    Job,
    Options,
    finalize,
    keep_smaller,
    last_error_line,
    out_dir,
    run_tool,
    workdir,
)
from ..formats import IMAGE_FORMATS, TOOLS, source_format
from ..registry import Backend, Requirement
from .poppler import collect_pages, page_count

GS = Requirement("gs", {"apt": "ghostscript", "dnf": "ghostscript", "pacman": "ghostscript",
                        "zypper": "ghostscript"}, "compress / merge PDF")
BASE = ["-dNOPAUSE", "-dBATCH", "-dSAFER"]


class GhostscriptBackend(Backend):
    name = "ghostscript"
    description = "PDF compress & merge, PostScript -> PDF"
    requirements = (GS,)

    def potential_pairs(self) -> dict[str, set[str]]:
        return {"pdf": {"compress", "merge-pdf", "png", "jpg"}, "ps": {"pdf", "png"}}

    def _exe(self) -> str:
        exe = shutil.which("gs")
        if exe is None:
            raise ConversionError("ghostscript (gs) not found")
        return exe

    def _pages_progress(self, src: Path, ctx: Context):
        total = page_count(src)

        def on_line(line: str) -> None:
            m = re.match(r"Page (\d+)", line)
            if m and total:
                ctx.progress(0.95 * int(m.group(1)) / total)

        return on_line

    def run(self, job: Job) -> list[Path]:
        src, action, opts, ctx = job.src, job.action, job.opts, job.ctx
        out = out_dir(src, opts)
        with workdir(out) as tmpdir:
            if action in ("png", "jpg"):
                device = ["-sDEVICE=png16m"] if action == "png" else [
                    "-sDEVICE=jpeg", f"-dJPEGQ={opts.quality}"]
                cmd = [self._exe(), *BASE, *device, f"-r{opts.page_dpi}", "-dTextAlphaBits=4",
                       "-dGraphicsAlphaBits=4", f"-sOutputFile={tmpdir / 'page-%03d'}.{action}",
                       str(src)]
                code, err = run_tool(cmd, ctx, timeout=opts.timeout,
                                     on_line=self._pages_progress(src, ctx))
                if code != 0:
                    raise ConversionError(f"ghostscript failed: {last_error_line(err)}")
                return collect_pages(tmpdir, src, action, out, opts.overwrite)

            tool = TOOLS.get(action)
            name = f"{src.stem}{tool.suffix if tool else ''}.pdf"
            tmp = tmpdir / name
            cmd = [self._exe(), *BASE, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5"]
            if action == "compress":
                cmd += ["-dPDFSETTINGS=/ebook", "-dDetectDuplicateImages=true"]
            cmd += [f"-sOutputFile={tmp}", str(src)]
            code, err = run_tool(cmd, ctx, timeout=opts.timeout,
                                 on_line=self._pages_progress(src, ctx))
            if code != 0 or not tmp.exists():
                raise ConversionError(f"ghostscript failed: {last_error_line(err)}")
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
        with workdir(out) as tmpdir:
            inputs: list[str] = []
            for i, path in enumerate(srcs):
                ctx.check()
                if source_format(path) in IMAGE_FORMATS:  # images become one-page PDFs first
                    from .pillow import flatten, open_upright

                    page = tmpdir / f"img-{i:04d}.pdf"
                    try:
                        flatten(open_upright(path)).save(
                            page, "PDF", resolution=float(opts.page_dpi)
                        )
                    except (OSError, ValueError) as exc:
                        raise ConversionError(f"{path.name}: cannot read image: {exc}") from exc
                    inputs.append(str(page))
                else:
                    inputs.append(str(path))
            tmp = tmpdir / name
            cmd = [self._exe(), *BASE, "-dQUIET", "-sDEVICE=pdfwrite", f"-sOutputFile={tmp}",
                   *inputs]
            code, err = run_tool(cmd, ctx, timeout=opts.timeout)
            if code != 0 or not tmp.exists():
                raise ConversionError(f"ghostscript failed: {last_error_line(err)}")
            ctx.progress(1)
            return [finalize(tmp, out / name, opts.overwrite)]
