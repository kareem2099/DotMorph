"""Office documents through LibreOffice in headless mode.

Uses its own profile under ~/.cache/dotmorph so it works while LibreOffice is open, and
runs one conversion at a time (LibreOffice can't share a profile between processes).
"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

from ..common import (
    Context,
    ConversionError,
    Job,
    finalize,
    last_error_line,
    out_dir,
    run_tool,
    workdir,
)
from ..registry import Backend, Requirement

SOFFICE = Requirement("soffice", {"apt": "libreoffice", "dnf": "libreoffice",
                                  "pacman": "libreoffice-fresh", "zypper": "libreoffice"},
                      "Word, Excel, PowerPoint, ODF -> PDF and back")

TEXT = {"docx", "doc", "odt", "rtf"}
SLIDES = {"pptx", "ppt", "odp"}
SHEETS = {"xlsx", "xls", "ods", "csv"}

FILTERS = {
    "pdf": "pdf",
    "docx": "docx:MS Word 2007 XML",
    "odt": "odt",
    "txt": "txt:Text (encoded):UTF8",
    "pptx": "pptx:Impress MS PowerPoint 2007 XML",
    "odp": "odp",
    "xlsx": "xlsx:Calc MS Excel 2007 XML",
    "ods": "ods",
    "csv": "csv:Text - txt - csv (StarCalc):44,34,76,1",
}

_lock = threading.Lock()


def _exe() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def _profile() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    path = base / "dotmorph" / "lo-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


class OfficeBackend(Backend):
    name = "libreoffice"
    description = "DOCX, ODT, RTF, PPTX, XLSX, CSV, HTML, TXT -> PDF and between Office formats"
    requirements = (SOFFICE,)

    def available(self) -> bool:
        return _exe() is not None

    def potential_pairs(self) -> dict[str, set[str]]:
        pairs: dict[str, set[str]] = {}
        for src in TEXT:
            pairs[src] = {"pdf", "docx", "odt", "txt"} - {src}
        for src in SLIDES:
            pairs[src] = {"pdf", "pptx", "odp"} - {src}
        for src in SHEETS:
            pairs[src] = {"pdf", "xlsx", "ods", "csv"} - {src}
        pairs["txt"] = {"pdf", "docx", "odt"}
        pairs["html"] = {"pdf", "odt", "docx"}
        return pairs

    def run(self, job: Job) -> list[Path]:
        src, target, opts, ctx = job.src, job.action, job.opts, job.ctx
        out = out_dir(src, opts)
        with workdir(out) as tmpdir:
            produced = office_convert(src, target, tmpdir, ctx, opts.timeout)
            ctx.progress(1)
            return [finalize(produced, out / f"{src.stem}.{target}", opts.overwrite)]


def office_convert(
    src: Path, target: str, dest_dir: Path, ctx: Context, timeout: float | None = None
) -> Path:
    """Convert `src` into `dest_dir` with LibreOffice; returns the produced file."""
    exe = _exe()
    if exe is None:
        raise ConversionError("LibreOffice not found")
    cmd = [
        exe, "--headless", "--norestore", "--nologo", "--nolockcheck",
        f"-env:UserInstallation={_profile().as_uri()}",
        "--convert-to", FILTERS[target], "--outdir", str(dest_dir), str(src),
    ]
    with _lock:
        ctx.check()
        _, err = run_tool(cmd, ctx, timeout=timeout or 300)
    produced = dest_dir / f"{src.stem}.{target}"
    if produced.exists():
        return produced
    candidates = [p for p in dest_dir.iterdir() if p.suffix == f".{target}"]
    if not candidates:
        raise ConversionError(f"LibreOffice failed: {last_error_line(err)}")
    return candidates[0]
