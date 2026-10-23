# Changelog

All notable changes to **DotMorph** are documented here.
DotMorph is part of [DotSuite](https://dotsuite.dev/en); its page is
[dotsuite.dev/en/product/dotmorph](https://dotsuite.dev/en/product/dotmorph).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.3] - 2026-10-24

### Added

- **AppImage updates.** The AppImage carries update information
  (`gh-releases-zsync`), and each release ships a `.zsync` file next to it, so
  AppImageUpdate and AppImageLauncher can update DotMorph from GitHub Releases and download
  only the parts that changed. The `.zsync` is summed and signed like every other file.

### Changed

- README: the AppImage no longer asks for `libxcb-cursor0` (bundled since 2.0.2).

## [2.0.2] - 2026-10-24

### Fixed

- **The AppImage now starts on systems without Qt's X11 libraries.** On a clean Ubuntu 22.04
  (and other minimal installs) it exited before showing a window: Qt's xcb plugin needs
  `libxkbcommon-x11`, `libxcb-cursor` and 14 more XCB libraries that only machines with Qt
  or a full desktop already have. The AppImage now bundles them (1.1 MB, taken from
  AlmaLinux 8, so glibc 2.28 is still the minimum).
- Two Qt plugins whose libraries are not shipped (PDF images, virtual keyboard) are left out
  of the AppImage instead of failing to load.

### Added

- `packaging/build.py appimage-test`: starts the AppImage offline on a clean Ubuntu 22.04
  X server and checks that its window opens. The release workflow runs it on every build.

## [2.0.1] - 2026-10-24

### Changed

- **The AppImage is about a third smaller** (~108 MB down to ~72 MB). The PySide6 wheels it
  bundles carry Qt developer tools DotMorph never runs: `lupdate` alone was 53 MB, plus Qt
  Designer, `qmlls`, test and compiler libraries, unused Quick Controls styles, type stubs and
  `pip`. `packaging/build.py appimage` now removes them before packing, and fails the build
  if trimming would take out anything the app loads.

## [2.0.0] - 2026-10-22 · "Overdrive"

The first stable release. DotMorph was rebuilt end to end: a new conversion engine, a new
animated wheel, and native Linux desktop integration. The jump from 0.1.0 to 2.0.0 marks
that rewrite. There was no 1.x release.

### Highlights

- **440+ conversions:** 53 formats and 6 tools on 8 backends. DotMorph detects the tools
  installed on your machine and only offers conversions that will work. It started with 9.
- **A two-ring radial menu drawn on the GPU:**
  - Categories sit on the inner ring, and each one blooms a fan of formats outward.
  - Animations throughout: fly-out, glow, hover lift, progress arc, a particle burst on
    success, and a shake on failure.
- **Edge dock:** drag the wheel against a screen edge and it becomes a slim tab. A half
  wheel opens from it, like Android's edge panels.
- **Opens in about 0.1 s** through a background daemon, instead of about 1 s to start Qt.
- **Opens from anywhere:**
  - file-manager right-click (Nautilus, Thunar, Dolphin, Nemo)
  - "Open with"
  - a global hotkey with your copied files
  - folders watched for new files
  - the terminal
- **Settings window**, with a full **Arabic** interface (right to left) and DotSuite branding.
- **Install it your way:** pipx (PyPI), AppImage, `.deb`, AUR, or from source. One tag
  publishes them all.
- **Fully local:** no uploads, no telemetry, Apache 2.0.

### Added: conversion engine

- **Pluggable backend registry** (`core/registry.py`):
  - Each backend declares what it can convert and which tools it needs, and the live table
    is built from what is installed right now.
  - When two backends can do the same conversion, the better one wins (Pillow before
    ImageMagick, librsvg before ImageMagick for SVG).
  - A broken or odd tool can never take the app down.
- **Format catalog** (`core/formats.py`): 53 formats in 4 categories, with aliases (`.jpeg`,
  `.jfif`, `.tif`, `.htm`, `.markdown`, `.mpg`, `.oga`). The menu order puts targets of the
  same category first (MP4 → MKV before MP4 → MP3), then the rest, then tools. For PDF,
  images come first.
- **Backends:**

  | Backend | Converts | Notes |
  |---------|----------|-------|
  | **Pillow** | PNG, JPG, WebP, AVIF, GIF, BMP, TIFF, ICO, TGA, image → PDF | Keeps animation (GIF / WebP / APNG / AVIF), EXIF orientation, ICC profiles and EXIF. HEIC/HEIF with the optional `heic` extra. |
  | **librsvg** | SVG → PNG, JPG, WebP, AVIF, GIF, BMP, TIFF, ICO, **vector PDF** | Called directly through ctypes, the same renderer GNOME uses, so no new dependency. Text and fonts stay real text in the PDF. |
  | **poppler** | PDF → PNG, JPG, WebP (one image per page), PDF → TXT | Progress per rendered page. |
  | **Ghostscript** | PDF compress, merge PDFs and images, PostScript → PDF | Also renders PDF pages when poppler is missing. |
  | **ImageMagick** | PSD, XCF, HEIC/HEIF, JPEG XL → any image format or PDF | Renders to PNG first and Pillow writes the result, so distro `policy.xml` limits on PDF don't get in the way. |
  | **ffmpeg** | MP4, MKV, WebM, MOV, AVI, M4V, FLV, WMV, MPEG, TS, 3GP ↔ video, GIF, audio; MP3, M4A, OGG, Opus, FLAC, WAV, AAC, WMA ↔ audio; GIF → MP4/WebM | Container swaps with the same codec are a stream copy (seconds, lossless), with a fallback to a transcode. GIF output uses a generated palette. Encoders are probed (libx264 → openh264 → mpeg4, VP9 → VP8). Live progress. |
  | **LibreOffice** | DOCX, DOC, ODT, RTF, TXT, HTML, PPTX, PPT, ODP, XLSX, XLS, ODS, CSV → PDF and between Office formats | Headless, with a private profile, so it works while LibreOffice is open. One conversion at a time. |
  | **pandoc** | Markdown, HTML, reST, Org, EPUB, DOCX, ODT → HTML, Markdown (GFM), DOCX, ODT, EPUB, TXT, PDF | Markdown → PDF goes through a PDF engine (typst, weasyprint, wkhtmltopdf, tectonic, xelatex, pdflatex), or through DOCX → LibreOffice. |

- **Tools that keep the format:**
  - `compress`: JPG, PNG (palette), WebP, AVIF, PDF (Ghostscript `/ebook`) and video
    (x264 / VP9). The result is never bigger than the original.
  - `resize-50` and `rotate-90`: images and video.
  - `strip`: removes EXIF, GPS and tags from images, video and audio. A JPEG keeps its
    quantisation tables, so there is no visible quality loss.
  - `mute`: drops the audio from a video.
  - `merge-pdf`: several images and/or PDFs into one PDF.
- **Options for every conversion:**
  - `resize` (`50%`, `1920x1080` to fit inside, or `1280` for width)
  - `strip`
  - `quality` (1–100)
  - `dpi`, with per-format defaults: PDF 150; SVG 96, which keeps its original size
  - `overwrite`
  - `timeout`
- **Real progress** from ffmpeg (`-progress`), PDF pages, and batches. When a tool can't
  report progress, the UI shows elapsed seconds instead.
- **Cancel:** kills the external tool's whole process group within about 0.5 s.
- **Parallel batches** (`jobs`). Outputs keep the input order, and LibreOffice jobs are
  serialised automatically.
- **Safe output:**
  - Every job works in a hidden `.dotmorph-*` folder next to the output, so the final move
    is a rename and half-written files never appear.
  - Existing files are never overwritten unless asked (you get `name (1).ext`).
  - Parallel jobs never claim the same name.
- **Helpful errors:**
  - A missing tool is named, with the install command for your distro (apt, dnf, pacman,
    zypper; detected from `/etc/os-release`).
  - Messages show the file name, not the full path.
  - A corrupt image says so plainly.

### Added: command line

- `dotmorph convert` gained:
  - `--resize`, `--strip`, `--quality`, `--dpi`, `--timeout`
  - `-j/--jobs`, `--notify`, `-n/--dry-run`
  - `--preset web|email|thumb|print|share`
  - a live progress bar on stderr
  - Ctrl-C cancels cleanly
  - exit codes: 0 = all converted, 1 = something failed, 130 = cancelled
- **Presets.** Explicit flags win over the preset, and `--to` is optional when the preset
  sets one.

  | Preset | Does |
  |--------|------|
  | `web` | WebP, fits 1920×1920, quality 80, no metadata |
  | `email` | JPG, fits 1280×1280, quality 75, no metadata |
  | `thumb` | WebP thumbnail, fits 320×320 |
  | `print` | PDF/SVG at 300 dpi, quality 95 |
  | `share` | `compress` in the same format, no metadata |

- `dotmorph formats` groups conversions by category. `formats FILE...` shows the targets
  for given files. `formats --missing` shows what each missing tool would add.
- `dotmorph doctor` reports:
  - every backend and its optional extras
  - missing tools, with install commands
  - the desktop integration status: daemon, file menus, hotkey, watch services, and
    `wl-paste` on Wayland
- `dotmorph completions bash|zsh|fish` prints a script generated from the real parser:
  subcommands, every flag, all 37 targets, presets and themes. `--install` writes it to
  your user completion folder.
- GUI flags: `--theme`, `--reduce-motion`, `--clipboard`, `--no-daemon`.

### Added: the wheel

- A new **QML wheel**, with sectors drawn on the GPU (QtQuick.Shapes) and a glow
  (MultiEffect):
  - **Two rings:** categories (Image, Video, Audio, Docs, Tools) inside, and that
    category's formats blooming outward in a fan. Few targets give a single ring.
  - A category with a single option is a **shortcut**: one click converts.
  - **Animations:** a staggered fly-out with a little spin, a hover lift in the
    category's colour, rings that lean toward the pointer, and an implode on close.
  - **Converting:** the centre becomes a progress arc with a percentage, or elapsed
    seconds, and a spark that orbits it. Click the centre to cancel.
  - **Success:** a check mark draws itself, with a particle burst. **Failure:** a cross,
    a shake, and the error underneath.
  - Drag-over and empty-state ripples.
- **Drag to move:** grab the wheel anywhere. It turns see-through while moving. A press
  that moves is never a click.
- **Options panel** (`O`, or the button on the rim):
  - quality slider, PDF/SVG resolution, size (75 / 50 / 25 %) and remove metadata
  - saved in `~/.config/dotmorph/settings.json`
  - a summary shows in the centre, and a dot on the button marks non-default options
- **Keyboard:** arrows / Tab, Enter / ↑, Backspace / ↓, `1`–`9`, `O`, Esc.
- **Themes:** dark, light and glass (`--theme`, or `DOTMORPH_THEME`). `--reduce-motion`
  (or `DOTMORPH_REDUCE_MOTION=1`) turns animations off.
- App icon (`dotmorph.svg`).

### Added: settings window (`dotmorph settings`)

- A separate window in the DotSuite style, with seven pages. It is also in the app menu as
  "DotMorph Settings" and as an action on the DotMorph launcher, and reachable from the
  wheel through **All settings…** in the options panel.
  - **General:**
    - theme, with a live preview of the wheel
    - reduced motion
    - language: System, English or العربية
    - notifications: long jobs, always or never
    - where converted files go: next to the original, or a folder you pick
    - default quality, resolution, size and metadata
  - **Wheel:** pin formats so they come first, or hide the ones you never use. Click once to
    pin, twice to hide, again to reset.
  - **Shortcut:** press keys to record a new global shortcut. Keys that are already taken are
    refused, and you can remove the shortcut.
  - **Integrations:** turn the daemon and the file-manager menus on and off, choose which
    quick actions the menus show, undock the edge dock, and install shell completion.
  - **Watch folders:** add a folder with a folder picker and a target format, see which
    watchers are active, and remove them.
  - **Tools:** every engine, ready or missing, with "copy install command" buttons.
  - **About:** version, links, and the settings file.
- **Saved settings** grew: theme, reduced motion, language, notification policy, output folder,
  pinned and hidden formats, and file-manager quick actions. Explicit `--theme` /
  `DOTMORPH_THEME` still win for a run.
- **Applied live:** the settings window asks a running daemon to reload, so theme, language,
  formats and the dock change immediately. The daemon writes settings by starting from
  the file, so the two never overwrite each other.

### Added: English and Arabic

- A full Arabic interface: the wheel (categories, tools, centre text, status), the options
  panel, the settings window and notifications.
- A right-to-left layout, with mirrored sliders and toggles, and an Arabic font picked
  automatically (Noto Kufi Arabic or another Noto Arabic font).
- **System** follows `LANGUAGE` / `LC_ALL` / `LANG`.
- Commands, format names and engine error messages stay English on purpose.

### Added: DotSuite branding

- The wheel's accent moved to DotSuite emerald (`#10B981`) on DotSuite's near-black and
  neutral greys. Category colours are unchanged.
- **New app icon** in the DotSuite neon style: the wheel's five sectors glowing emerald
  around a DotSuite node.
- `dotmorph integrate` also installs PNG icons (16–512 px) for panels and docks that don't
  scale SVG.
- `docs/screenshots/banner.png` (1280×640, also usable as GitHub's social preview), plus a
  new `settings.png`, and `demo.gif`, `overdrive.png` and `edge-dock.png` re-rendered in
  the new style.

### Added: packages and releases

- **PyPI:**
  - `pipx install 'dotmorph[gui]'`.
  - The `gui` extra now pulls `PySide6-Essentials` (everything the wheel needs), not the
    full PySide6: about 250 MB instead of about 700 MB.
  - The README uses absolute links and images, so it renders on PyPI.
- **AppImage:** Python, PySide6 and DotMorph in one file. Only the conversion tools come
  from your system. It pins PySide6 6.9, so it runs on glibc 2.28+ (Ubuntu 20.04, Debian 11,
  RHEL 8 and newer); PySide6 6.10+ would raise that to 2.34. Desktop integration, the hotkey, autostart and watch services point at
  the `.AppImage` file itself (`$APPIMAGE`), not at its temporary mount.
- **Debian package (`.deb`):**
  - Uses the distribution's Qt 6 and PySide6, with tools as Recommends / Suggests.
  - Byte-compiles on install. Depends on Qt / PySide6 6.6+ and Pillow 10+, so apt refuses
    releases that are too old instead of installing something broken.
  - Ships the docs, the man page, completions, icons, launchers and AppStream metainfo.
- **AUR:** a `PKGBUILD` and `.SRCINFO` generated with the tag tarball's checksum. Pushed to
  the AUR automatically when a key is configured.
- **Arch package (`.pkg.tar.zst`):** built with `makepkg` from that same PKGBUILD in an Arch
  container, checked with `namcap`, installed and smoke-tested, then attached to the release.
- **Checksums and signatures:**
  - Every release file gets an entry in `SHA256SUMS` and a detached, ASCII-armored GPG
    signature (`.asc`). `SHA256SUMS.asc` and the public key `dotmorph-signing-key.asc` are
    attached too.
  - The workflow verifies every checksum and signature before publishing.
  - PyPI uploads carry PEP 740 attestations.
- **Shared Linux assets** in `packaging/linux/`, generated from the code by
  `packaging/build.py assets` and checked in CI:
  - desktop launchers ("DotMorph", "DotMorph Settings") listing every supported MIME type
  - AppStream metainfo `io.github.kareem2099.DotMorph`, with screenshots and releases
  - the man page `dotmorph(1)`
  - icons from 16 to 512 px plus SVG
  - bash, zsh and fish completions
- **Release workflow** (`.github/workflows/release.yml`):
  - A `vX.Y.Z` tag runs the tests, checks that the tag matches the version, and builds and
    smoke-tests every package.
  - It then creates the GitHub Release with notes from this CHANGELOG, `SHA256SUMS` and `.asc`
    signatures. After the release succeeds, it publishes to PyPI with trusted publishing and
    updates the AUR.
  - A manual run is a dry run that publishes nothing.
  - The steps are in `docs/RELEASING.md`.
- **Repository files:**
  - issue forms: the bug report asks for `dotmorph doctor` output, the install method,
    the display server and the area
  - a feature request form and a pull request checklist
  - `CONTRIBUTING.md`, `SECURITY.md` (private reporting) and `CODE_OF_CONDUCT.md`
  - Sponsor links (`FUNDING.yml`)
  - Dependabot for GitHub Actions and Python dependencies
  - `.gitattributes`: generated files collapsed in diffs, binaries marked
  - `.github/setup-repo.sh`: one-time GitHub setup with `gh` (description, topics, Discussions,
    labels, security features, the `pypi` environment limited to tags, branch protection,
    and secrets with `--secrets`), with a `DRY_RUN=1` mode
- **No Flatpak, on purpose:** DotMorph runs the converters on your system and integrates
  with your file manager, hotkeys, autostart and systemd, which a Flatpak sandbox blocks.
- The Qt warning "Failed to register with host portal" no longer appears in the terminal.

### Added: edge dock

- **Dock:** drag the wheel against the left or right screen edge and it docks as a slim
  glowing tab, with a breathing light.
- **Peek:** a half wheel opens out of the edge when you hover the tab for a moment, click
  it, or drag files over it. Items are mirrored, so the first category is on top on both
  sides, and the closed half behind the edge never reacts to clicks.
- **Fold back:** it folds into the tab when the pointer leaves, after a conversion, or on
  Esc / ✕.
- **Move:** drag up and down to slide along the edge; pull away from the edge to get the
  full wheel back.
- **Hide:** right-click the tab to hide it (daemon) or quit.
- **Progress while folded:** a conversion that keeps running fills the tab bottom-up.
- **Remembered:** the side and height on the edge are saved. The daemon shows the tab at
  login, and `dotmorph FILE` opens the half wheel right there.

### Added: Linux integration

- **Daemon** (`dotmorph daemon`):
  - Keeps Qt and the wheel loaded. `dotmorph FILE` hands the files over a Unix socket in
    `$XDG_RUNTIME_DIR` with a JSON-lines protocol and stdlib only (no Qt import), and the
    wheel opens in about 0.1 s.
  - `--install` adds XDG autostart; `--status`, `--stop` and `--uninstall` manage it.
- **File managers** (`dotmorph integrate`):
  - A *DotMorph* submenu with the wheel and quick actions (To PNG / JPG / WebP / PDF / MP4 /
    MP3 / GIF, Compress) for Nautilus (Scripts), Thunar (`uca.xml`, merged and never
    clobbered), Dolphin (service menu) and Nemo (actions).
  - In Thunar and Nemo, each action only shows for files it can handle, extension aliases
    included.
  - A `.desktop` entry with MIME types for "Open with DotMorph", plus the icon.
  - Quick actions run without a window and notify when done.
  - A manifest makes `--remove` exact.
- **Global hotkey** (`dotmorph hotkey`):
  - Registered with the desktop, so it also works on Wayland: GNOME custom shortcuts
    (appended next to yours) and Xfce. Other desktops get the command to bind themselves.
  - The default is Super+Shift+M; GNOME uses Super+M itself. Keys that are already taken
    are refused unless `--force` is given.
  - Opens the wheel with the files copied in the file manager (wl-paste, xclip, xsel;
    `text/uri-list` and `x-special/gnome-copied-files`).
- **Watch folders** (`dotmorph watch DIR --to FORMAT`):
  - inotify through ctypes, with no polling and no dependency.
  - Reacts when a file is finished, including browsers' `.part` → final renames.
  - Ignores hidden files and never re-converts its own output.
  - `--install` runs it as a systemd user service; `--list` and `--uninstall` manage the
    services.
- **Notifications** (`convert --notify`, and the wheel itself after long jobs) with an
  **Open folder** button. It selects the new files through
  `org.freedesktop.FileManager1.ShowItems`, with an `xdg-open` fallback.
- **Wayland:** the wheel runs through XWayland, so it stays on top and can be placed. It
  opens centred, because Wayland doesn't expose the pointer position.

### Changed

- **SVG rendering** moved from ImageMagick's built-in renderer to librsvg. The old renderer
  broke `letter-spacing`, bold text and strokes. Against Chromium's rendering of the same
  file, the mean pixel difference dropped from 8.09 to 0.43.
- **SVG output size:** SVG now renders at its original size by default (96 dpi), instead
  of 1.56× larger. Use `--dpi 192` for 2×.
- **`dotmorph FILE`** goes through the daemon when it runs. Use `--no-daemon` for a
  separate window.
- **Window:** 380 → 560 px, to fit two rings. Still frameless, transparent and always on
  top.
- **Package metadata:** the description, keywords and classifiers were rewritten. The
  homepage is now [dotsuite.dev/en/product/dotmorph](https://dotsuite.dev/en/product/dotmorph).

### Fixed

Bugs in 0.1.0, plus those found and fixed while 2.0 was being tested on a real desktop:

- **Hotkey shake:** holding the hotkey made the wheel shake. Key repeat (every 30 ms) sent
  a new "open" each time, and each one restarted the open animation. Repeats within
  0.6 s, and requests for files already shown, are now ignored.
- **Drag treated as a click:** releasing on a sector started a conversion (and the menu
  then closed), and releasing outside the ring closed it.
- **Crash on close:** closing the menu while a conversion ran crashed the worker thread.
- **Slow cancel:** cancelling waited about 2 s for ffmpeg to flush its encoder.
- **Daemon didn't answer:** its socket server was created before the Qt event loop.
- **Long socket paths:** an unusually long `$XDG_RUNTIME_DIR` broke the Unix socket
  (108-byte limit). There is now a short private fallback path.
- **Fake 0% on GIF:** GIF making showed 0% for the whole job, because the palette pass
  reads the whole video first. It now shows elapsed time.
- **"Open with DotMorph" for `.ts` and `.3gp` videos:** they were registered as a Qt
  Linguist file and as audio. Every format now has an explicit freedesktop MIME type, so
  launchers come out the same on every machine.
- **QML warnings on exit:** "Cannot read property of null" no longer appears.

### Quality

- **94 tests** (11 at 0.1.0) covering:
  - the engine, and every backend (skipped when its tool isn't installed)
  - presets, dry run, completions (bash and zsh syntax-checked; bash completion exercised)
  - the real QML wheel offscreen: keyboard, drag, options, edge dock, hit-testing on both
    sides
  - the daemon round-trip (including reload), file-manager integration, the hotkey (with a
    fake gsettings) and watch
  - settings and translations, the settings backend, and the settings window loading every
    page in English and Arabic
  - packaging: versions agree, generated assets are current and validate (desktop-file-validate,
    appstreamcli), the `.deb` builds and runs, the AUR files render, the AppImage launcher
    path
- Tests never touch your settings: XDG folders are redirected to a temp dir.
- Timing-sensitive tests (watch folders, the daemon, cancel, GUI conversions) wait for real
  readiness instead of fixed sleeps. The suite passes with every CPU core saturated, so a
  slow CI runner doesn't block a release.
- CI runs on Python 3.10, 3.12 and 3.13. It installs poppler, Ghostscript, ImageMagick,
  ffmpeg, pandoc and librsvg, and runs the GUI tests offscreen.
- `docs/screenshots/demo.gif`, `overdrive.png`, `edge-dock.png`, `settings.png` and
  `banner.png` are rendered from the
  real QML, offscreen and frame by frame, so they can be regenerated after UI changes.

### Upgrading from 0.1.0

```bash
pipx install 'dotmorph[gui]'        # or the AppImage / .deb / AUR package
dotmorph doctor                      # see what is available and what to install
dotmorph integrate                   # optional: right-click menus
dotmorph daemon --install            # optional: instant open + edge dock at login
dotmorph hotkey                      # optional: Super+Shift+M
```

The `dotmorph convert` flags from 0.1.0 still work. Only the default `--dpi` for SVG changed.

### Supported systems

- The README has a per-distribution table: which install method works on Ubuntu, Debian,
  Kali, Fedora, RHEL, openSUSE and Arch.
- It also lists the minimum versions: Python 3.10, Qt / PySide6 6.6, Pillow 10, librsvg
  2.52, and glibc 2.28 (2.34 with Python 3.14).
- The full test suite was run on PySide6 6.9 with Python 3.13 and Pillow 10.4, as well as
  on PySide6 6.12 with Python 3.14 and Pillow 13.

### Known limitations

- **No native Wayland surface:** on Wayland the wheel runs through XWayland; a native
  layer-shell surface is planned.
- **Hotkey:** only GNOME and Xfce are set up automatically.
- **fish completions** are generated but not checked by the test suite where fish isn't
  installed.
- **LibreOffice** conversions run one at a time, a limitation of its profile.
- **AppImage:** x86_64 only for now. Qt needs `libxcb-cursor0` from the system.
- **.deb:** needs a release that packages PySide6 6.6+: Debian 13+, Ubuntu 25.04+, Kali
  Rolling. On older releases use pipx or the AppImage.

---

## [0.1.0] - 2026-10-20

### Added
- **Conversion engine:** PDF → PNG / JPG via `pdftoppm`, and PNG / JPG / WebP between
  each other via Pillow. Batch conversion, never overwrites, alpha flattened for JPG.
- **CLI:** `dotmorph convert`, `dotmorph formats`.
- **First radial-menu prototype** (PySide6 / QML): frameless, always on top, opens at the
  pointer, with drag and drop.

[2.0.3]: https://github.com/kareem2099/DotMorph/compare/v2.0.2...v2.0.3
[2.0.2]: https://github.com/kareem2099/DotMorph/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/kareem2099/DotMorph/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/kareem2099/DotMorph/compare/v0.1.0...v2.0.0
[0.1.0]: https://github.com/kareem2099/DotMorph/releases/tag/v0.1.0
