"""Release packaging: versions agree, generated assets are current, .deb / AUR / AppImage
inputs are right. Builds write to a temp dir, never to the repository's dist/."""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def build():
    spec = importlib.util.spec_from_file_location("dotmorph_build", ROOT / "packaging/build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_versions_agree_and_assets_are_current(build, capsys):
    build.main(["check"])  # raises SystemExit with the list of problems otherwise
    assert "ok: version" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="does not match"):
        build.main(["check", "--tag", "v9.9.9"])


def test_release_notes_come_from_the_changelog(build):
    notes = build.release_notes(build.version())
    assert "### " in notes and "## [" not in notes
    assert notes.rstrip().endswith(f"blob/v{build.version()}/CHANGELOG.md")
    older = build.release_notes("2.0.0")
    assert "### Highlights" in older and "## [0.1.0]" not in older
    assert "AppImage is about" not in older


def test_desktop_and_appstream_files_validate(build):
    linux = ROOT / "packaging/linux"
    if shutil.which("desktop-file-validate"):
        proc = subprocess.run(["desktop-file-validate", *map(str, linux.glob("*.desktop"))],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    if shutil.which("appstreamcli"):
        proc = subprocess.run(["appstreamcli", "validate", "--no-net",
                               str(linux / f"{build.APP_ID}.metainfo.xml")],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout
    desktop = (linux / "dotmorph.desktop").read_text()
    assert "Exec=dotmorph %F" in desktop and "video/mp4;" in desktop and "image/heic;" in desktop
    assert all((linux / "icons" / f"dotmorph-{s}.png").exists() for s in build.PNG_SIZES)


def test_install_share_layout(build, tmp_path):
    build.install_share(tmp_path, zsh_dir="share/zsh/vendor-completions")
    usr = tmp_path / "usr/share"
    for rel in ("applications/dotmorph.desktop", "applications/dotmorph-settings.desktop",
                f"metainfo/{build.APP_ID}.metainfo.xml", "man/man1/dotmorph.1.gz",
                "icons/hicolor/scalable/apps/dotmorph.svg",
                "icons/hicolor/48x48/apps/dotmorph.png",
                "bash-completion/completions/dotmorph", "zsh/vendor-completions/_dotmorph",
                "fish/vendor_completions.d/dotmorph.fish"):
        assert (usr / rel).is_file(), rel


@pytest.mark.skipif(not shutil.which("dpkg-deb"), reason="dpkg-deb not installed")
def test_deb_package(build, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "DIST", tmp_path)
    deb = build.cmd_deb(None)
    info = subprocess.run(["dpkg-deb", "--field", str(deb), "Package", "Version", "Depends"],
                          capture_output=True, text=True, check=True).stdout
    assert "Package: dotmorph" in info and f"Version: {build.version()}-1" in info
    assert "python3-pyside6.qtquick" in info and "qml6-module-qtquick-shapes" in info
    listing = subprocess.run(["dpkg-deb", "-c", str(deb)], capture_output=True, text=True,
                             check=True).stdout
    assert "./usr/bin/dotmorph" in listing
    assert "./usr/lib/python3/dist-packages/dotmorph/ui/qml/main.qml" in listing
    assert "__pycache__" not in listing

    root = tmp_path / "root"
    subprocess.run(["dpkg-deb", "-x", str(deb), str(root)], check=True)
    out = subprocess.run(["python3", str(root / "usr/bin/dotmorph"), "--version"],
                         env={"PYTHONPATH": str(root / "usr/lib/python3/dist-packages"),
                              "PATH": "/usr/bin:/bin"},
                         capture_output=True, text=True)
    if "No module named 'PIL'" not in out.stderr:  # system Python without Pillow: skip run
        assert out.stdout.strip() == f"dotmorph {build.version()}"


def test_aur_files(build, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "DIST", tmp_path)
    tarball = tmp_path / "src.tar.gz"
    tarball.write_bytes(b"pretend tarball")
    out = build.cmd_aur(type("A", (), {"tarball": str(tarball), "fetch": False})())
    pkgbuild = (out / "PKGBUILD").read_text()
    srcinfo = (out / ".SRCINFO").read_text()
    import hashlib

    sha = hashlib.sha256(b"pretend tarball").hexdigest()
    assert f"pkgver={build.version()}" in pkgbuild and f"sha256sums=('{sha}')" in pkgbuild
    assert f"sha256sums = {sha}" in srcinfo and "depends = pyside6" in srcinfo
    assert "packaging/build.py install-share" in pkgbuild
    if shutil.which("bash"):
        subprocess.run(["bash", "-n", str(out / "PKGBUILD")], check=True)


def test_appimage_needs_a_wheel(build, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "DIST", tmp_path)
    with pytest.raises(SystemExit, match="build the wheel first"):
        build.cmd_appimage(type("A", (), {"python": "3.12", "linux_tag": "x"})())


def _fake_appdir(root: Path, build, extra: tuple[str, ...] = ()) -> Path:
    site = root / "opt/python3.12/lib/python3.12/site-packages"
    for rel in [*build.APPIMAGE_KEEP, *extra]:
        path = site / rel.replace("*", "6")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 100)
    return site


def test_appimage_trim(build, tmp_path):
    junk = ("PySide6/lupdate", "PySide6/QtCore.pyi", "PySide6/Qt/lib/libQt6Designer.so.6",
            "PySide6/Qt/lib/libQt6QuickControls2Material.so.6",
            "PySide6/Qt/qml/QtQuick/Controls/Material/qmldir", "PySide6/Qt/qml/QtTest/qmldir",
            "PySide6/Qt/plugins/qmltooling/libqmldbg_debugger.so", "pip/__init__.py",
            "pip-25.0.dist-info/METADATA")
    site = _fake_appdir(tmp_path, build, junk)
    (site / "PySide6/Qt/lib/libQt6Designer.so").symlink_to("libQt6Designer.so.6")
    assert build.trim_appdir(tmp_path) == 100 * len(junk) + len("libQt6Designer.so.6")
    for rel in junk:
        assert not (site / rel).exists(), rel
    assert not (site / "PySide6/Qt/lib/libQt6Designer.so").is_symlink()
    for rel in build.APPIMAGE_KEEP:
        assert any(site.glob(rel)), rel
    assert build.trim_appdir(tmp_path) == 0  # idempotent


def test_appimage_trim_refuses_to_break_the_app(build, tmp_path):
    site = _fake_appdir(tmp_path, build)
    (site / "PySide6/Qt/lib/libQt6QuickControls2Basic.so.6").unlink()
    with pytest.raises(SystemExit, match="libQt6QuickControls2Basic"):
        build.trim_appdir(tmp_path)
    with pytest.raises(SystemExit, match="no site-packages"):
        build.trim_appdir(tmp_path / "empty")


def test_appimage_trim_list_spares_what_the_qml_imports(build):
    """Every QtQuick module the QML imports must stay out of APPIMAGE_TRIM."""
    import re
    from fnmatch import fnmatch

    qml = ROOT / "src/dotmorph/ui/qml"
    imports = {m for f in qml.glob("*.qml")
               for m in re.findall(r"^import (QtQuick[\w.]*)", f.read_text(), re.M)}
    assert {"QtQuick.Shapes", "QtQuick.Controls.Basic"} <= imports
    for module in imports:
        rel = "PySide6/Qt/qml/" + module.replace(".", "/") + "/qmldir"
        hits = [p for p in build.APPIMAGE_TRIM if fnmatch(rel, p) or rel.startswith(p + "/")]
        assert not hits, (module, hits)


def test_appimage_x11_libs(build, monkeypatch, tmp_path):
    """The bundled X11 libraries go next to Qt's and nothing trims them; without a container
    tool the build stops with a clear message instead of shipping an AppImage that can't start."""
    from fnmatch import fnmatch

    assert "libxkbcommon-x11.so.0" in build.APPIMAGE_X11_LIBS
    assert "libxcb-cursor.so.0" in build.APPIMAGE_X11_LIBS  # Qt 6.5+ refuses xcb without it
    for lib in build.APPIMAGE_X11_LIBS:
        rel = f"PySide6/Qt/lib/{lib}"
        assert not [p for p in build.APPIMAGE_TRIM if fnmatch(rel, p)], lib
    monkeypatch.setattr(build.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="docker"):
        build.fetch_x11_libs(tmp_path)
    with pytest.raises(SystemExit, match="docker"):
        build.cmd_appimage_test(type("A", (), {"appimage": str(tmp_path / "x.AppImage")})())


def test_launcher_inside_an_appimage(tmp_path, monkeypatch):
    from dotmorph.linux import paths

    image = tmp_path / "DotMorph-2.0.0-x86_64.AppImage"
    image.write_text("")
    monkeypatch.setenv("APPIMAGE", str(image))
    assert paths.launcher() == [str(image)]
    monkeypatch.setenv("APPIMAGE", str(tmp_path / "gone.AppImage"))
    assert paths.launcher() != [str(tmp_path / "gone.AppImage")]


def test_sums_and_signatures(build, tmp_path, monkeypatch):
    for name in ("DotMorph-2.0.0-x86_64.AppImage", "dotmorph_2.0.0-1_all.deb", "PKGBUILD"):
        (tmp_path / name).write_text(name)
    (tmp_path / "RELEASE_NOTES.md").write_text("notes")
    sums = build.write_sums(tmp_path)
    listed = [line.split("  ")[1] for line in sums.read_text().splitlines()]
    assert listed == ["DotMorph-2.0.0-x86_64.AppImage", "PKGBUILD", "dotmorph_2.0.0-1_all.deb"]
    if shutil.which("sha256sum"):
        subprocess.run(["sha256sum", "-c", build.SUMS], cwd=tmp_path, check=True,
                       capture_output=True)
    if not shutil.which("gpg"):
        return
    home = tmp_path.parent / "gnupg"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("GNUPGHOME", str(home))  # a throwaway keyring, never the user's
    monkeypatch.delenv("GPG_PASSPHRASE", raising=False)
    subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-gen-key",
                    "DotMorph Test <test@invalid>", "ed25519", "sign", "1d"],
                   check=True, capture_output=True)
    try:
        signed = build.sign(tmp_path)
        assert {p.name for p in signed} == {f"{n}.asc" for n in listed + [build.SUMS]}
        assert (tmp_path / build.PUBKEY).read_text().startswith("-----BEGIN PGP PUBLIC KEY")
        for asc in signed:
            subprocess.run(["gpg", "--batch", "--verify", str(asc), str(asc)[:-4]],
                           check=True, capture_output=True)
        (tmp_path / "PKGBUILD").write_text("tampered")
        bad = subprocess.run(["gpg", "--batch", "--verify", str(tmp_path / "PKGBUILD.asc"),
                              str(tmp_path / "PKGBUILD")], capture_output=True)
        assert bad.returncode != 0
    finally:
        subprocess.run(["gpgconf", "--kill", "gpg-agent"], capture_output=True)


def test_generated_assets_do_not_depend_on_the_machine(build, monkeypatch):
    """CI regenerates packaging/linux/ and compares: nothing may depend on CPU count,
    the system MIME database or the Python version."""
    import mimetypes
    import os

    first = build.text_assets()
    monkeypatch.setattr(os, "cpu_count", lambda: 2)
    monkeypatch.setattr(mimetypes, "guess_type", lambda *a, **k: (None, None))
    assert build.text_assets() == first
    monkeypatch.setattr(os, "cpu_count", lambda: 64)
    assert build.text_assets() == first


def test_every_format_has_a_freedesktop_mime_type():
    from dotmorph.core.formats import FORMATS
    from dotmorph.linux.integrate import MIME

    assert set(FORMATS) <= set(MIME)
    assert MIME["ts"] == ["video/mp2t"] and MIME["3gp"] == ["video/3gpp"]


def test_appimage_launcher_has_one_name(build):
    """python-appimage names the image after the last Name= line."""
    desktop = build.appimage_desktop()
    names = [ln for ln in desktop.splitlines() if ln.startswith("Name=")]
    assert names == ["Name=DotMorph"]
    assert "Desktop Action" not in desktop and "Actions=" not in desktop
    assert "Exec=dotmorph %F" in desktop
