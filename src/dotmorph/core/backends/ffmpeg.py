"""Video and audio through ffmpeg, with live progress.

Same-codec container swaps (MP4 <-> MKV <-> MOV) are tried as a stream copy first, which
takes seconds instead of minutes; if the streams don't fit the new container it falls back
to a real transcode.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from ..common import (
    ConversionError,
    Job,
    Options,
    finalize,
    fit_limit,
    keep_smaller,
    last_error_line,
    out_dir,
    parse_resize,
    run_tool,
    too_big,
    workdir,
)
from ..formats import AUDIO_FORMATS, FIT_TOOLS, TOOLS, VIDEO_FORMATS, normalize_ext
from ..registry import Backend, Requirement

FFMPEG = Requirement("ffmpeg", {"apt": "ffmpeg", "dnf": "ffmpeg-free", "pacman": "ffmpeg",
                                "zypper": "ffmpeg"}, "video & audio")

VIDEO_OUT = ("mp4", "mkv", "webm", "mov", "avi")
AUDIO_OUT = ("mp3", "m4a", "ogg", "opus", "flac", "wav")
REMUXABLE = {"mp4", "mkv", "mov", "m4v"}
VIDEO_TOOLS = {"compress", "resize-50", "rotate-90", "mute", "strip"}
COMPRESSIBLE = {"mp4", "mkv", "mov", "m4v", "webm"}
FIT_AUDIO = {"mp3", "m4a", "ogg", "opus"}  # lossy formats a bitrate can size
FIT_AUDIO_ENCODER = {"mp3": ("libmp3lame",), "m4a": ("aac",), "ogg": ("libvorbis",),
                     "opus": ("libopus",)}

# Preferred encoder first; the first one this ffmpeg build has is used.
H264 = ("libx264", "libopenh264", "mpeg4")
VP9 = ("libvpx-vp9", "libvpx")
AUDIO_CODECS = {
    "mp3": ("libmp3lame",),
    "m4a": ("aac",),
    "ogg": ("libvorbis", "vorbis"),
    "opus": ("libopus", "opus"),
    "flac": ("flac",),
    "wav": ("pcm_s16le",),
}


@lru_cache(maxsize=1)
def encoders() -> frozenset[str]:
    exe = shutil.which("ffmpeg")
    if not exe:
        return frozenset()
    try:
        proc = subprocess.run(
            [exe, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    names = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            names.add(parts[1])
    return frozenset(names)


def _pick(options: tuple[str, ...]) -> str | None:
    have = encoders()
    return next((e for e in options if e in have), None)


def duration(path: Path) -> float:
    exe = shutil.which("ffprobe")
    if not exe:
        return 0.0
    try:
        proc = subprocess.run(
            [exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=20,
        )
        return float(proc.stdout.strip().splitlines()[0])
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return 0.0


def _scale_filter(spec: str) -> str:
    kind, pct, a, b = parse_resize(spec)
    even = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    if kind == "pct":
        return f"scale=trunc(iw*{pct / 100:.4f}/2)*2:trunc(ih*{pct / 100:.4f}/2)*2"
    if kind == "box":
        return f"scale={a}:{b}:force_original_aspect_ratio=decrease,{even}"
    return f"scale={a}:-2"


def _video_codec(target: str, crf_bump: int = 0) -> list[str]:
    if target == "webm":
        enc = _pick(VP9)
        if not enc:
            raise ConversionError("this ffmpeg has no VP9/VP8 encoder")
        return ["-c:v", enc, "-crf", str(33 + crf_bump), "-b:v", "0", "-row-mt", "1",
                "-deadline", "good", "-cpu-used", "5"]
    if target == "avi":
        return ["-c:v", "mpeg4", "-q:v", "4"]
    enc = _pick(H264)
    if enc == "libx264":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(23 + crf_bump),
                "-pix_fmt", "yuv420p"]
    if enc == "libopenh264":
        return ["-c:v", "libopenh264", "-b:v", "2M" if not crf_bump else "1M",
                "-pix_fmt", "yuv420p"]
    return ["-c:v", "mpeg4", "-q:v", "4"]


def _audio_codec_for_video(target: str) -> list[str]:
    if target == "webm":
        enc = _pick(("libopus", "libvorbis"))
        return ["-c:a", enc or "libopus", "-b:a", "128k"]
    if target == "avi":
        enc = _pick(("libmp3lame",)) or "aac"
        return ["-c:a", enc, "-b:a", "192k"]
    return ["-c:a", "aac", "-b:a", "160k"]


def _audio_args(target: str) -> list[str]:
    enc = _pick(AUDIO_CODECS[target])
    if enc is None:
        raise ConversionError(f"this ffmpeg build can't encode {target}")
    args = ["-c:a", enc]
    if enc == "libmp3lame":
        args += ["-q:a", "2"]
    elif enc == "libvorbis":
        args += ["-q:a", "5"]
    elif enc in ("libopus", "opus"):
        args += ["-b:a", "128k"]
    elif enc == "aac":
        args += ["-b:a", "192k"]
    if enc in ("vorbis", "opus"):
        args += ["-strict", "-2"]
    return args


def _container(target: str) -> list[str]:
    return ["-movflags", "+faststart"] if target in ("mp4", "mov", "m4v") else []


def _filters(job: Job) -> list[str]:
    chain = []
    if job.opts.resize:
        chain.append(_scale_filter(job.opts.resize))
    if job.action == "resize-50":
        chain.append("scale=trunc(iw/4)*2:trunc(ih/4)*2")
    elif job.action == "rotate-90":
        chain.append("transpose=1")
    return chain


def _gif_args(opts: Options) -> list[str]:
    scale = _scale_filter(opts.resize) if opts.resize else "scale='min(640,iw)':-1"
    graph = (
        f"fps=12,{scale}:flags=lanczos,split[a][b];"
        "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5"
    )
    return ["-filter_complex", graph, "-loop", "0"]


class FFmpegBackend(Backend):
    name = "ffmpeg"
    description = "Video (MP4, MKV, WebM, MOV, AVI, GIF) and audio (MP3, M4A, OGG, Opus, FLAC, WAV)"
    requirements = (FFMPEG,)
    extras = (Requirement("ffprobe", FFMPEG.packages, "progress percentage"),)

    def clear_cache(self) -> None:
        encoders.cache_clear()

    def potential_pairs(self) -> dict[str, set[str]]:
        pairs: dict[str, set[str]] = {}
        for src in VIDEO_FORMATS:
            actions = (set(VIDEO_OUT) | {"gif"} | set(AUDIO_OUT) | VIDEO_TOOLS) - {src}
            if src not in COMPRESSIBLE:
                actions.discard("compress")
            else:
                actions |= set(FIT_TOOLS)
            if src not in VIDEO_OUT and src != "m4v":
                actions -= {"resize-50", "rotate-90", "mute", "strip"}
            pairs[src] = actions
        for src in AUDIO_FORMATS:
            pairs[src] = (set(AUDIO_OUT) - {src}) | ({"strip"} if src in AUDIO_OUT else set())
            if src in FIT_AUDIO:
                pairs[src] |= set(FIT_TOOLS)
        pairs["gif"] = {"mp4", "webm"}
        return pairs

    def pairs(self) -> dict[str, set[str]]:
        if not self.available():
            return {}
        have = encoders()
        pairs = self.potential_pairs()
        for actions in pairs.values():
            for fmt, options in AUDIO_CODECS.items():
                if not any(e in have for e in options):
                    actions.discard(fmt)
            if not any(e in have for e in VP9):
                actions.discard("webm")
        return pairs

    # ---- running ----------------------------------------------------------------------

    def run(self, job: Job) -> list[Path]:
        src, action, opts, ctx = job.src, job.action, job.opts, job.ctx
        tool = TOOLS.get(action)
        source = normalize_ext(src.suffix)
        target = source if tool else action
        name = f"{src.stem}{tool.suffix if tool else ''}.{target}"
        out = out_dir(src, opts)
        total = duration(src)

        with workdir(out) as tmpdir:
            tmp = tmpdir / name
            limit = fit_limit(action, opts)
            if limit:
                self._fit(job, source, tmp, tmpdir, total, limit)
                ctx.progress(1)
                return [finalize(tmp, out / name, opts.overwrite)]
            attempts = self._plans(job, source, target)
            last_err = ""
            for args in attempts:
                ctx.check()
                tmp.unlink(missing_ok=True)
                code, err = self._ffmpeg(src, args, tmp, total, job)
                if code == 0 and tmp.exists() and tmp.stat().st_size > 0:
                    break
                last_err = err
            else:
                raise ConversionError(_explain(last_err))
            if action == "compress":
                keep_smaller(tmp, src)
            ctx.progress(1)
            return [finalize(tmp, out / name, opts.overwrite)]

    def _plans(self, job: Job, source: str, target: str) -> list[list[str]]:
        """ffmpeg argument lists to try in order (stream copy first when it can work)."""
        action, opts = job.action, job.opts
        filters = _filters(job)
        meta = ["-map_metadata", "-1", "-map_chapters", "-1"] if opts.strip else []

        if target in AUDIO_FORMATS and source in AUDIO_FORMATS | VIDEO_FORMATS:
            if action == "strip":
                return [["-map", "0:a", "-c", "copy", "-map_metadata", "-1"]]
            return [["-vn", "-map", "0:a:0", *_audio_args(target), *meta]]

        if action == "gif":
            return [[*_gif_args(opts)]]
        if action == "strip":
            return [["-map", "0:V?", "-map", "0:a?", "-map", "0:s?", "-c", "copy",
                     "-map_metadata", "-1", "-map_chapters", "-1", *_container(target)]]
        if action == "mute":
            return [["-map", "0:V", "-c:v", "copy", "-an", *_container(target)],
                    ["-map", "0:V", *_video_codec(target), "-an", *_container(target)]]

        crf_bump = 5 if action == "compress" else 0
        vf = ["-vf", ",".join(filters)] if filters else []
        maps = ["-map", "0:V:0", "-map", "0:a?"]
        audio = ["-an"] if source == "gif" else _audio_codec_for_video(target)
        transcode = [*maps, *vf, *_video_codec(target, crf_bump), *audio, *meta,
                     *_container(target)]
        plans = [transcode]
        if action == target and source in REMUXABLE and target in REMUXABLE and not filters:
            copy = ["-map", "0:V?", "-map", "0:a?", "-c", "copy", *meta, *_container(target)]
            if target == "mkv":
                copy[4:4] = ["-map", "0:s?"]
            plans.insert(0, copy)
        return plans

    # ---- fit under X MB -------------------------------------------------------------------

    def _fit(self, job: Job, source: str, tmp: Path, tmpdir: Path, total: float,
             limit: int) -> None:
        """Encode so the result is at most `limit` bytes: the bitrate comes from the
        duration; if the file still comes out too big, retry a little lower."""
        src = job.src
        if src.stat().st_size <= limit and not job.opts.strip and not job.opts.resize:
            shutil.copy2(src, tmp)  # already fits
            return
        if total <= 0:
            raise ConversionError("can't read the length of this file (is ffprobe installed?)")
        budget = limit * 8 / 1000 / total * 0.96  # kbit/s for everything, minus container
        meta = ["-map_metadata", "-1"] if job.opts.strip else []
        # each retry fills part of what's left of the bar, so it never goes backwards
        span = (0.0, 0.8)

        def next_span(s: tuple[float, float]) -> tuple[float, float]:
            return s[1], s[1] + (0.99 - s[1]) * 0.75

        if source in FIT_AUDIO:
            enc = _pick(FIT_AUDIO_ENCODER[source])
            if enc is None:
                raise ConversionError(f"this ffmpeg build can't encode {source}")
            kbps = min(320.0, budget)
            for _ in range(4):
                if kbps < 24:
                    raise too_big(limit, "audio")
                code, err = self._ffmpeg(src, ["-vn", "-map", "0:a:0", "-c:a", enc,
                                               "-b:a", f"{int(kbps)}k", *meta], tmp, total, job,
                                         span=span)
                if code != 0 or not tmp.exists():
                    raise ConversionError(_explain(err))
                if tmp.stat().st_size <= limit:
                    return
                kbps *= 0.92 * limit / tmp.stat().st_size
                span = next_span(span)
            raise too_big(limit, "audio")

        audio = 96 if budget > 600 else 64 if budget > 250 else 32
        video = budget - audio
        for _ in range(4):
            if video < 60:
                raise ConversionError(
                    f"{total / 60:.0f} min of video is too long to fit in {limit / 1e6:g} MB")
            height = None if video > 1800 else 720 if video > 700 else 480 if video > 300 else 360
            self._fit_video(job, source, tmp, tmpdir, total, video, audio, height, meta, span)
            if tmp.stat().st_size <= limit:
                return
            video *= 0.92 * limit / tmp.stat().st_size
            span = next_span(span)
        raise too_big(limit, "video")

    def _fit_video(self, job: Job, source: str, tmp: Path, tmpdir: Path, total: float,
                   video_kbps: float, audio_kbps: int, height: int | None,
                   meta: list[str], span: tuple[float, float] = (0.0, 0.99)) -> None:
        vf = ["-vf", f"scale=-2:'min({height},ih)'"] if height else []
        rate = ["-b:v", f"{int(video_kbps)}k", "-maxrate", f"{int(video_kbps * 1.5)}k",
                "-bufsize", f"{int(video_kbps * 2)}k"]
        if source == "webm":
            enc = _pick(VP9)
            if not enc:
                raise ConversionError("this ffmpeg has no VP9/VP8 encoder")
            codec = ["-c:v", enc, "-deadline", "good", "-cpu-used", "4", "-row-mt", "1"]
            acodec = ["-c:a", _pick(("libopus", "libvorbis")) or "libopus"]
        else:
            enc = _pick(H264) or "mpeg4"
            codec = ["-c:v", enc, "-pix_fmt", "yuv420p"]
            if enc == "libx264":
                codec += ["-preset", "medium"]
            acodec = ["-c:a", "aac"]
        log = ["-passlogfile", str(tmpdir / "pass")]
        two_pass = enc in ("libx264", "libvpx-vp9", "libvpx")
        lo, hi = span
        mid = lo + (hi - lo) * 0.45  # the first pass is about half the work
        maps = ["-map", "0:V:0", "-map", "0:a?"]
        if two_pass:  # first pass: analyse only (first ~half of the progress bar)
            code, err = self._ffmpeg(job.src, ["-map", "0:V:0", *vf, *codec, *rate, "-pass", "1",
                                               *log, "-an", "-f", "null"], Path(os.devnull),
                                     total, job, span=(lo, mid))
            if code != 0:
                raise ConversionError(_explain(err))
        second = ["-pass", "2", *log] if two_pass else []
        tmp.unlink(missing_ok=True)
        code, err = self._ffmpeg(job.src, [*maps, *vf, *codec, *rate, *second, *acodec,
                                           "-b:a", f"{audio_kbps}k", *meta,
                                           *_container(source)], tmp, total, job,
                                 span=(mid if two_pass else lo, hi))
        if code != 0 or not tmp.exists():
            raise ConversionError(_explain(err))

    def _ffmpeg(
        self, src: Path, args: list[str], dest: Path, total: float, job: Job,
        span: tuple[float, float] = (0.0, 0.99),
    ) -> tuple[int, str]:
        exe = shutil.which("ffmpeg")
        if exe is None:
            raise ConversionError("ffmpeg not found")
        ctx = job.ctx
        lo, hi = span

        def on_line(line: str) -> None:
            key, _, value = line.partition("=")
            if key in ("out_time_us", "out_time_ms") and total > 0 and value.isdigit():
                ctx.progress(lo + (hi - lo) * min(1.0, int(value) / 1_000_000 / total))

        cmd = [exe, "-hide_banner", "-nostdin", "-y", "-i", str(src), *args,
               "-progress", "pipe:1", "-nostats", str(dest)]
        return run_tool(cmd, ctx, timeout=job.opts.timeout, on_line=on_line)


def _explain(stderr: str) -> str:
    text = stderr.lower()
    if "does not contain any stream" in text or "matches no streams" in text:
        return "no matching audio/video track in this file"
    if "invalid data found" in text:
        return "not a media file ffmpeg can read"
    return f"ffmpeg failed: {last_error_line(stderr)}"
