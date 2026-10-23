# DotMorph 2.0 "Overdrive" plan

Goal: take DotMorph from an alpha with 4 image formats to a Linux-native converter
with a GPU-animated wheel, dozens of conversions, and deep desktop integration.

Available on the dev box (Kali / Xfce, X11): `ffmpeg`, `magick`, `gs`, `pdftoppm`,
`libreoffice`, `pandoc`, `cwebp`, `xdotool`, `xclip`, `notify-send`, `gdbus`,
Thunar / Nautilus / Dolphin. Pillow 13 (AVIF + WebP built in), PySide6 6.12 with
QtQuick.Shapes, QtQuick.Particles, QtQuick.Effects, QtDBus.

---

## Phase A: Engine with pluggable backends ✅ done (440 conversions live, 39 tests)

Replace the hard-coded `TARGETS` dict with a backend registry.

```
core/
  registry.py        Backend protocol, build the live matrix from installed tools
  backends/
    pillow.py        png jpg webp avif gif bmp tiff ico (+ heic if pillow-heif)
    poppler.py       pdf -> png/jpg (existing code, moved)
    ghostscript.py   pdf compress (screen/ebook/printer presets)
    magick.py        svg -> png/pdf, psd/xcf -> png, anything Pillow can't read
    ffmpeg.py        video + audio + video -> gif
    office.py        libreoffice --headless: docx/odt/pptx/xlsx -> pdf, docx <-> odt
    pandoc.py        md -> html/docx/odt, html -> md
  tasks.py           non-format actions: resize, strip metadata, rotate, merge to PDF
```

- Each backend declares `pairs` (src -> dst), `tools` it needs, and `available()`
  (`shutil.which`). The wheel and `dotmorph formats` only show what really works.
- Categories for the UI: Image, Video, Audio, Document, Tools.
- New conversions:
  - Image: + AVIF, GIF, BMP, TIFF, ICO, HEIC (optional), SVG input
  - Images -> one PDF (merge), PDF -> compressed PDF
  - Video: mp4, mkv, webm, mov, avi; video -> gif (palettegen, nice quality); video -> mp3
  - Audio: mp3, wav, flac, ogg, opus, m4a
  - Docs: docx / odt / pptx / xlsx -> pdf; docx <-> odt; md -> html / docx
  - Tools: resize 50% / 25%, strip EXIF, compress, rotate 90
- Real progress: ffmpeg `-progress pipe:1`, pdftoppm per page, per-file for batches.
- Cancellation (kill the subprocess) and a per-job timeout.
- Parallel batches (`-j N`, defaults to CPU count for image jobs).

## Phase B: "Overdrive" animation (QML rewrite) ✅ done (offscreen-rendered and tested; needs a real-desktop try)

Replace the `Canvas` wheel (repaints everything on CPU) with `QtQuick.Shapes`
sectors so each one animates on its own, on the GPU.

- **Open:** sectors fly out from the centre one after another (staggered OutBack),
  slight spin-in, glowing ring fades up (`MultiEffect` blur + glow).
- **Hover:** sector pushes outward and grows, gradient fill, label/icon bounces,
  soft "magnetic" pull toward the pointer, haptic-like tick sound optional.
- **Two rings:** first ring = categories; hovering one blooms an outer ring with
  its targets (handles 20+ formats without clutter).
- **Drag over:** ripple waves from the drop point, pulsing border.
- **Converting:** the centre becomes a circular progress arc with a % counter and an
  orbiting particle.
- **Done:** particle burst (`QtQuick.Particles`) + checkmark that draws itself.
  **Failed:** shake + red pulse with the error.
- **Close:** implode into the centre before quitting.
- Format icons (SVG, one per category), themes dark / light / glass, honours a
  `reduce-motion` setting.
- Keyboard: arrows / Tab to move, Enter to convert, Backspace to go back a ring.

## Phase C: Linux-native integration ✅ done (tests use sandboxed XDG dirs; not yet installed on the real desktop)

- **Daemon + instant open:** `dotmorph daemon` keeps Qt loaded; `dotmorph FILE`
  talks to it over `QLocalServer`, so the wheel appears in ~50 ms instead of ~1 s.
- **Global hotkey (X11):** Super+M opens the wheel with the files currently copied
  in the file manager (reads `text/uri-list` from the clipboard).
- **File manager actions:** `dotmorph integrate` installs
  Thunar custom action (`uca.xml`), Nautilus script, Dolphin service menu,
  Nemo action, plus a `.desktop` file with MimeTypes ("Open with DotMorph").
  `dotmorph integrate --remove` undoes it.
- **Notifications over D-Bus** with an "Open folder" button that selects the file
  (`org.freedesktop.FileManager1.ShowItems`).
- **Watch folders:** `dotmorph watch ~/Downloads --from heic --to jpg` (inotify),
  plus `dotmorph watch --install` that writes a systemd **user** service.
- **`dotmorph doctor`:** lists every backend, what's missing, and the exact install
  command for the distro (apt / dnf / pacman / zypper, read from `/etc/os-release`).

## Phase D: CLI power-ups ✅ done

- `convert` gains `--resize`, `--strip`, `--preset`, `-j N`, a live progress bar,
  `--dry-run`.
- `formats` grouped by category, greys out what's missing.
- Shell completions for bash / zsh / fish (`dotmorph completions zsh`).

## Phase E: Tests, docs, release ✅ done (75 tests, demo GIF, CHANGELOG, released as 2.0.0)

- Tests per backend, auto-skipped when the tool isn't installed.
- Update README, ROADMAP, demo GIF of the new animations.
- Version 2.0.0 (first stable release).

---

## Order and size

| # | Phase | Size | Depends on |
|---|-------|------|------------|
| 1 | A: engine + new formats | large | — |
| 2 | B: animated wheel | large | A (categories) |
| 3 | C: Linux integration | medium | A |
| 4 | D: CLI | small | A |
| 5 | E: tests / docs | small | all |

Wayland stays in "Later" as before.
