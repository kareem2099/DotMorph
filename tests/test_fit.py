"""'Fit under X MB': every result must be at or under the limit, as good as it can be, and
files that already fit come back untouched."""

import os
import shutil
import subprocess

import pytest
from PIL import Image

from dotmorph.cli import parse_size
from dotmorph.core import registry
from dotmorph.core.common import MB, ConversionError
from dotmorph.core.converter import Options, convert
from dotmorph.core.formats import FIT_TOOLS

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
needs_gs = pytest.mark.skipif(not shutil.which("gs"), reason="needs ghostscript")


def noisy_photo(path, size=(2400, 1800)):
    """Random noise compresses badly: a worst case for size targets."""
    Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)).save(path, quality=95)
    return path


def test_parse_size():
    assert parse_size("8M") == 8 * MB
    assert parse_size("10MB") == 10 * MB
    assert parse_size("500k") == 500_000
    assert parse_size("2.5m") == 2_500_000
    assert parse_size("1200000") == 1_200_000
    with pytest.raises(ValueError):
        parse_size("lots")


def test_fit_tools_are_offered_where_they_work():
    registry.refresh()
    assert set(FIT_TOOLS) <= set(registry.actions_for("jpg"))
    assert set(FIT_TOOLS) <= set(registry.actions_for("png"))
    if shutil.which("ffmpeg"):
        assert set(FIT_TOOLS) <= set(registry.actions_for("mp4"))
        assert set(FIT_TOOLS) <= set(registry.actions_for("mp3"))
    if shutil.which("gs"):
        assert set(FIT_TOOLS) <= set(registry.actions_for("pdf"))
    assert not set(FIT_TOOLS) & set(registry.actions_for("txt"))


def test_photo_fits_with_the_best_quality_that_does(tmp_path):
    src = noisy_photo(tmp_path / "photo.jpg")
    assert src.stat().st_size > 900_000
    out = convert(src, "fit-10mb", Options(fit_bytes=400_000))[0]
    assert out.name == "photo-10mb.jpg"
    assert out.stat().st_size <= 400_000
    assert out.stat().st_size > 250_000  # used most of the budget, not crushed


def test_png_falls_back_to_palette_then_size(tmp_path):
    src = noisy_photo(tmp_path / "shot.png", (900, 700))
    out = convert(src, "fit-10mb", Options(fit_bytes=150_000))[0]
    assert out.stat().st_size <= 150_000
    with Image.open(out) as im:
        assert im.width < 900  # noise doesn't fit losslessly: smaller dimensions


def test_already_fits_is_returned_untouched(tmp_path):
    src = tmp_path / "small.jpg"
    Image.new("RGB", (64, 64), "red").save(src)
    out = convert(src, "fit-16mb")[0]
    assert out.read_bytes() == src.read_bytes()


def test_impossible_target_says_so(tmp_path):
    src = noisy_photo(tmp_path / "huge.jpg")
    with pytest.raises(ConversionError, match="under"):
        convert(src, "fit-10mb", Options(fit_bytes=200))


@needs_ffmpeg
def test_video_fits_and_stays_a_video(tmp_path):
    src = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=duration=8:size=1280x720:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
                    "-c:v", "libx264", "-b:v", "6M", "-c:a", "aac", "-shortest", str(src)],
                   check=True)
    assert src.stat().st_size > 3 * MB
    seen = []
    out = convert(src, "fit-10mb", Options(fit_bytes=1 * MB), on_progress=seen.append)[0]
    assert out.name == "clip-10mb.mp4" and out.stat().st_size <= 1 * MB
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                            "-of", "csv=p=0", str(out)], capture_output=True, text=True)
    assert {"video", "audio"} <= set(probe.stdout.split())
    assert seen == sorted(seen)  # two passes, but the progress bar never goes backwards


@needs_ffmpeg
def test_audio_fits(tmp_path):
    src = tmp_path / "song.mp3"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "anoisesrc=d=30:a=0.5", "-c:a", "libmp3lame", "-b:a", "320k", str(src)],
                   check=True)
    out = convert(src, "fit-10mb", Options(fit_bytes=500_000))[0]
    assert out.suffix == ".mp3" and out.stat().st_size <= 500_000


@needs_ffmpeg
def test_too_long_video_explains_why(tmp_path):
    src = tmp_path / "long.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=duration=20:size=320x240:rate=10", "-c:v", "libx264",
                    "-b:v", "2M", str(src)], check=True)
    with pytest.raises(ConversionError, match="too long|under"):
        convert(src, "fit-10mb", Options(fit_bytes=20_000))


@needs_gs
def test_pdf_fits(tmp_path):
    pages = [Image.frombytes("RGB", (1200, 900), os.urandom(1200 * 900 * 3)) for _ in range(3)]
    src = tmp_path / "scan.pdf"
    pages[0].save(src, save_all=True, append_images=pages[1:], resolution=150)
    assert src.stat().st_size > 1.5 * MB
    out = convert(src, "fit-10mb", Options(fit_bytes=600_000))[0]
    assert out.name == "scan-10mb.pdf" and out.stat().st_size <= 600_000


def test_fit_flag_needs_a_size_tool(tmp_path, capsys):
    from dotmorph.cli import main

    src = tmp_path / "a.jpg"
    Image.new("RGB", (32, 32), "red").save(src)
    assert main(["convert", str(src), "--to", "webp", "--fit", "1M"]) == 2
    assert "--fit works with the size tools" in capsys.readouterr().err
    assert not (tmp_path / "a.webp").exists()  # nothing written with the limit dropped
    assert main(["convert", str(src), "--fit", "0"]) == 2
    with pytest.raises(ValueError):
        parse_size("0k")
    assert main(["convert", str(src), "--fit", "1M", "-q"]) == 0  # alone: fit-25mb, 1 MB
    assert (tmp_path / "a-25mb.jpg").exists()
