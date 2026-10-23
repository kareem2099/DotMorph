from conftest import make_png

from dotmorph.cli import main


def test_convert_command(tmp_path, capsys):
    src = make_png(tmp_path / "a.png")
    assert main(["convert", str(src), "--to", "webp", "--resize", "50%", "-q"]) == 0
    assert "ok" in capsys.readouterr().out
    assert (tmp_path / "a.webp").exists()


def test_convert_reports_failures(tmp_path, capsys):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"nope")
    assert main(["convert", str(bad), "--to", "jpg", "-q"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_formats_and_doctor(tmp_path, capsys):
    assert main(["formats"]) == 0
    out = capsys.readouterr().out
    assert "IMAGE" in out and "conversions available" in out
    assert main(["formats", str(make_png(tmp_path / "a.png"))]) == 0
    assert capsys.readouterr().out.startswith("jpg, webp")
    assert main(["doctor"]) == 0
    assert "pillow" in capsys.readouterr().out
