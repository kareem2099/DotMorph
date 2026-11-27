"""UI sounds: which events play, the off switches, the rate limit and the fallback order."""

import os
import subprocess
from types import SimpleNamespace

import pytest

from dotmorph import settings
from dotmorph.ui import sound
from dotmorph.ui.sound import EVENTS, Canberra, Player, sound_file

REAL_DESKTOP_ALLOWS = sound.desktop_allows  # the fixture below swaps it out


class FakeLib:
    """Stands in for libcanberra: records ca_context_play's properties."""

    def __init__(self, play_result=0):
        self.played, self.props, self.play_result = [], [], play_result

    def ca_context_create(self, ref):
        ref._obj.value = 1234
        return 0

    def ca_context_change_props(self, ctx, *args):
        self.props.append(args)
        return 0

    def ca_context_play(self, ctx, cid, *args):
        assert args[-1] is None  # NULL-terminated, or libcanberra reads garbage
        pairs = dict(zip(args[:-1:2], args[1:-1:2], strict=True))
        self.played.append({k.decode(): v.decode() for k, v in pairs.items()})
        return self.play_result


def prefs(**kw):
    return SimpleNamespace(**{"sound": True, "sound_volume": 70, "sound_ticks": False, **kw})


@pytest.fixture(autouse=True)
def quiet_desktop(monkeypatch):
    """Never touch the real sound server or gsettings."""
    monkeypatch.setattr(sound, "desktop_allows", lambda: True)
    monkeypatch.setattr(sound.shutil, "which", lambda name: None)
    monkeypatch.delenv("DOTMORPH_SOUND", raising=False)


def test_every_event_has_a_small_sound_file():
    total = 0
    for name in EVENTS:
        path = sound_file(name)
        assert path.exists(), name
        total += path.stat().st_size
    assert total < 150_000  # the plan's budget for all of them


def test_canberra_gets_file_role_and_volume():
    lib = FakeLib()
    player = Player(prefs(sound_volume=50), canberra=Canberra(lib))
    assert player.play("chime") == "canberra"
    props = lib.played[0]
    assert props["media.filename"] == str(sound_file("chime"))
    assert props["media.role"] == "event" and props["event.id"] == "dotmorph-chime"
    assert props["canberra.volume"] == "-6.0"  # 50 % is -6 dB
    assert b"DotMorph" in lib.props[0]


@pytest.mark.parametrize("off", [
    dict(sound=False), dict(sound_volume=0),
])
def test_settings_turn_it_off(off):
    lib = FakeLib()
    assert Player(prefs(**off), canberra=Canberra(lib)).play("click") is None
    assert not lib.played


def test_mute_env_and_desktop_switches(monkeypatch):
    lib = FakeLib()
    player = Player(prefs(), canberra=Canberra(lib))
    player.muted = True
    assert player.play("click") is None
    player.muted = False
    monkeypatch.setenv("DOTMORPH_SOUND", "0")
    assert player.play("click") is None
    monkeypatch.delenv("DOTMORPH_SOUND")
    monkeypatch.setattr(sound, "desktop_allows", lambda: False)
    assert player.play("click") is None
    assert not lib.played
    monkeypatch.setattr(sound, "desktop_allows", lambda: True)
    assert player.play("click") == "canberra"


def test_hover_ticks_are_opt_in_and_rate_limited(monkeypatch):
    lib = FakeLib()
    player = Player(prefs(), canberra=Canberra(lib))
    assert player.play("tick") is None  # off by default
    player = Player(prefs(sound_ticks=True), canberra=Canberra(lib))
    clock = iter([10.0, 10.02, 10.07, 10.08]).__next__
    monkeypatch.setattr(sound.time, "monotonic", clock)
    played = [player.play("tick") for _ in range(4)]
    assert played == ["canberra", None, "canberra", None]  # at most one per 60 ms


def test_unknown_events_and_test_button():
    lib = FakeLib()
    player = Player(prefs(sound=False), canberra=Canberra(lib))
    assert player.play("explosion") is None
    assert player.play("chime", force=True) == "canberra"  # "Play test" plays even if off


def test_settings_are_read_at_play_time():
    current = prefs()
    player = Player(lambda: current, canberra=Canberra(FakeLib()))
    assert player.play("click") == "canberra"
    current = prefs(sound=False)  # the settings window saved; the daemon reloaded
    assert player.play("snap") is None


def test_falls_back_to_pw_play_then_paplay_then_silence(monkeypatch):
    started = []

    class FakeProc:
        def __init__(self, cmd, **kw):
            started.append(cmd)

        def poll(self):
            return 0

    monkeypatch.setattr(sound.subprocess, "Popen", FakeProc)
    tools = {"pw-play": "/usr/bin/pw-play", "paplay": "/usr/bin/paplay"}
    monkeypatch.setattr(sound.shutil, "which", lambda name: tools.get(name))
    player = Player(prefs(sound_volume=40), canberra=None)
    assert player.play("click") == "pw-play"
    assert started[-1] == ["/usr/bin/pw-play", "--volume=0.40", str(sound_file("click"))]
    del tools["pw-play"]
    assert player.play("snap") == "paplay"
    assert "--property=media.role=event" in started[-1]
    tools.clear()
    assert player.play("chime") is None


def test_canberra_failure_falls_back(monkeypatch):
    monkeypatch.setattr(sound.subprocess, "Popen", lambda cmd, **kw: SimpleNamespace(poll=None))
    monkeypatch.setattr(sound.shutil, "which", lambda name: "/usr/bin/pw-play"
                        if name == "pw-play" else None)
    player = Player(prefs(), canberra=Canberra(FakeLib(play_result=-1)))
    assert player.play("click") == "pw-play"


def test_a_broken_backend_never_raises():
    class Boom:
        def play(self, *a):
            raise RuntimeError("sound server on fire")

    assert Player(prefs(), canberra=Boom()).play("click") is None


def test_gnome_event_sounds_switch(monkeypatch):
    check = REAL_DESKTOP_ALLOWS  # with a fake gsettings
    monkeypatch.setattr(sound.shutil, "which", lambda name: "/usr/bin/gsettings")
    calls = []

    def gsettings(out):
        def run(*a, **k):
            calls.append(out)
            return subprocess.CompletedProcess(a, 0, out, "")
        return run

    sound.forget_desktop()
    monkeypatch.setattr(sound.subprocess, "run", gsettings("false\n"))
    assert check() is False
    monkeypatch.setattr(sound.subprocess, "run", gsettings("true\n"))
    assert check() is False and len(calls) == 1  # remembered for a while, not asked each time
    t0 = sound.time.monotonic()
    monkeypatch.setattr(sound.time, "monotonic", lambda: t0 + sound.DESKTOP_RECHECK + 1)
    assert check() is True  # switched back on: noticed without a restart
    sound.forget_desktop()


def test_sound_settings_are_cleaned():
    s = settings.Settings(sound=1, sound_volume=400, sound_ticks=0).clean()
    assert (s.sound, s.sound_volume, s.sound_ticks) == (True, 100, False)
    assert settings.Settings().sound and not settings.Settings().sound_ticks


def test_mute_flag_reaches_the_daemon(monkeypatch):
    from dotmorph import app

    assert app._gui_args(["--mute", "a.png"]).mute
    assert not app._gui_args(["a.png"]).mute


# ---- QML: each state change plays its sound once ---------------------------------------

pytest.importorskip("PySide6.QtQuick")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_wheel_plays_each_event_once(tmp_path):
    from conftest import make_png
    from PySide6.QtCore import Q_ARG, QEventLoop, QMetaObject, QObject, QTimer, QUrl, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem

    from dotmorph.ui.bridge import Bridge
    from dotmorph.ui.dock import Dock
    from dotmorph.ui.i18n_qt import I18n
    from dotmorph.ui.window import QML_MAIN

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841

    class Recorder(QObject):
        def __init__(self):
            super().__init__()
            self.calls = []

        @Slot(str)
        def play(self, name):
            self.calls.append(name)

    def wait(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    settings.save(settings.Settings(reduce_motion=True))
    bridge = Bridge([str(make_png(tmp_path / "a.png"))])
    rec, dock, i18n_obj = Recorder(), Dock(bridge), I18n("en")
    engine = QQmlApplicationEngine()
    for name, obj in (("sound", rec), ("bridge", bridge), ("dock", dock), ("i18n", i18n_obj)):
        engine.rootContext().setContextProperty(name, obj)
    engine.load(QUrl.fromLocalFile(str(QML_MAIN)))
    root = engine.rootObjects()[0]
    wheel = root.findChild(QQuickItem, "wheel")
    wait(50)
    assert rec.calls == ["bloom"]

    wheel.setProperty("hoverInner", 0)  # hover ticks: the player decides, QML always asks
    assert rec.calls[-1] == "tick"
    rec.calls.clear()
    # a click on a format: a real conversion, then the done chime
    QMetaObject.invokeMethod(wheel, "picked", Q_ARG("QString", "webp"))
    for _ in range(100):
        wait(50)
        if "chime" in rec.calls:
            break
    assert rec.calls == ["click", "chime"]
    assert (tmp_path / "a.webp").exists()
    bridge.finished.emit(False)
    bridge.cancelled.emit()
    assert rec.calls == ["click", "chime", "thud", "cancel"]

    import shiboken6

    shiboken6.delete(root)
