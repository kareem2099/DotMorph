"""Markup and e-books through pandoc: Markdown, HTML, reST, Org, EPUB, DOCX, ODT.

Markdown -> PDF uses a pandoc PDF engine when one is installed (typst, weasyprint, ...),
otherwise goes Markdown -> DOCX -> PDF through LibreOffice.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..common import ConversionError, Job, finalize, last_error_line, out_dir, run_tool, workdir
from ..registry import Backend, Requirement

PANDOC = Requirement("pandoc", {"apt": "pandoc", "dnf": "pandoc", "pacman": "pandoc-cli",
                                "zypper": "pandoc"}, "Markdown, HTML, EPUB, reST, Org")

PDF_ENGINES = ("typst", "weasyprint", "wkhtmltopdf", "tectonic", "xelatex", "pdflatex")
WRITERS = {"md": "gfm", "txt": "plain", "html": "html5", "docx": "docx", "odt": "odt",
           "epub": "epub3", "pdf": None}

PAIRS = {
    "md": {"html", "docx", "odt", "epub", "txt", "pdf"},
    "rst": {"md", "html", "docx", "odt", "epub", "pdf"},
    "org": {"md", "html", "docx", "odt", "epub", "pdf"},
    "html": {"md", "docx", "odt", "epub", "txt"},
    "docx": {"md", "html", "epub"},
    "odt": {"md", "html", "epub"},
    "epub": {"md", "html", "docx", "txt"},
}


def pdf_engine() -> str | None:
    return next((e for e in PDF_ENGINES if shutil.which(e)), None)


def _office() -> bool:
    return bool(shutil.which("soffice") or shutil.which("libreoffice"))


class PandocBackend(Backend):
    name = "pandoc"
    description = "Markdown, HTML, reST, Org, EPUB <-> DOCX / ODT / HTML / PDF"
    requirements = (PANDOC,)
    extras = (
        Requirement("weasyprint", {"apt": "weasyprint", "dnf": "weasyprint",
                                   "pacman": "python-weasyprint", "zypper": "python3-weasyprint"},
                    "Markdown -> PDF (or have LibreOffice installed)"),
    )

    def potential_pairs(self) -> dict[str, set[str]]:
        return {src: set(targets) for src, targets in PAIRS.items()}

    def pairs(self) -> dict[str, set[str]]:
        if not self.available():
            return {}
        pairs = self.potential_pairs()
        if not (pdf_engine() or _office()):
            for targets in pairs.values():
                targets.discard("pdf")
        return pairs

    def run(self, job: Job) -> list[Path]:
        src, target, opts, ctx = job.src, job.action, job.opts, job.ctx
        out = out_dir(src, opts)
        name = f"{src.stem}.{target}"
        with workdir(out) as tmpdir:
            tmp = tmpdir / name
            if target == "pdf":
                engine = pdf_engine()
                if engine:
                    self._pandoc(job, tmp, ["--pdf-engine", engine])
                elif _office():
                    from .office import office_convert

                    docx = tmpdir / f"{src.stem}.docx"
                    self._pandoc(job, docx, ["-t", "docx"])
                    ctx.progress(0.5)
                    tmp = office_convert(docx, "pdf", tmpdir, ctx, opts.timeout)
                else:
                    raise ConversionError("Markdown -> PDF needs weasyprint, typst or LibreOffice")
            else:
                extra = ["-t", WRITERS[target]]
                if target == "html":
                    extra += ["--metadata", f"pagetitle={src.stem}"]
                self._pandoc(job, tmp, extra)
            ctx.progress(1)
            return [finalize(tmp, out / name, opts.overwrite)]

    def _pandoc(self, job: Job, dest: Path, extra: list[str]) -> None:
        exe = shutil.which("pandoc")
        if exe is None:
            raise ConversionError("pandoc not found")
        src = job.src
        cmd = [exe, str(src), "-o", str(dest), "-s", "--resource-path", str(src.parent), *extra]
        code, err = run_tool(cmd, job.ctx, timeout=job.opts.timeout or 300, cwd=src.parent)
        if code != 0 or not dest.exists():
            raise ConversionError(f"pandoc failed: {last_error_line(err)}")
