"""Backends that call external tools. Each test is skipped when its tool isn't installed."""

import shutil
import threading
import time

import pytest
from conftest import make_pdf, make_png, make_video, make_wav, needs, pdf_pages, probe
from PIL import Image

from dotmorph.core import registry
from dotmorph.core.converter import (
    Cancelled,
    ConversionError,
    MissingDependencyError,
    Options,
    convert,
    convert_many,
)

# ---- poppler / ghostscript ----------------------------------------------------------------


@needs("pdftoppm")
def test_pdf_to_webp_pages(tmp_path):
    outs = convert(make_pdf(tmp_path / "doc.pdf", pages=2), "webp", Options(dpi=72))
    assert [p.name for p in outs] == ["doc-001.webp", "doc-002.webp"]
    with Image.open(outs[0]) as im:
        assert im.format == "WEBP"


@needs("pdftotext")
def test_pdf_to_text(tmp_path):
    (txt,) = convert(make_pdf(tmp_path / "doc.pdf"), "txt")
    assert txt.name == "doc.txt"


@needs("gs")
def test_compress_pdf_never_grows(tmp_path):
    src = make_pdf(tmp_path / "doc.pdf", pages=3)
    (out,) = convert(src, "compress")
    assert out.name == "doc-compressed.pdf"
    assert out.stat().st_size <= src.stat().st_size


@needs("gs")
def test_merge_pdfs_and_images(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", pages=2)
    png = make_png(tmp_path / "b.png", mode="RGB")
    result = convert_many([pdf, png], "merge-pdf")
    assert result.ok, result.errors
    assert pdf_pages(result.outputs[0]) == 3


# ---- ImageMagick --------------------------------------------------------------------------

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
    '<rect width="40" height="20" fill="#7C5CFF"/></svg>'
)


@pytest.mark.skipif(not registry.actions_for("svg"), reason="no SVG renderer")
def test_svg_to_png_honours_dpi(tmp_path):
    src = tmp_path / "logo.svg"
    src.write_text(SVG)
    (png,) = convert(src, "png", Options(dpi=192))  # 2x the 96 dpi CSS pixel
    with Image.open(png) as im:
        assert im.size == (80, 40)
    (pdf,) = convert(src, "pdf")
    assert pdf.read_bytes().startswith(b"%PDF")


TEXT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="80">'
    '<text x="10" y="60" font-family="DejaVu Sans" font-size="60" font-weight="700" '
    'letter-spacing="-2" fill="#123456">Dot</text></svg>'
)


def _librsvg_ready() -> bool:
    from dotmorph.core.backends.svg import SvgBackend

    return SvgBackend().available()


@pytest.mark.skipif(not _librsvg_ready(), reason="librsvg not installed")
def test_svg_uses_librsvg_original_size_transparency_and_vector_pdf(tmp_path):
    assert registry.backend_for("svg", "png").name == "librsvg"
    src = tmp_path / "title.svg"
    src.write_text(TEXT_SVG)
    (png,) = convert(src, "png")
    with Image.open(png) as im:
        assert im.size == (300, 80)  # 1 CSS px = 1 px by default
        rgba = im.convert("RGBA")
        assert rgba.getpixel((299, 0))[3] == 0  # background stays transparent
        # bold text with negative letter-spacing really drawn (ImageMagick made blobs)
        ink = rgba.getchannel("A").point(lambda v: 1 if v > 200 else 0).histogram()[1]
        assert 2000 < ink < 12000
    (pdf,) = convert(src, "pdf")
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF") and b"/Subtype /Image" not in data  # vector, not a picture
    assert b"FontFile" in data  # text embedded as text


# ---- ffmpeg -------------------------------------------------------------------------------


@needs("ffmpeg", "ffprobe")
def test_video_container_swap_and_transcodes(tmp_path):
    src = make_video(tmp_path / "clip.mp4")
    (mkv,) = convert(src, "mkv")
    assert probe(mkv, "stream=codec_name").splitlines()[0] == "h264"  # stream copy
    (webm,) = convert(src, "webm")
    assert "vp9" in probe(webm, "stream=codec_name") or "vp8" in probe(webm, "stream=codec_name")
    (gif,) = convert(src, "gif")
    with Image.open(gif) as im:
        assert im.format == "GIF" and im.n_frames > 1


@needs("ffmpeg", "ffprobe")
def test_extract_audio_and_audio_formats(tmp_path):
    src = make_video(tmp_path / "clip.mp4")
    (mp3,) = convert(src, "mp3")
    assert probe(mp3, "stream=codec_name") == "mp3"
    (flac,) = convert(make_wav(tmp_path / "tone.wav"), "flac")
    assert probe(flac, "stream=codec_name") == "flac"
    with pytest.raises(ConversionError, match="no matching"):
        convert(make_video(tmp_path / "silent.mp4", audio=False), "mp3")


@needs("ffmpeg", "ffprobe")
def test_video_tools(tmp_path):
    src = make_video(tmp_path / "clip.mp4", size="96x64")
    (muted,) = convert(src, "mute")
    assert "audio" not in probe(muted, "stream=codec_type")
    (half,) = convert(src, "resize-50")
    assert probe(half, "stream=width,height").splitlines()[0] == "48,32"
    (turned,) = convert(src, "rotate-90")
    assert probe(turned, "stream=width,height").splitlines()[0] == "64,96"


@needs("ffmpeg", "ffprobe")
def test_ffmpeg_reports_progress_and_cancels(tmp_path):
    # long enough that a full VP9 encode takes far longer than the cancel bound below
    src = make_video(tmp_path / "long.mp4", seconds=90, size="640x360")
    seen = []
    convert(src, "mkv", on_progress=seen.append)  # remux: fast, still reports the end
    assert seen and seen[-1] == 1.0

    cancel = threading.Event()
    threading.Timer(0.4, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(Cancelled):
        convert(src, "webm", cancel=cancel)
    assert time.monotonic() - started < 15
    assert not list(tmp_path.glob("long*.webm"))
    assert not list(tmp_path.glob(".dotmorph-*"))


def test_missing_tool_gives_install_hint(tmp_path, monkeypatch):
    real = shutil.which
    monkeypatch.setattr(shutil, "which", lambda t, *a, **k: None if t == "ffmpeg" else real(t))
    registry.refresh()
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"\x00")
    with pytest.raises(MissingDependencyError, match="install"):
        convert(src, "mp3")


# ---- LibreOffice / pandoc -----------------------------------------------------------------


@needs("soffice")
def test_office_csv_to_xlsx_and_txt_to_pdf(tmp_path):
    csv = tmp_path / "data.csv"
    csv.write_text("name,score\nada,10\nlinus,9\n")
    (xlsx,) = convert(csv, "xlsx")
    assert xlsx.read_bytes()[:2] == b"PK"
    txt = tmp_path / "note.txt"
    txt.write_text("hello from DotMorph\n")
    (pdf,) = convert(txt, "pdf")
    assert pdf.read_bytes().startswith(b"%PDF")


@needs("pandoc")
def test_pandoc_markdown_round_trip(tmp_path):
    md = tmp_path / "readme.md"
    md.write_text("# Title\n\nSome **bold** text.\n")
    (html,) = convert(md, "html")
    assert "<strong>bold</strong>" in html.read_text()
    (docx,) = convert(md, "docx")
    assert docx.read_bytes()[:2] == b"PK"
    (back,) = convert(html, "md", Options(out_dir=tmp_path / "back"))
    assert "**bold**" in back.read_text()


@pytest.mark.skipif("pdf" not in registry.actions_for("md"), reason="no pandoc PDF route")
def test_markdown_to_pdf(tmp_path):
    md = tmp_path / "notes.md"
    md.write_text("# Notes\n\nDotMorph converts everything.\n")
    (pdf,) = convert(md, "pdf")
    assert pdf.read_bytes().startswith(b"%PDF")
