"""Transcription through whisper.cpp. A fake `whisper-cli` stands in for the real one (same
arguments, same progress lines on stderr, same output files), so no model is downloaded."""

import io
import os
import shutil
import stat
import sys

import pytest
from conftest import make_video, make_wav

from dotmorph.core import registry
from dotmorph.core.backends import whisper
from dotmorph.core.converter import Options, convert

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")

FAKE_CLI = r'''#!{python}
import sys
args = sys.argv[1:]
def opt(flag):
    return args[args.index(flag) + 1]
model, wav, lang, out = opt("-m"), opt("-f"), opt("-l"), opt("-of")
open(wav, "rb").read(4)                      # the WAV ffmpeg made must exist
for p in (25, 50, 100):
    print(f"whisper_print_progress_callback: progress = {{p:3d}}%", file=sys.stderr)
text = f"hello from whisper (lang={{lang}})"
if "-otxt" in args:
    open(out + ".txt", "w").write(text + "\n")
if "-osrt" in args:
    open(out + ".srt", "w").write(f"1\n00:00:00,000 --> 00:00:01,000\n{{text}}\n\n")
if "-ovtt" in args:
    open(out + ".vtt", "w").write(f"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n{{text}}\n\n")
'''


@pytest.fixture
def fake_whisper(tmp_path, monkeypatch):
    """A whisper-cli on PATH and a model in DotMorph's models folder."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cli = bin_dir / "whisper-cli"
    cli.write_text(FAKE_CLI.format(python=sys.executable))
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    model = whisper.models_dir() / "ggml-base.bin"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"ggml")
    registry.refresh()
    yield model
    registry.refresh()


def test_needs_a_model_and_says_how_to_get_it(tmp_path, monkeypatch):
    monkeypatch.delenv("DOTMORPH_WHISPER_MODEL", raising=False)
    registry.refresh()
    assert whisper.find_model() is None
    assert not whisper.MODEL.present()
    assert whisper.MODEL.install == "dotmorph whisper --download base"
    assert "copy-text" not in registry.actions_for("mp3")
    missing = registry.missing_for("mp3", "txt")
    if shutil.which("whisper-cli") and shutil.which("ffmpeg"):
        assert missing == [whisper.MODEL]
    else:
        assert missing and missing[0].name in ("whisper-cli", "ffmpeg", "whisper model")


def test_model_lookup_order(tmp_path, monkeypatch):
    folder = whisper.models_dir()
    folder.mkdir(parents=True)
    (folder / "ggml-small.bin").write_bytes(b"x")
    assert whisper.find_model() == folder / "ggml-small.bin"   # the only one there
    (folder / "ggml-base.bin").write_bytes(b"x")
    assert whisper.find_model() == folder / "ggml-base.bin"    # the default wins
    custom = tmp_path / "mine.bin"
    custom.write_bytes(b"x")
    monkeypatch.setenv("DOTMORPH_WHISPER_MODEL", str(custom))
    assert whisper.find_model() == custom                      # explicit choice first
    monkeypatch.setenv("DOTMORPH_WHISPER_MODEL", str(tmp_path / "gone.bin"))
    assert whisper.find_model() is None


@needs_ffmpeg
def test_targets_for_audio_and_video(fake_whisper):
    for src in ("mp3", "wav", "mp4", "mkv"):
        assert {"txt", "srt", "vtt", "copy-text"} <= set(registry.actions_for(src)), src
    assert registry.backend_for("mp3", "copy-text").name == "whisper"
    png = registry.backend_for("png", "copy-text")  # images: OCR's, never whisper's
    assert png is None or png.name == "tesseract"


@needs_ffmpeg
def test_audio_to_text_with_progress_and_language(fake_whisper, tmp_path):
    src = make_wav(tmp_path / "memo.wav", seconds=1)
    seen: list[float] = []
    outputs = convert(src, "txt", Options(language="ar"), on_progress=seen.append)
    assert [p.name for p in outputs] == ["memo.txt"]
    assert outputs[0].read_text().strip() == "hello from whisper (lang=ar)"
    assert seen and seen[-1] == 1 and any(0.05 < p < 1 for p in seen)


@needs_ffmpeg
def test_video_to_subtitles(fake_whisper, tmp_path):
    src = make_video(tmp_path / "talk.mp4", seconds=1)
    srt = convert(src, "srt")[0]
    vtt = convert(src, "vtt")[0]
    assert srt.name == "talk.srt" and "-->" in srt.read_text()
    assert vtt.read_text().startswith("WEBVTT")
    assert "lang=auto" in srt.read_text()  # no language given: detect


@needs_ffmpeg
def test_copy_text_puts_the_transcript_on_the_clipboard(fake_whisper, tmp_path, monkeypatch):
    from dotmorph.linux import clipboard

    copied: list[str] = []
    monkeypatch.setattr(clipboard, "copy_text", lambda text: copied.append(text) or True)
    out = convert(make_wav(tmp_path / "note.wav"), "copy-text")[0]
    assert copied == ["hello from whisper (lang=auto)"]
    assert out.name == "note.txt"  # and kept as a file too

    monkeypatch.setattr(clipboard, "copy_text", lambda text: False)
    with pytest.raises(Exception, match="clipboard"):
        convert(make_wav(tmp_path / "note2.wav"), "copy-text")


class _Response(io.BytesIO):
    def __init__(self, data: bytes, length: int):
        super().__init__(data)
        self.headers = {"Content-Length": str(length)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_model(monkeypatch):
    urls = []

    def fake_open(url, timeout):
        urls.append(url)
        return _Response(b"m" * 3000, 3000)

    monkeypatch.setattr(whisper.urllib.request, "urlopen", fake_open)
    progress = []
    path = whisper.download("tiny", lambda done, total: progress.append((done, total)))
    assert path == whisper.models_dir() / "ggml-tiny.bin" and path.stat().st_size == 3000
    assert urls == ["https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin"]
    assert progress[-1] == (3000, 3000)

    monkeypatch.setattr(whisper.urllib.request, "urlopen",
                        lambda url, timeout: _Response(b"m" * 10, 3000))
    with pytest.raises(OSError, match="incomplete"):
        whisper.download("base")
    assert not (whisper.models_dir() / "ggml-base.bin").exists()
    assert not list(whisper.models_dir().glob("*.part"))
    with pytest.raises(ValueError):
        whisper.download("huge")


def test_cli_lists_models(capsys):
    from dotmorph.cli import main

    assert main(["whisper", "--list"]) == 0
    out = capsys.readouterr().out
    assert "base" in out and "(default)" in out and "dotmorph whisper --download" in out
    assert main(["whisper", "--download", "huge"]) == 2


def test_clipboard_copy_tries_the_available_tools(monkeypatch):
    from dotmorph.linux import clipboard

    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: f"/usr/bin/{name}")
    cmds = clipboard._copy_commands()
    assert [c[0] for c in cmds] == ["wl-copy", "xclip", "xsel"]
    monkeypatch.delenv("WAYLAND_DISPLAY")
    monkeypatch.delenv("DISPLAY")
    assert clipboard._copy_commands() == [] and clipboard.copy_text("x") is False


def test_language_codes_for_whisper():
    from dotmorph.core.backends.whisper import spoken

    assert spoken(None) == "auto" and spoken("") == "auto"
    assert spoken("ar") == "ar" and spoken("pt-BR") == "pt" and spoken("pt_BR") == "pt"
    assert spoken("ar+en") == "ar" and spoken("EN") == "en"
