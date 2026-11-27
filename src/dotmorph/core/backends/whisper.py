"""Speech to text through whisper.cpp (`whisper-cli`), fully offline.

Audio or video in; plain text, SRT or VTT subtitles out, or the transcript straight onto the
clipboard ("Copy text"). ffmpeg first extracts the audio as 16 kHz mono WAV, which is what
Whisper expects. The model is a separate download (`dotmorph whisper --download base`): the
backend only shows up once whisper-cli, ffmpeg and a model are all there.
"""

from __future__ import annotations

import os
import re
import shutil
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...linux.paths import data_home
from ..common import ConversionError, Job, finalize, last_error_line, out_dir, run_tool, workdir
from ..formats import AUDIO_FORMATS, VIDEO_FORMATS
from ..registry import Backend, Requirement
from .ffmpeg import FFMPEG

WHISPER = Requirement("whisper-cli", {"apt": "whisper.cpp-tools", "dnf": "whisper-cpp",
                                      "pacman": "whisper.cpp", "zypper": "whisper-cpp"},
                      "speech to text")
TARGETS = {"txt", "srt", "vtt", "copy-text"}
OUTPUT_FLAG = {"txt": "-otxt", "srt": "-osrt", "vtt": "-ovtt", "copy-text": "-otxt"}

# Multilingual ggml models from the whisper.cpp project (size in MB). "base" is the default:
# good enough for clear speech in most languages, fast on a laptop CPU.
MODELS = {"tiny": 75, "base": 142, "small": 466, "medium": 1500, "large-v3-turbo": 1600}
DEFAULT_MODEL = "base"
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{name}.bin"
_PROGRESS = re.compile(r"progress\s*=\s*(\d+)%")


def models_dir() -> Path:
    return data_home() / "dotmorph" / "whisper"


def installed_models() -> dict[str, Path]:
    """Models DotMorph can use, best first: its own folder, then a system one."""
    found: dict[str, Path] = {}
    for folder in (models_dir(), Path("/usr/share/whisper.cpp/models")):
        for name in sorted(MODELS, key=lambda n: -MODELS[n]):
            path = folder / f"ggml-{name}.bin"
            if path.is_file() and name not in found:
                found[name] = path
    return found


def find_model() -> Path | None:
    """$DOTMORPH_WHISPER_MODEL, else the default model, else the best one installed."""
    env = os.environ.get("DOTMORPH_WHISPER_MODEL")
    if env:
        return Path(env) if Path(env).is_file() else None
    models = installed_models()
    return models.get(DEFAULT_MODEL) or next(iter(models.values()), None)


@dataclass(frozen=True)
class ModelRequirement(Requirement):
    """A Whisper model file rather than a program; installed by `dotmorph whisper`."""

    def present(self) -> bool:
        return find_model() is not None

    @property
    def install(self) -> str:
        return f"dotmorph whisper --download {DEFAULT_MODEL}"


MODEL = ModelRequirement("whisper model", {}, f"speech model (~{MODELS[DEFAULT_MODEL]} MB)")


def download(name: str, on_progress: Callable[[int, int], None] | None = None) -> Path:
    """Fetch ggml-<name>.bin into models_dir(); a .part file until it's complete."""
    if name not in MODELS:
        raise ValueError(f"unknown model {name!r}; choose from {', '.join(MODELS)}")
    dest = models_dir() / f"ggml-{name}.bin"
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".bin.part")
    with urllib.request.urlopen(MODEL_URL.format(name=name), timeout=60) as resp, \
            open(part, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done, total)
    if total and part.stat().st_size != total:
        part.unlink(missing_ok=True)
        raise OSError("download incomplete")
    part.replace(dest)
    return dest


def spoken(language: str | None) -> str:
    """whisper-cli's -l: one ISO 639-1 code ("pt-BR" -> "pt", "ar+en" -> "ar"), or auto."""
    if not language:
        return "auto"
    first = language.split("+")[0].strip().replace("_", "-").split("-")[0].lower()
    return first or "auto"


class WhisperBackend(Backend):
    name = "whisper"
    description = "Audio / video -> text, SRT, VTT, or straight to the clipboard (offline)"
    requirements = (WHISPER, FFMPEG, MODEL)

    def potential_pairs(self) -> dict[str, set[str]]:
        return {src: set(TARGETS) for src in AUDIO_FORMATS | VIDEO_FORMATS}

    def run(self, job: Job) -> list[Path]:
        src, opts, ctx = job.src, job.opts, job.ctx
        exe = shutil.which("whisper-cli")
        model = find_model()
        if exe is None or model is None:
            raise ConversionError("whisper-cli or its model is missing (dotmorph doctor)")
        ext = "txt" if job.action == "copy-text" else job.action
        out = out_dir(src, opts)
        with workdir(out) as tmpdir:
            wav = tmpdir / "audio.wav"
            code, err = run_tool(
                [shutil.which("ffmpeg") or "ffmpeg", "-nostdin", "-hide_banner", "-y", "-i",
                 str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
                ctx, timeout=opts.timeout,
            )
            if code != 0 or not wav.exists():
                raise ConversionError(f"no audio to transcribe: {last_error_line(err)}")
            ctx.progress(0.05)

            def progress(line: str) -> None:
                if m := _PROGRESS.search(line):
                    ctx.progress(0.05 + 0.9 * int(m.group(1)) / 100)

            threads = str(max(1, min(8, (os.cpu_count() or 2) - 1)))
            code, err = run_tool(
                [exe, "-m", str(model), "-f", str(wav), "-l", spoken(opts.language),
                 OUTPUT_FLAG[job.action], "-of", str(tmpdir / "out"), "-pp", "-t", threads],
                ctx, timeout=opts.timeout, on_err_line=progress,
            )
            result = tmpdir / f"out.{ext}"
            if code != 0 or not result.exists():
                raise ConversionError(f"whisper-cli failed: {last_error_line(err)}")
            if job.action == "copy-text":
                from ...linux.clipboard import copy_text

                text = result.read_text(encoding="utf-8", errors="replace").strip()
                if not copy_text(text):
                    raise ConversionError("transcribed, but no clipboard tool (wl-copy, xclip)")
            ctx.progress(1)
            return [finalize(result, out / f"{src.stem}.{ext}", opts.overwrite)]
