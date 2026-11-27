"""OCR through Tesseract: text out of images and scans, and searchable PDFs.

Images -> TXT, the clipboard ("Copy text") or a searchable PDF ("OCR"); scanned PDFs -> a
searchable PDF or the clipboard. ocrmypdf makes the best searchable PDFs (it keeps the
original images and skips pages that already have text) and is used when installed; without
it pages are rendered with pdftoppm, OCR'd one by one and merged with Ghostscript.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from ..common import ConversionError, Job, finalize, last_error_line, out_dir, run_tool, workdir
from ..formats import IMAGE_FORMATS, TOOLS
from ..registry import Backend, Requirement

TESSERACT = Requirement("tesseract", {"apt": "tesseract-ocr", "dnf": "tesseract",
                                      "pacman": "tesseract", "zypper": "tesseract-ocr"},
                        "text from images and scans (OCR)")
OCRMYPDF = Requirement("ocrmypdf", {"apt": "ocrmypdf", "dnf": "ocrmypdf", "pacman": "ocrmypdf",
                                    "zypper": "python3-ocrmypdf", "pip": "ocrmypdf"},
                       "better searchable PDFs")
# Images Tesseract reads directly (via Leptonica); others go through Pillow to PNG first.
DIRECT = {"png", "jpg", "tiff", "bmp", "gif", "webp"}
IMAGE_SOURCES = DIRECT | {"heic", "heif", "avif", "tga", "jxl", "psd"}
# ISO 639-1 (what --lang and the UI use) -> Tesseract language packs.
TESSERACT_LANG = {
    "en": "eng", "ar": "ara", "de": "deu", "fr": "fra", "es": "spa", "it": "ita",
    "pt": "por", "ru": "rus", "tr": "tur", "fa": "fas", "nl": "nld", "pl": "pol",
    "uk": "ukr", "zh": "chi_sim", "ja": "jpn", "ko": "kor", "hi": "hin", "ur": "urd",
}


@lru_cache(maxsize=1)
def installed_languages() -> frozenset[str]:
    exe = shutil.which("tesseract")
    if not exe:
        return frozenset()
    try:
        proc = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    lines = (proc.stdout + proc.stderr).splitlines()
    return frozenset(ln.strip() for ln in lines[1:] if ln.strip() and " " not in ln.strip())


def languages(requested: str | None) -> str:
    """Tesseract's -l value. Explicit: "ar", "ara", "ar+en" ... Default: English plus the
    interface language when its pack is installed. A missing pack names the package."""
    have = installed_languages()
    if requested:
        # "pt-BR" / "pt_BR" -> "pt" -> "por"; Tesseract names ("ara", "chi_sim") pass through
        codes = [TESSERACT_LANG.get(c.strip().replace("_", "-").split("-")[0].lower(), c.strip())
                 for c in requested.split("+") if c.strip()]
        missing = [c for c in codes if have and c not in have]
        if missing:
            pack = missing[0].replace("_", "-")
            raise ConversionError(f"no OCR language pack for {missing[0]}: "
                                  f"install tesseract-ocr-{pack}")
        return "+".join(codes)
    from ...i18n import current

    ui = TESSERACT_LANG.get(current().split("-")[0], "")
    codes = ["eng"] + ([ui] if ui and ui != "eng" and ui in have else [])
    return "+".join(codes)


class OcrBackend(Backend):
    name = "tesseract"
    description = "OCR: images -> text or a searchable PDF, scanned PDFs -> searchable PDF"
    requirements = (TESSERACT,)
    extras = (OCRMYPDF,)

    def clear_cache(self) -> None:
        installed_languages.cache_clear()

    def potential_pairs(self) -> dict[str, set[str]]:
        pairs = {src: {"txt", "copy-text", "ocr"} for src in IMAGE_SOURCES & IMAGE_FORMATS}
        pairs["pdf"] = {"ocr", "copy-text"}
        return pairs

    def pairs(self) -> dict[str, set[str]]:
        if not self.available():
            return {}
        pairs = self.potential_pairs()
        # scanned PDFs need pages rendered first: ocrmypdf, or pdftoppm + gs to merge
        if not (shutil.which("ocrmypdf") or (shutil.which("pdftoppm") and shutil.which("gs"))):
            pairs["pdf"].discard("ocr")
        if not shutil.which("pdftoppm"):
            pairs["pdf"].discard("copy-text")
        return {k: v for k, v in pairs.items() if v}

    def run(self, job: Job) -> list[Path]:
        src, action, opts, ctx = job.src, job.action, job.opts, job.ctx
        lang = languages(opts.language)
        out = out_dir(src, opts)
        is_pdf = src.suffix.lower() == ".pdf"
        with workdir(out) as tmpdir:
            if action == "ocr":
                name = f"{src.stem}{TOOLS['ocr'].suffix}.pdf"
                tmp = tmpdir / name
                if is_pdf:
                    self._pdf_to_searchable(src, tmp, tmpdir, lang, job)
                else:
                    self._tesseract(self._readable(src, tmpdir), tmp.with_suffix(""), lang,
                                    "pdf", job)
            else:
                name = f"{src.stem}.txt"
                tmp = tmpdir / name
                pages = self._pages(src, tmpdir, job) if is_pdf else [self._readable(src, tmpdir)]
                texts = []
                for i, page in enumerate(pages):
                    ctx.check()
                    base = tmpdir / f"text-{i:04d}"
                    self._tesseract(page, base, lang, "txt", job,
                                    span=(i / len(pages), (i + 1) / len(pages)))
                    texts.append(base.with_suffix(".txt").read_text(encoding="utf-8",
                                                                     errors="replace"))
                tmp.write_text("\n\f\n".join(t.strip() for t in texts) + "\n", encoding="utf-8")
                if action == "copy-text":
                    from ...linux.clipboard import copy_text

                    text = tmp.read_text(encoding="utf-8").strip()
                    if not text:
                        raise ConversionError("no text found")
                    if not copy_text(text):
                        raise ConversionError("read the text, but no clipboard tool "
                                              "(wl-copy, xclip)")
            ctx.progress(1)
            return [finalize(tmp, out / name, opts.overwrite)]

    # ---- helpers ------------------------------------------------------------------------

    def _readable(self, src: Path, tmpdir: Path) -> Path:
        """Tesseract reads common formats itself; HEIC, AVIF... go through Pillow first."""
        if src.suffix.lower().lstrip(".").replace("jpeg", "jpg") in DIRECT:
            return src
        from .pillow import flatten, open_upright

        png = tmpdir / "page.png"
        try:
            flatten(open_upright(src)).save(png)
        except (OSError, ValueError) as exc:
            raise ConversionError(f"cannot read image: {exc}") from exc
        return png

    def _tesseract(self, image: Path, base: Path, lang: str, kind: str, job: Job,
                   span: tuple[float, float] = (0.0, 0.95)) -> None:
        exe = shutil.which("tesseract") or "tesseract"
        env = dict(os.environ, OMP_THREAD_LIMIT="1")  # no thread storm on parallel batches
        code, err = run_tool([exe, str(image), str(base), "-l", lang, kind], job.ctx,
                             timeout=job.opts.timeout, env=env)
        if code != 0 or not base.with_suffix(f".{kind}").exists():
            raise ConversionError(f"tesseract failed: {last_error_line(err)}")
        job.ctx.progress(span[1])

    def _pages(self, pdf: Path, tmpdir: Path, job: Job) -> list[Path]:
        exe = shutil.which("pdftoppm")
        if not exe:
            raise ConversionError("pdftoppm not found (poppler-utils)")
        code, err = run_tool([exe, "-r", "300", "-gray", "-png", str(pdf), str(tmpdir / "pg")],
                             job.ctx, timeout=job.opts.timeout)
        pages = sorted(tmpdir.glob("pg-*.png"))
        if code != 0 or not pages:
            raise ConversionError(f"cannot render the PDF: {last_error_line(err)}")
        return pages

    def _pdf_to_searchable(self, src: Path, tmp: Path, tmpdir: Path, lang: str,
                           job: Job) -> None:
        ocrmypdf = shutil.which("ocrmypdf")
        if ocrmypdf:
            code, err = run_tool([ocrmypdf, "--skip-text", "--quiet", "-l", lang, str(src),
                                  str(tmp)], job.ctx, timeout=job.opts.timeout)
            if code == 0 and tmp.exists():
                return
            raise ConversionError(f"ocrmypdf failed: {last_error_line(err)}")
        pages = self._pages(src, tmpdir, job)
        parts = []
        for i, page in enumerate(pages):
            job.ctx.check()
            base = tmpdir / f"ocr-{i:04d}"
            self._tesseract(page, base, lang, "pdf", job,
                            span=(0, 0.9 * (i + 1) / len(pages)))
            parts.append(str(base.with_suffix(".pdf")))
        gs = shutil.which("gs") or "gs"
        code, err = run_tool([gs, "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dQUIET",
                              "-sDEVICE=pdfwrite", f"-sOutputFile={tmp}", *parts], job.ctx,
                             timeout=job.opts.timeout)
        if code != 0 or not tmp.exists():
            raise ConversionError(f"ghostscript failed: {last_error_line(err)}")
