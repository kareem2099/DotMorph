"""PDF through poppler: pdftoppm (pages -> images) and pdftotext."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from ..common import ConversionError, Job, finalize, last_error_line, out_dir, run_tool, workdir
from ..registry import Backend, Requirement

POPPLER = {"apt": "poppler-utils", "dnf": "poppler-utils", "pacman": "poppler",
           "zypper": "poppler-tools"}


def page_count(pdf: Path) -> int:
    """Number of pages, or 0 when pdfinfo is missing or the file is odd."""
    exe = shutil.which("pdfinfo")
    if not exe:
        return 0
    try:
        proc = subprocess.run([exe, str(pdf)], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    m = re.search(r"^Pages:\s+(\d+)", proc.stdout, re.MULTILINE)
    return int(m.group(1)) if m else 0


def collect_pages(
    tmpdir: Path, src: Path, target: str, out: Path, overwrite: bool, pattern: str = "page-*"
) -> list[Path]:
    """Move rendered pages to their final names: report.png, or report-001.png ..."""
    pages = sorted(tmpdir.glob(pattern), key=lambda p: int(re.findall(r"\d+", p.stem)[-1]))
    if not pages:
        raise ConversionError("PDF produced no pages")
    results = []
    for index, page in enumerate(pages, start=1):
        name = f"{src.stem}.{target}" if len(pages) == 1 else f"{src.stem}-{index:03d}.{target}"
        results.append(finalize(page, out / name, overwrite))
    return results


class PopplerBackend(Backend):
    name = "poppler"
    description = "PDF -> PNG / JPG / WebP (one image per page), PDF -> text"
    requirements = (
        Requirement("pdftoppm", POPPLER, "render PDF pages"),
        Requirement("pdftotext", POPPLER, "extract PDF text"),
    )

    def available(self) -> bool:
        return any(r.present() for r in self.requirements)

    def potential_pairs(self) -> dict[str, set[str]]:
        return {"pdf": {"png", "jpg", "webp", "txt"}}

    def pairs(self) -> dict[str, set[str]]:
        actions = set()
        if shutil.which("pdftoppm"):
            actions |= {"png", "jpg", "webp"}
        if shutil.which("pdftotext"):
            actions.add("txt")
        return {"pdf": actions} if actions else {}

    def run(self, job: Job) -> list[Path]:
        if job.action == "txt":
            return self._text(job)
        return self._render(job)

    def _text(self, job: Job) -> list[Path]:
        src, opts = job.src, job.opts
        out = out_dir(src, opts)
        with workdir(out) as tmpdir:
            tmp = tmpdir / f"{src.stem}.txt"
            code, err = run_tool(
                [shutil.which("pdftotext") or "pdftotext", "-layout", "-enc", "UTF-8",
                 str(src), str(tmp)],
                job.ctx, timeout=opts.timeout,
            )
            if code != 0 or not tmp.exists():
                raise ConversionError(f"pdftotext failed: {last_error_line(err)}")
            job.ctx.progress(1)
            return [finalize(tmp, out / tmp.name, opts.overwrite)]

    def _render(self, job: Job) -> list[Path]:
        src, target, opts, ctx = job.src, job.action, job.opts, job.ctx
        exe = shutil.which("pdftoppm")
        if exe is None:
            raise ConversionError("pdftoppm not found")
        jpeg = target == "jpg"
        cmd = [exe, "-r", str(opts.page_dpi), "-jpeg" if jpeg else "-png"]
        if jpeg:
            cmd += ["-jpegopt", f"quality={opts.quality}"]
        out = out_dir(src, opts)
        total = page_count(src)

        with workdir(out) as tmpdir:
            cmd += [str(src), str(tmpdir / "page")]

            def tick() -> None:
                if total:
                    done = sum(1 for _ in tmpdir.glob("page-*"))
                    ctx.progress(0.9 * max(0, done - 1) / total)

            code, err = run_tool(cmd, ctx, timeout=opts.timeout, on_tick=tick)
            if code != 0:
                raise ConversionError(f"pdftoppm failed: {last_error_line(err)}")

            if target == "webp":
                from .pillow import save_image

                for page in sorted(tmpdir.glob("page-*.png")):
                    ctx.check()
                    with Image.open(page) as im:
                        save_image(im, page.with_suffix(".webp"), "webp", opts)
                    page.unlink()
            results = collect_pages(tmpdir, src, target, out, opts.overwrite)
            ctx.progress(1)
            return results
