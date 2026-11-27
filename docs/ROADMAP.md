# DotMorph Roadmap

Legend: `[x]` done and tested, `[~]` written but not yet tried on a real desktop, `[ ]` todo.

**Focus:** Linux desktops, X11 and Wayland. On Wayland the wheel runs through XWayland and
the hotkey goes through GNOME / Xfce shortcuts; native Wayland (layer-shell) is under Later.
Developed on Kali, GNOME on Wayland.

## Phase 0: Foundation
- [x] Repo layout, `pyproject.toml`, Apache 2.0, CI
- [x] MVP formats: PDF→PNG/JPG, PNG↔JPG, WebP

## Phase 1: Radial menu prototype
- [x] Frameless transparent always-on-top window, opens at the pointer (centred on Wayland)
- [x] Drag to move the wheel (a drag is never a click)
- [x] Two-ring menu (categories + blooming fan), GPU sectors, hover lift/glow, staggered fly-out, implode on close
- [x] Drag & drop files onto the wheel
- [x] Demo GIF (`docs/screenshots/demo.gif`, rendered from the real QML)
- [x] Keyboard navigation (arrows, Enter, Backspace, 1-9, O)
- [x] Progress arc (elapsed seconds when unknown), click-to-cancel, success burst + check, failure shake

## Phase 2: Conversion engine
- [x] `pdftoppm` for PDF, Pillow for images
- [x] Batch conversion, never overwrites by default, alpha flattened for JPG
- [x] Tests for every backend (skipped when the tool is missing)
- [x] Options in the wheel: quality, PDF/SVG dpi, size, strip metadata (remembered)
- [x] Progress for large PDFs (and videos), cancel, parallel batches

## Phase 3: Ways to trigger it
- [x] Global hotkey: GNOME (Wayland + X11) and Xfce custom shortcuts, opens with copied files
- [x] Edge dock: snap the wheel to a screen edge as a tab, half wheel on hover/click/drag-over, slide, undock, remembered
- [~] File-manager actions: Thunar, Nautilus, Dolphin, Nemo + Open With (`dotmorph integrate`)
- [x] Daemon for instant open (`dotmorph daemon --install`)
- [~] Watch folders (inotify) + systemd user service
- [x] CLI: `convert` (presets, dry run, progress, parallel), `formats` (`--missing`), `doctor`, shell completions

## Phase 4: Polish
- [~] Settings window: general, wheel (pin / hide formats), shortcut recorder, integrations, watch folders, tools, about
- [~] Themes: dark, light, glass (`--theme`), `--reduce-motion`
- [~] EN / AR translations with right-to-left layout and Arabic font
- [~] Desktop notifications with "open folder" (selects the files)
- [~] Icon and branding in line with DotSuite (emerald accent, neon icon, PNG sizes, banner)

## Phase 5: Distribution
- [x] PyPI (`pipx install 'dotmorph[gui]'`), published with attestations in 2.0.0
- [x] `.deb` (built, contents checked, runs; installs with apt dependencies)
- [x] AppImage (built and smoke-tested in the release workflow)
- [~] AUR (`PKGBUILD` and an Arch package ship with every release; the AUR push waits for an AUR account key)
- [x] Release automation on tag: GitHub Release, PyPI trusted publishing, AUR push (docs/RELEASING.md)
- [x] AppStream metainfo, man page, packaged completions and icons
- Flatpak: not planned. The sandbox blocks the host converters and the desktop integration DotMorph is built on.

## Phase 6: Website and launch
- [x] Product page on [dotsuite.dev](https://dotsuite.dev/en/product/dotmorph) (instead of a separate landing page)
- [x] Listed on AppImageHub, OpenDesktop and the AppImage catalog
- [~] Launch series on dev.to (part 1 published), Medium, social posts
- [ ] Share on r/linux, Show HN

## 2.2: voice and smarter conversions (details in [PLAN-2.x.md](PLAN-2.x.md))
2.1 and 2.2 shipped together as 2.2.0.
- [x] Sound effects (libcanberra, no new dependency)
- [x] Languages: Russian, German, Italian, French, Spanish, Portuguese (Brazil), Turkish, with plural rules
- [x] "Fit under X MB" size targets (Discord, WhatsApp, email)
- [x] OCR: image → text, scanned PDF → searchable PDF
- [x] Transcription: audio / video → text, SRT, VTT, copy to clipboard (whisper.cpp, offline) ([#4](https://github.com/kareem2099/DotMorph/issues/4))

## Next: 2.3
- [ ] **2.3** Custom actions (TOML plugins, user-defined sectors)
- [ ] **2.3** Native Wayland on KDE / wlroots (layer-shell, portal global shortcuts)

## Done in 2.0
- [x] More formats: HEIC, AVIF, SVG, GIF, PSD, XCF, resize (2.0 engine)
- [x] Compress / strip metadata (pairs with DotScramble)
- [x] Audio / video through ffmpeg
- [x] Office (LibreOffice) and Markdown / EPUB (pandoc)
- [x] `dotmorph doctor`
