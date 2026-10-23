import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from PIL import Image

from dotmorph.core import registry


def needs(*tools: str):
    missing = [t for t in tools if shutil.which(t) is None]
    return pytest.mark.skipif(bool(missing), reason=f"not installed: {', '.join(missing)}")


@pytest.fixture(autouse=True)
def private_config(tmp_path_factory, monkeypatch):
    """Never read or write the real ~/.config (wheel settings, integration files)."""
    home = tmp_path_factory.mktemp("xdg")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "data"))
    monkeypatch.setenv("LANGUAGE", "en")  # English UI text unless a test switches it
    from dotmorph import i18n

    monkeypatch.setattr(i18n, "_current", None)


@pytest.fixture(autouse=True)
def fresh_registry():
    registry.refresh()
    yield
    registry.refresh()


def make_png(path: Path, mode: str = "RGBA", size=(32, 24)) -> Path:
    colour = (255, 0, 0, 0) if mode == "RGBA" else (255, 0, 0)
    Image.new(mode, size, colour).save(path)
    return path


def make_pdf(path: Path, pages: int = 1) -> Path:
    imgs = [Image.new("RGB", (100, 100), c) for c in ("red", "blue", "green", "white")[:pages]]
    imgs[0].save(path, save_all=True, append_images=imgs[1:])
    return path


def make_wav(path: Path, seconds: float = 0.5) -> Path:
    rate = 8000
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x10" * int(rate * seconds))
    return path


def make_video(path: Path, seconds: float = 1, audio: bool = True, size: str = "96x64") -> Path:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate=10"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(path)]
    subprocess.run(cmd, check=True)
    return path


def probe(path: Path, entries: str) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", entries, "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def pdf_pages(path: Path) -> int:
    import re

    return len(re.findall(rb"/Type\s*/Page\b", path.read_bytes()))
