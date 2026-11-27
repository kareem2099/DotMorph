"""DotMorph's UI sounds, synthesized from scratch: sine and noise envelopes, no samples and no
licences to track. Writes src/dotmorph/ui/sounds/<event>.oga (Ogg Vorbis, mono).

    python packaging/sounds.py      # needs ffmpeg with libvorbis

The files are committed; run this only to change a sound.
"""

from __future__ import annotations

import math
import random
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "dotmorph" / "ui" / "sounds"
RATE = 44100
rng = random.Random(7)  # the same sounds on every run


def samples(seconds: float) -> list[float]:
    return [0.0] * int(RATE * seconds)


def env(t: float, attack: float, decay: float) -> float:
    """Fast attack, exponential decay."""
    return (t / attack if t < attack else 1.0) * math.exp(-max(0.0, t - attack) / decay)


def swoosh(seconds: float, f0: float, f1: float, rising: bool = True) -> list[float]:
    """Band of noise whose brightness sweeps f0 -> f1, with a soft bell-shaped envelope."""
    out, lp, hp = samples(seconds), 0.0, 0.0
    n = len(out)
    for i in range(n):
        x = i / n
        cutoff = f0 + (f1 - f0) * (x if rising else 1 - x)
        a = 1 - math.exp(-2 * math.pi * cutoff / RATE)
        lp += a * (rng.uniform(-1, 1) - lp)
        hp += 0.02 * (lp - hp)  # remove rumble
        out[i] = (lp - hp) * math.sin(math.pi * x) ** 2
    return out


def tone(seconds: float, freq: float, decay: float, partials=((1, 1.0),),
         attack: float = 0.004) -> list[float]:
    out = samples(seconds)
    for i in range(len(out)):
        t = i / RATE
        out[i] = env(t, attack, decay) * sum(a * math.sin(2 * math.pi * freq * k * t)
                                             for k, a in partials)
    return out


def mix(*parts: tuple[list[float], float, float]) -> list[float]:
    """(signal, start seconds, gain) -> one signal."""
    out = [0.0] * max(int(s * RATE) + len(sig) for sig, s, _g in parts)
    for sig, start, gain in parts:
        o = int(start * RATE)
        for i, v in enumerate(sig):
            out[o + i] += v * gain
    return out


def fade(data: list[float], seconds: float = 0.05) -> list[float]:
    n = min(len(data), int(seconds * RATE))
    for i in range(n):
        data[-1 - i] *= i / n
    return data


def sounds() -> dict[str, tuple[list[float], float]]:
    """event -> (signal, peak level)."""
    s = {}
    # hovering a sector: a tiny glassy tick
    s["tick"] = tone(0.06, 2600, 0.014, ((1, 1), (2.7, 0.3))), 0.4
    # the wheel blooming open: a rising airy swoosh plus a soft rising tone
    rise = samples(0.42)
    for i in range(len(rise)):
        t = i / RATE
        rise[i] = math.sin(2 * math.pi * (320 + 700 * (t / 0.42) ** 1.5) * t) * \
            math.sin(math.pi * t / 0.42) ** 2
    s["bloom"] = mix((swoosh(0.42, 400, 5000), 0, 1.0), (rise, 0, 0.35)), 0.5
    # picking a format: a crisp two-layer click
    s["click"] = mix((tone(0.05, 1900, 0.008), 0, 1.0), (tone(0.08, 820, 0.02), 0.004, 0.6)), 0.5
    # done: two bell notes (C6 then G6) with a few sparkles for the particle burst
    bell = ((1, 1.0), (2.76, 0.25), (5.4, 0.08))
    sparkles = [(tone(0.05, rng.uniform(3500, 6500), 0.01), rng.uniform(0.05, 0.4),
                 rng.uniform(0.08, 0.2)) for _ in range(10)]
    s["chime"] = fade(mix((tone(0.7, 1046.5, 0.22, bell), 0, 1.0),
                          (tone(0.6, 1568.0, 0.25, bell), 0.09, 0.9), *sparkles), 0.15), 0.55
    # failed: a low, muted thud that goes down, under the shake
    thud = samples(0.28)
    for i in range(len(thud)):
        t = i / RATE
        thud[i] = env(t, 0.005, 0.06) * math.sin(2 * math.pi * (150 - 70 * t / 0.28) * t)
    s["thud"] = mix((thud, 0, 1.0), (tone(0.2, 300, 0.03), 0.0, 0.25),
                    (swoosh(0.12, 200, 900), 0, 0.3)), 0.6
    # docking to the edge: a quick downward zip and a magnetic thump
    zip_ = samples(0.05)
    for i in range(len(zip_)):
        t = i / RATE
        zip_[i] = math.sin(2 * math.pi * (1400 - 1000 * t / 0.05) * t) * (1 - t / 0.05)
    s["snap"] = mix((zip_, 0, 0.5), (tone(0.25, 95, 0.06, ((1, 1), (2, 0.4))), 0.02, 1.0)), 0.6
    # cancel: a soft swoosh falling away
    s["cancel"] = swoosh(0.3, 500, 3500, rising=False), 0.3
    return s


def write_wav(path: Path, data: list[float], peak: float) -> None:
    m = max(abs(v) for v in data) or 1.0
    frames = b"".join(struct.pack("<h", int(max(-1, min(1, v / m * peak)) * 32767)) for v in data)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, (data, peak) in sounds().items():
            wav = Path(tmp) / f"{name}.wav"
            write_wav(wav, data, peak)
            dest = OUT / f"{name}.oga"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
                            "-c:a", "libvorbis", "-q:a", "3", "-map_metadata", "-1",
                            "-fflags", "+bitexact", "-flags:a", "+bitexact", str(dest)],
                           check=True)
            print(f"{dest.relative_to(OUT.parent.parent.parent.parent)}  "
                  f"{len(data) / RATE:.2f} s  {dest.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
