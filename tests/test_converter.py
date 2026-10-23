import shutil

import pytest
from conftest import make_png, pdf_pages
from PIL import Image

from dotmorph.core.converter import ConversionError, Options, convert, convert_many

needs_poppler = pytest.mark.skipif(shutil.which("pdftoppm") is None, reason="poppler not installed")


def test_png_to_jpg_flattens_alpha_on_white(tmp_path):
    (out,) = convert(make_png(tmp_path / "a.png"), "jpg")
    assert out == tmp_path / "a.jpg"
    with Image.open(out) as im:
        assert im.format == "JPEG"
        assert im.getpixel((0, 0))[0] > 240  # transparent -> white, not black


def test_png_to_webp_and_back(tmp_path):
    (webp,) = convert(make_png(tmp_path / "a.png"), "webp")
    (png,) = convert(webp, "png", Options(out_dir=tmp_path / "out"))
    assert png.parent == tmp_path / "out"
    with Image.open(png) as im:
        assert im.size == (32, 24)


def test_never_overwrites_by_default(tmp_path):
    src = make_png(tmp_path / "a.png")
    first = convert(src, "jpg")[0]
    second = convert(src, "jpg")[0]
    assert first.name == "a.jpg" and second.name == "a (1).jpg"
    assert convert(src, "jpg", Options(overwrite=True))[0] == first


def test_rejects_unsupported_pairs_and_missing_files(tmp_path):
    src = make_png(tmp_path / "a.png")
    with pytest.raises(ConversionError):
        convert(src, "png")  # same format
    with pytest.raises(ConversionError):
        convert(tmp_path / "nope.png", "jpg")


def test_corrupt_image_reports_error_and_leaves_no_file(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(ConversionError):
        convert(bad, "jpg")
    assert not (tmp_path / "bad.jpg").exists()


def test_convert_many_continues_after_failure(tmp_path):
    good = make_png(tmp_path / "good.png")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"x")
    calls = []
    result = convert_many([bad, good], "jpg", on_progress=lambda i, n: calls.append((i, n)))
    assert [p.name for p in result.outputs] == ["good.jpg"]
    assert len(result.errors) == 1 and not result.ok
    assert calls == [(1, 2), (2, 2)]


@needs_poppler
def test_pdf_to_png_single_and_multi_page(tmp_path):
    pages = [Image.new("RGB", (100, 100), c) for c in ("red", "blue", "green")]
    one, three = tmp_path / "one.pdf", tmp_path / "three.pdf"
    pages[0].save(one)
    pages[0].save(three, save_all=True, append_images=pages[1:])

    assert [p.name for p in convert(one, "png", Options(dpi=72))] == ["one.png"]
    outs = convert(three, "jpg", Options(dpi=72))
    assert [p.name for p in outs] == ["three-001.jpg", "three-002.jpg", "three-003.jpg"]


@needs_poppler
def test_broken_pdf_raises(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-garbage")
    with pytest.raises(ConversionError):
        convert(bad, "png")


# ---- 2.0 engine: images, tools, batches -------------------------------------------------

import threading  # noqa: E402

from PIL import ImageSequence  # noqa: E402

from dotmorph.core.converter import Cancelled  # noqa: E402


def test_animated_gif_to_webp_keeps_frames(tmp_path):
    frames = [Image.new("RGB", (20, 20), c) for c in ("red", "green", "blue")]
    gif = tmp_path / "anim.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=80, loop=0)
    (webp,) = convert(gif, "webp")
    with Image.open(webp) as im:
        assert sum(1 for _ in ImageSequence.Iterator(im)) == 3


def test_exif_orientation_is_applied_and_strip_removes_exif(tmp_path):
    src = tmp_path / "photo.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # rotated 90 degrees
    exif[0x010F] = "SecretCam"
    Image.new("RGB", (40, 20), "white").save(src, exif=exif)

    (png,) = convert(src, "png")
    with Image.open(png) as im:
        assert im.size == (20, 40)  # turned upright
    (clean,) = convert(src, "strip")
    assert clean.name == "photo-clean.jpg"
    with Image.open(clean) as im:
        assert 0x010F not in im.getexif()


def test_tools_resize_rotate_and_resize_option(tmp_path):
    src = make_png(tmp_path / "a.png", size=(40, 20))
    (half,) = convert(src, "resize-50")
    (turned,) = convert(src, "rotate-90")
    (small,) = convert(src, "webp", Options(resize="25%"))
    with Image.open(half) as a, Image.open(turned) as b, Image.open(small) as c:
        assert (a.size, b.size, c.size) == ((20, 10), (20, 40), (10, 5))
    assert half.name == "a-resized.png" and turned.name == "a-rotated.png"


def test_compress_never_grows_the_file(tmp_path):
    src = tmp_path / "noise.png"
    Image.effect_noise((64, 64), 80).convert("RGB").save(src)
    (out,) = convert(src, "compress")
    assert out.name == "noise-compressed.png"
    assert out.stat().st_size <= src.stat().st_size


def test_more_image_formats(tmp_path):
    from dotmorph.core.registry import actions_for

    src = make_png(tmp_path / "a.png")
    # AVIF needs Pillow 11.2+; older Pillow simply doesn't offer it
    targets = ["gif", "bmp", "tiff", "ico", "pdf"]
    if "avif" in actions_for("png"):
        targets.append("avif")
    for target in targets:
        (out,) = convert(src, target)
        assert out.suffix == f".{target}" and out.stat().st_size > 0


def test_merge_images_into_one_pdf(tmp_path):
    imgs = [make_png(tmp_path / f"p{i}.png", mode="RGB") for i in range(3)]
    result = convert_many(imgs, "merge-pdf")
    assert result.ok and [p.name for p in result.outputs] == ["p0-merged.pdf"]
    assert pdf_pages(result.outputs[0]) == 3


def test_parallel_batch_never_loses_files_with_same_name(tmp_path):
    a = make_png(tmp_path / "a.png")
    b = tmp_path / "a.jpg"
    Image.new("RGB", (8, 8)).save(b)
    many = [make_png(tmp_path / f"x{i}.png") for i in range(6)]
    fractions = []
    result = convert_many([a, b, *many], "webp", jobs=4, on_fraction=fractions.append)
    assert result.ok
    names = sorted(p.name for p in result.outputs)
    assert "a.webp" in names and "a (1).webp" in names and len(names) == 8
    assert fractions[-1] == 1.0
    assert not list(tmp_path.glob(".dotmorph-*"))  # scratch dirs cleaned up


def test_cancelled_batch_does_nothing(tmp_path):
    cancel = threading.Event()
    cancel.set()
    result = convert_many([make_png(tmp_path / "a.png")], "jpg", cancel=cancel)
    assert result.cancelled and not result.outputs and not result.ok
    with pytest.raises(Cancelled):
        convert(tmp_path / "a.png", "jpg", cancel=cancel)
