"""Settings, presets, dry run, `formats --missing` and shell completions."""

import shutil
import subprocess

import pytest
from conftest import make_pdf, make_png

from dotmorph import completions, settings
from dotmorph.cli import _parser, main
from dotmorph.core import registry
from dotmorph.core.common import Options
from dotmorph.core.converter import plan

# ---- settings -------------------------------------------------------------------------


def test_settings_round_trip_and_cleaning(tmp_path):
    s = settings.load()
    assert (s.quality, s.dpi, s.resize, s.strip) == (90, 0, "", False)
    assert s.summary() == ""
    s.quality, s.resize, s.strip, s.dpi = 250, "50%", True, 300
    settings.save(s)
    back = settings.load()
    assert back.quality == 100 and back.resize == "50%" and back.strip and back.dpi == 300
    assert back.summary() == "Q100 · 300 dpi · 50% · no metadata"
    opts = back.options()
    assert (opts.quality, opts.dpi, opts.resize, opts.strip) == (100, 300, "50%", True)


def test_broken_settings_file_falls_back_to_defaults():
    path = settings.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert settings.load() == settings.Settings()
    path.write_text('{"quality": "x", "resize": "huge", "unknown": 1}')
    assert settings.load() == settings.Settings()


# ---- presets and dry run --------------------------------------------------------------


def test_preset_sets_target_and_options(tmp_path, capsys):
    src = make_png(tmp_path / "big.png", size=(4000, 2000))
    assert main(["convert", str(src), "--preset", "web", "-q"]) == 0
    from PIL import Image

    with Image.open(tmp_path / "big.webp") as im:
        assert im.size == (1920, 960)  # fits 1920x1920


def test_explicit_flags_beat_the_preset(tmp_path, capsys):
    src = make_png(tmp_path / "a.png", size=(400, 200))
    assert main(["convert", str(src), "--preset", "thumb", "--to", "jpg", "--resize", "100",
                 "-q"]) == 0
    from PIL import Image

    with Image.open(tmp_path / "a.jpg") as im:
        assert im.size == (100, 50)


def test_convert_needs_a_target(tmp_path, capsys):
    assert main(["convert", str(make_png(tmp_path / "a.png"))]) == 2
    assert "--to is required" in capsys.readouterr().err


def test_dry_run_writes_nothing(tmp_path, capsys):
    png = make_png(tmp_path / "a.png")
    assert main(["convert", str(png), str(tmp_path / "nope.png"), "--to", "webp",
                 "--dry-run"]) == 1
    out = capsys.readouterr().out
    assert "would" in out and "a.webp" in out and "[pillow]" in out
    assert "skip" in out and "file not found" in out
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.png"]


def test_plan_names_pdf_pages_tools_and_merges(tmp_path):
    pdf = make_pdf(tmp_path / "doc.pdf")
    png = make_png(tmp_path / "a.png")
    if registry.backend_for("pdf", "png"):
        (step,) = plan([pdf], "png")
        assert step.output.endswith("doc[-NNN].png")
    (step,) = plan([png], "compress", Options(out_dir=tmp_path / "o"))
    assert step.output == str(tmp_path / "o" / "a-compressed.png")
    steps = plan([png, png], "merge-pdf")
    assert {s.output for s in steps} == {str(tmp_path / "a-merged.pdf")}


def test_formats_missing_lists_what_a_tool_would_add(monkeypatch, capsys):
    real = shutil.which
    monkeypatch.setattr(shutil, "which", lambda t, *a, **k: None if t == "ffmpeg" else real(t))
    registry.refresh()
    assert main(["formats", "--missing"]) == 0
    out = capsys.readouterr().out
    assert "ffmpeg" in out and "mp4 ->" in out and "install:" in out


# ---- completions ----------------------------------------------------------------------


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_scripts_cover_commands_and_targets(shell):
    script = completions.generate(shell, _parser())
    flags = ("-l preset", "-l dry-run") if shell == "fish" else ("--preset", "--dry-run")
    for word in ("convert", "watch", "hotkey", "webp", "merge-pdf", *flags):
        assert word in script
    tool = {"bash": "bash", "zsh": "zsh", "fish": "fish"}[shell]
    if shutil.which(tool):
        proc = subprocess.run([tool, "-n"], input=script, text=True, capture_output=True)
        assert proc.returncode == 0, proc.stderr


@pytest.mark.skipif(not shutil.which("bash"), reason="no bash")
def test_bash_completion_really_completes(tmp_path):
    script = tmp_path / "dotmorph.bash"
    script.write_text(completions.generate("bash", _parser()))
    probe = (
        f"source {script}; "
        "COMP_WORDS=(dotmorph convert a.png --to we); COMP_CWORD=4; _dotmorph; "
        'echo "${COMPREPLY[*]}"; '
        "COMP_WORDS=(dotmorph wat); COMP_CWORD=1; _dotmorph; echo \"${COMPREPLY[*]}\""
    )
    out = subprocess.run(["bash", "-c", probe], capture_output=True, text=True).stdout.split("\n")
    assert set(out[0].split()) == {"webp", "webm"}
    assert out[1] == "watch"


def test_completion_install_goes_to_user_dirs(capsys):
    assert main(["completions", "fish", "--install"]) == 0
    assert completions.install_path("fish").exists()
    assert main(["completions", "zsh", "--install"]) == 0
    assert "fpath=" in capsys.readouterr().out
