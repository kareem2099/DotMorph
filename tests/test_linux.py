"""Desktop integration. Nothing here touches your real settings: every test redirects the
XDG directories into tmp_path and fakes gsettings."""

import os
import stat
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

import pytest
from conftest import make_png

from dotmorph.linux import clipboard, hotkey, integrate, ipc, notify, paths, watch


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    (tmp_path / "run").mkdir(mode=0o700)
    monkeypatch.setattr(paths, "launcher", lambda: ["/opt/Dot Morph/bin/dotmorph"])
    return tmp_path


# ---- small helpers --------------------------------------------------------------------


def test_desktop_exec_quotes_paths_and_keeps_field_codes(xdg):
    assert paths.desktop_exec("convert", "%F") == '"/opt/Dot Morph/bin/dotmorph" convert %F'
    assert paths.shell_command("--clipboard") == "'/opt/Dot Morph/bin/dotmorph' --clipboard"


def test_parse_uri_list(tmp_path):
    a = make_png(tmp_path / "a b.png")
    text = f"copy\nfile://{str(a).replace(' ', '%20')}\n# comment\nfile://otherhost/x.png\n"
    assert clipboard.parse_uri_list(text) == [a]


def test_notification_text_and_show_items(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "it's.png"
    assert notify.message([a], []) == ("Converted", "a.png")
    assert notify.message([], ["x: boom"])[0] == "Conversion failed"
    arg = notify.show_items_arg([a, b])
    assert arg.startswith("['file://") and "it%27s.png" in arg  # quotes are %-encoded


def test_notify_runs_detached(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(notify.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(notify, "_supports_actions", lambda: True)
    monkeypatch.setattr(notify.subprocess, "Popen", lambda cmd, **kw: calls.append((cmd, kw)))
    assert notify.notify([tmp_path / "a.png"])
    cmd, kw = calls[0]
    assert cmd[:2] == ["sh", "-c"] and kw["start_new_session"]
    assert cmd[-2] == str(tmp_path.resolve()) and cmd[-1] == "Open folder"


# ---- integrate ------------------------------------------------------------------------

USER_UCA = """<?xml version="1.0" encoding="UTF-8"?>
<actions><action><icon>utilities-terminal</icon><name>Open Terminal Here</name>
<unique-id>1234-1</unique-id><command>exo-open --launch TerminalEmulator</command>
<description/><patterns>*</patterns><directories/></action></actions>
"""


def test_integrate_install_and_remove_keeps_user_thunar_actions(xdg):
    uca = xdg / "config" / "Thunar" / "uca.xml"
    uca.parent.mkdir(parents=True)
    uca.write_text(USER_UCA)

    written = integrate.install()
    data = xdg / "data"
    desktop = (data / "applications" / "dotmorph.desktop").read_text()
    assert 'Exec="/opt/Dot Morph/bin/dotmorph" %F' in desktop
    assert "image/png;" in desktop and "video/mp4;" in desktop

    script = data / "nautilus" / "scripts" / "DotMorph" / "To PNG"
    assert script.stat().st_mode & stat.S_IXUSR
    body = script.read_text()
    assert "convert --to png --notify -q $NAUTILUS_SCRIPT_SELECTED_FILE_PATHS" in body
    assert (data / "nemo" / "actions" / "dotmorph-png.nemo_action").exists()
    dolphin = (data / "kio" / "servicemenus" / "dotmorph.desktop").read_text()
    assert "X-KDE-Submenu=DotMorph" in dolphin
    assert (data / "icons" / "hicolor" / "scalable" / "apps" / "dotmorph.svg").exists()

    ids = [a.findtext("unique-id") for a in ET.parse(uca).getroot()]
    assert "1234-1" in ids and "dotmorph-wheel" in ids and "dotmorph-png" in ids
    png = next(a for a in ET.parse(uca).getroot() if a.findtext("unique-id") == "dotmorph-png")
    patterns = png.findtext("patterns").split(";")
    assert "*.jpg" in patterns and "*.JPEG" in patterns and "*.png" not in patterns
    assert png.findtext("submenu") == "DotMorph"

    integrate.install()  # running twice must not duplicate anything
    ids = [a.findtext("unique-id") for a in ET.parse(uca).getroot()]
    assert ids.count("dotmorph-png") == 1

    removed = integrate.remove()
    assert all(not p.exists() for p in written if p != uca)
    assert [a.findtext("unique-id") for a in ET.parse(uca).getroot()] == ["1234-1"]
    assert removed and not integrate.manifest_path().exists()


def test_integrate_never_clobbers_an_unreadable_uca(xdg):
    uca = xdg / "config" / "Thunar" / "uca.xml"
    uca.parent.mkdir(parents=True)
    uca.write_text("<actions><broken>")
    integrate.install()
    assert uca.read_text() == "<actions><broken>"


# ---- hotkey (gsettings faked) ---------------------------------------------------------


class FakeGsettings:
    def __init__(self):
        self.store = {
            (hotkey.MEDIA_KEYS, "custom-keybindings"): "['/x/custom0/']",
            (f"{hotkey.CUSTOM_SCHEMA}:/x/custom0/", "binding"): "'<Super>t'",
            (f"{hotkey.CUSTOM_SCHEMA}:/x/custom0/", "name"): "'Terminal'",
        }

    def __call__(self, *args):
        verb = args[0]
        if verb == "get":
            return self.store.get((args[1], args[2]), "''")
        if verb == "set":
            value = args[3] if args[2] == "custom-keybindings" else repr(args[3])
            self.store[(args[1], args[2])] = value
            return ""
        if verb == "list-recursively":
            if args[1] == "org.gnome.shell.keybindings":
                return "org.gnome.shell.keybindings toggle-message-tray ['<Super>v', '<Super>m']"
            return ""
        if verb == "reset-recursively":
            for key in [k for k in self.store if k[0] == args[1]]:
                del self.store[key]
            return ""
        raise AssertionError(args)


def test_gnome_hotkey_appends_detects_conflicts_and_removes(xdg, monkeypatch):
    fake = FakeGsettings()
    monkeypatch.setattr(hotkey, "_gsettings", fake)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setattr(hotkey.shutil, "which", lambda name: f"/usr/bin/{name}")

    with pytest.raises(hotkey.HotkeyError, match="toggle-message-tray"):
        hotkey.install("<Super>m")  # GNOME's own notification list
    with pytest.raises(hotkey.HotkeyError, match="Terminal"):
        hotkey.install("<Super>t")  # another custom shortcut

    result = hotkey.install()
    assert result.binding == "<Super><Shift>m"
    listed = fake.store[(hotkey.MEDIA_KEYS, "custom-keybindings")]
    assert "/x/custom0/" in listed and hotkey.OUR_PATH in listed  # others kept
    ours = f"{hotkey.CUSTOM_SCHEMA}:{hotkey.OUR_PATH}"
    assert "--clipboard" in fake.store[(ours, "command")]

    assert hotkey.remove()
    assert hotkey.OUR_PATH not in fake.store[(hotkey.MEDIA_KEYS, "custom-keybindings")]
    assert "/x/custom0/" in fake.store[(hotkey.MEDIA_KEYS, "custom-keybindings")]


def test_unknown_desktop_gets_instructions(monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
    with pytest.raises(hotkey.HotkeyError, match="--clipboard"):
        hotkey.install()


# ---- watch ----------------------------------------------------------------------------


def test_watch_converts_new_files_only_once(tmp_path):
    lines = []
    w = watch.Watcher([tmp_path], "webp", {"png"}, log=lines.append)
    thread = threading.Thread(target=w.run, daemon=True)
    thread.start()
    # wait until the inotify watches are really in place (slow CI runners need a while)
    ready = time.monotonic() + 20
    while not any(line.startswith("watching") for line in lines):
        assert time.monotonic() < ready, "watcher did not start"
        time.sleep(0.05)
    make_png(tmp_path / ".hidden.png")
    part = tmp_path / "shot.png.part"  # browsers download then rename
    make_png(tmp_path / "tmp.png").rename(part)
    part.rename(tmp_path / "shot.png")
    make_png(tmp_path / "a.png")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not {"a.webp", "shot.webp"} <= {
        p.name for p in tmp_path.glob("*.webp")
    }:
        time.sleep(0.1)
    time.sleep(1.0)  # give it a chance to (wrongly) loop on its own output
    w.stop.set()
    thread.join(3)
    names = sorted(p.name for p in tmp_path.glob("*.webp"))
    assert names == ["a.webp", "shot.webp"], lines
    assert not (tmp_path / ".hidden.webp").exists()


def test_watch_rejects_impossible_targets(tmp_path):
    from dotmorph.core.common import ConversionError

    with pytest.raises(ConversionError):
        watch.Watcher([tmp_path], "webp", {"mp3"})


def test_watch_service_unit(xdg):
    unit = watch.install_service(["/home/me/Downloads", "--to", "jpg"],
                                 ["/home/me/Downloads"], "jpg", start=False)
    text = unit.read_text()
    assert "ExecStart='/opt/Dot Morph/bin/dotmorph' watch /home/me/Downloads --to jpg" in text
    assert "WantedBy=default.target" in text
    assert watch.installed_services() == [unit]
    assert watch.remove_service(unit.stem, stop=False)
    assert watch.installed_services() == []


# ---- daemon ---------------------------------------------------------------------------


@pytest.mark.skipif(pytest.importorskip("PySide6") is None, reason="needs PySide6")
def test_daemon_round_trip(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    env = dict(os.environ, XDG_RUNTIME_DIR=str(run), QT_QPA_PLATFORM="offscreen")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run))
    proc = subprocess.Popen([sys.executable, "-m", "dotmorph", "daemon"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(150):  # Qt can take several seconds to start on a busy CI runner
            if ipc.daemon_running():
                break
            time.sleep(0.2)
        info = ipc.daemon_running()
        assert info and info["visible"] is False
        assert ipc.request({"cmd": "open", "files": [str(make_png(tmp_path / "a.png"))]})["ok"]
        time.sleep(0.5)
        assert ipc.daemon_running()["visible"] is True
        assert ipc.request({"cmd": "reload"})["ok"]  # the settings window saved something
        assert ipc.request({"cmd": "quit"})["ok"]
        proc.wait(timeout=10)
        assert proc.returncode == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    assert not ipc.daemon_running()
