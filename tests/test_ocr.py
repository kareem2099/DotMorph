"""OCR with the real Tesseract (skipped where it isn't installed): text in, text out."""

import shutil
import subprocess

import pytest
from PIL import Image, ImageDraw, ImageFont

from dotmorph.core import registry
from dotmorph.core.backends import ocr
from dotmorph.core.common import ConversionError
from dotmorph.core.converter import Options, convert

needs_tesseract = pytest.mark.skipif(not shutil.which("tesseract"), reason="needs tesseract")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def text_image(path, lines=("DOTMORPH OCR TEST", "Radial menu for Linux")):
    img = Image.new("RGB", (1400, 140 + 110 * len(lines)), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT, 72)
    except OSError:
        font = ImageFont.load_default(size=72)
    for i, line in enumerate(lines):
        draw.text((60, 60 + 110 * i), line, fill="black", font=font)
    img.save(path)
    return path


def words(text: str) -> str:
    return " ".join(text.upper().split())


def test_language_codes(monkeypatch):
    monkeypatch.setattr(ocr, "installed_languages", lambda: frozenset({"eng", "ara", "osd"}))
    assert ocr.languages("ar") == "ara"
    assert ocr.languages("ar+en") == "ara+eng"
    monkeypatch.setattr(ocr, "installed_languages", lambda: frozenset({"eng", "por", "ara"}))
    assert ocr.languages("pt-BR") == "por" and ocr.languages("ara") == "ara"
    monkeypatch.setattr(ocr, "installed_languages", lambda: frozenset({"eng", "ara", "osd"}))
    with pytest.raises(ConversionError, match="tesseract-ocr-deu"):
        ocr.languages("de")
    monkeypatch.setattr("dotmorph.i18n.current", lambda: "ar")
    assert ocr.languages(None) == "eng+ara"  # English plus the UI language when installed
    monkeypatch.setattr("dotmorph.i18n.current", lambda: "ru")
    assert ocr.languages(None) == "eng"      # Russian pack not installed: English only


@needs_tesseract
def test_offered_for_images_and_pdfs():
    registry.refresh()
    assert {"txt", "copy-text", "ocr"} <= set(registry.actions_for("png"))
    assert {"txt", "ocr"} <= set(registry.actions_for("jpg"))
    if shutil.which("pdftoppm") and (shutil.which("gs") or shutil.which("ocrmypdf")):
        assert {"ocr", "copy-text"} <= set(registry.actions_for("pdf"))


@needs_tesseract
def test_image_to_text(tmp_path):
    out = convert(text_image(tmp_path / "sign.png"), "txt")[0]
    assert out.name == "sign.txt"
    assert "DOTMORPH OCR TEST" in words(out.read_text())


@needs_tesseract
def test_jpeg_and_heic_style_inputs(tmp_path):
    png = text_image(tmp_path / "a.png")
    Image.open(png).save(tmp_path / "a.tga")  # not read by Tesseract itself: goes via Pillow
    out = convert(tmp_path / "a.tga", "txt")[0]
    assert "RADIAL MENU" in words(out.read_text())


@needs_tesseract
def test_copy_text(tmp_path, monkeypatch):
    from dotmorph.linux import clipboard

    copied = []
    monkeypatch.setattr(clipboard, "copy_text", lambda text: copied.append(text) or True)
    convert(text_image(tmp_path / "note.png"), "copy-text")
    assert copied and "DOTMORPH OCR TEST" in words(copied[0])

    blank = tmp_path / "blank.png"
    Image.new("RGB", (400, 300), "white").save(blank)
    with pytest.raises(ConversionError, match="no text"):
        convert(blank, "copy-text")


@needs_tesseract
def test_image_to_searchable_pdf(tmp_path):
    if not shutil.which("pdftotext"):
        pytest.skip("needs pdftotext to read the result")
    out = convert(text_image(tmp_path / "page.png"), "ocr")[0]
    assert out.name == "page-ocr.pdf"
    text = subprocess.run(["pdftotext", str(out), "-"], capture_output=True, text=True).stdout
    assert "DOTMORPH OCR TEST" in words(text)


@needs_tesseract
@pytest.mark.skipif(not (shutil.which("pdftoppm") and shutil.which("pdftotext")),
                    reason="needs poppler")
def test_scanned_pdf_becomes_searchable(tmp_path):
    pages = [Image.open(text_image(tmp_path / f"p{i}.png", (f"PAGE NUMBER {i}", "SCANNED")))
             for i in (1, 2)]
    scan = tmp_path / "scan.pdf"
    pages[0].convert("RGB").save(scan, save_all=True,
                                 append_images=[p.convert("RGB") for p in pages[1:]])
    before = subprocess.run(["pdftotext", str(scan), "-"], capture_output=True, text=True).stdout
    assert not before.strip()  # a scan: no text layer yet
    out = convert(scan, "ocr")[0]
    after = words(subprocess.run(["pdftotext", str(out), "-"], capture_output=True,
                                 text=True).stdout)
    assert "PAGE NUMBER 1" in after and "PAGE NUMBER 2" in after


@needs_tesseract
def test_missing_language_pack_names_the_package(tmp_path):
    if "ara" in ocr.installed_languages():
        pytest.skip("Arabic pack installed here")
    with pytest.raises(ConversionError, match="tesseract-ocr-ara"):
        convert(text_image(tmp_path / "x.png"), "txt", Options(language="ar"))
