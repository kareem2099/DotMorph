"""Command line interface: `dotmorph convert report.pdf --to png`, `formats`, `doctor`."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import threading
from pathlib import Path

from . import __version__
from .core import registry
from .core.converter import BatchResult, Options, convert_many, default_jobs, plan
from .core.formats import CATEGORIES, FIT_TOOLS, FORMATS, TOOLS, normalize_ext
from .core.presets import PRESETS
from .core.system import distro_name, package_manager


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dotmorph",
        description="DotMorph: radial-menu file converter. "
        "Run `dotmorph [FILES...]` with no subcommand to open the radial menu.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"dotmorph {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    conv = sub.add_parser("convert", help="convert files from the terminal")
    conv.add_argument("files", nargs="+", type=Path)
    conv.add_argument(
        "--to", metavar="TARGET",
        help="format (png, mp4, pdf, ...) or tool: " + ", ".join(TOOLS),
    )
    conv.add_argument(
        "--preset", choices=sorted(PRESETS),
        help="; ".join(f"{name}: {p.help}" for name, p in PRESETS.items()),
    )
    conv.add_argument("-o", "--out", type=Path, help="output directory (default: next to source)")
    conv.add_argument(
        "--dpi", type=int, help="render resolution (default: PDF 150, SVG 96 = original size)"
    )
    conv.add_argument("--quality", type=int, help="JPEG/WebP/AVIF quality (default 90)")
    conv.add_argument(
        "--resize", metavar="SPEC", help="50%%, 1920x1080 (fit inside) or 1280 (width)"
    )
    conv.add_argument("--strip", action="store_true", help="drop EXIF / tags while converting")
    conv.add_argument("--overwrite", action="store_true", help="replace existing files")
    conv.add_argument("-j", "--jobs", type=int, default=0,
                      help="files converted in parallel (default: CPU cores, up to 8)")
    conv.add_argument("--timeout", type=float, help="give up on one file after N seconds")
    conv.add_argument("--fit", metavar="SIZE",
                      help="make each file at most SIZE (8M, 10MB, 500K): video, audio, images, "
                           "PDF; --to is then optional")
    conv.add_argument("--lang", metavar="CODE",
                      help="language for transcription and OCR (en, ar, de, ar+en for OCR; "
                           "default: detect / English plus the interface language)")
    conv.add_argument("-q", "--quiet", action="store_true", help="no progress bar")
    conv.add_argument("--notify", action="store_true",
                      help="desktop notification when done (with an Open folder button)")
    conv.add_argument("-n", "--dry-run", action="store_true",
                      help="show what would be converted, and how, without doing it")

    wh = sub.add_parser("whisper", help="speech models for transcription (audio/video -> text)")
    wh.add_argument("--download", metavar="MODEL", nargs="?", const="base",
                    help="download a model: tiny, base (default), small, medium, large-v3-turbo")
    wh.add_argument("--list", action="store_true", help="models available and installed")

    fmts = sub.add_parser("formats", help="list supported conversions")
    fmts.add_argument("files", nargs="*", type=Path, help="show targets for these files only")
    fmts.add_argument("--missing", action="store_true",
                      help="what installing the missing tools would add")

    sub.add_parser("settings", help="open the settings window")

    comp = sub.add_parser("completions", help="shell completion script (bash, zsh, fish)")
    comp.add_argument("shell", choices=("bash", "zsh", "fish"))
    comp.add_argument("--install", action="store_true",
                      help="write it where your shell picks it up (per user)")

    sub.add_parser("doctor", help="check which tools are installed and what they unlock")

    dmn = sub.add_parser("daemon", help="keep the wheel loaded so it opens instantly")
    group = dmn.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true", help="start now and at every login")
    group.add_argument("--uninstall", action="store_true", help="stop and remove from login")
    group.add_argument("--stop", action="store_true", help="stop the running daemon")
    group.add_argument("--status", action="store_true", help="is it running?")
    dmn.add_argument("--theme", choices=("dark", "light", "glass"),
                     help="override the theme from the settings")

    integ = sub.add_parser("integrate",
                           help="add DotMorph to file-manager right-click menus and Open With")
    integ.add_argument("--remove", action="store_true", help="take everything out again")

    hk = sub.add_parser("hotkey", help="global shortcut: open the wheel with the copied files")
    hk.add_argument("--key", help="e.g. '<Super><Shift>m' (the default) or '<Control><Alt>c'")
    hk.add_argument("--force", action="store_true", help="even if the key is already taken")
    hk.add_argument("--remove", action="store_true", help="remove the shortcut")

    wt = sub.add_parser("watch", help="convert new files in folders automatically")
    wt.add_argument("dirs", nargs="*", type=Path)
    wt.add_argument("--to", metavar="TARGET", help="format or tool for new files")
    wt.add_argument("--from", dest="sources", metavar="EXTS",
                    help="only these source formats, comma separated (default: all that fit)")
    wt.add_argument("-o", "--out", type=Path, help="output directory (default: same folder)")
    wt.add_argument("--quality", type=int, default=90)
    wt.add_argument("--resize", metavar="SPEC")
    wt.add_argument("--strip", action="store_true")
    wt.add_argument("-r", "--recursive", action="store_true", help="watch sub-folders too")
    wt.add_argument("--notify", action="store_true", help="notification for each file")
    wt.add_argument("--install", action="store_true", help="run as a systemd user service")
    wt.add_argument("--list", action="store_true", help="list installed watch services")
    wt.add_argument("--uninstall", metavar="NAME", help="remove an installed watch service")
    return parser


# ---- convert --------------------------------------------------------------------------


class _Progress:
    """One self-updating line on stderr: `  42%  [3/10]  ████████░░░░░░`."""

    def __init__(self, total: int, enabled: bool) -> None:
        self.total = total
        self.enabled = enabled
        self.done = 0
        self.fraction = 0.0
        self.lock = threading.Lock()

    def files(self, done: int, total: int) -> None:
        self.done = done
        self.draw()

    def smooth(self, fraction: float) -> None:
        self.fraction = fraction
        self.draw()

    def draw(self) -> None:
        if not self.enabled:
            return
        with self.lock:
            width = 24
            filled = int(width * self.fraction)
            bar = "█" * filled + "░" * (width - filled)
            sys.stderr.write(
                f"\r  {self.fraction * 100:3.0f}%  [{self.done}/{self.total}]  {bar} "
            )
            sys.stderr.flush()

    def close(self) -> None:
        if self.enabled:
            sys.stderr.write("\r" + " " * 50 + "\r")
            sys.stderr.flush()


def parse_size(spec: str) -> int:
    """'8M', '10MB', '500k', '2.5m', '1200000' -> bytes (decimal units, like the presets)."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kmg]?)b?\s*", spec.lower())
    if not m:
        raise ValueError(f"not a size: {spec!r} (try 8M or 500K)")
    size = int(float(m.group(1)) * {"": 1, "k": 10**3, "m": 10**6, "g": 10**9}[m.group(2)])
    if size <= 0:
        raise ValueError(f"the size must be more than 0: {spec!r}")
    return size


def _convert(args: argparse.Namespace) -> int:
    preset = PRESETS[args.preset] if args.preset else None
    fit_bytes = None
    if args.fit:
        try:
            fit_bytes = parse_size(args.fit)
        except ValueError as exc:
            print(f"dotmorph convert: {exc}", file=sys.stderr)
            return 2
    to = args.to or (preset.to if preset else None) or ("fit-25mb" if fit_bytes else None)
    if not to:
        print("dotmorph convert: --to is required (or a --preset that sets it)", file=sys.stderr)
        return 2
    if fit_bytes and to not in FIT_TOOLS:
        print(f"dotmorph convert: --fit works with the size tools, not --to {to} "
              "(drop --to, or use --to fit-10mb / fit-16mb / fit-25mb)", file=sys.stderr)
        return 2
    dpi = args.dpi or (preset.dpi if preset else None)
    quality = args.quality or (preset.quality if preset else None) or 90
    opts = Options(
        out_dir=args.out,
        dpi=max(1, dpi) if dpi else None,
        quality=min(100, max(1, quality)),
        overwrite=args.overwrite,
        resize=args.resize or (preset.resize if preset else None),
        strip=args.strip or bool(preset and preset.strip),
        timeout=args.timeout,
        language=args.lang,
        fit_bytes=fit_bytes,
    )
    target = normalize_ext(to)
    if args.dry_run:
        return _dry_run(args.files, target, opts)
    progress = _Progress(len(args.files), enabled=not args.quiet and sys.stderr.isatty())
    cancel = threading.Event()
    holder: list[BatchResult] = []

    def work() -> None:
        holder.append(
            convert_many(
                args.files, target, opts, progress.files,
                jobs=args.jobs or default_jobs(), cancel=cancel, on_fraction=progress.smooth,
            )
        )

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    try:
        while worker.is_alive():
            worker.join(0.2)
    except KeyboardInterrupt:
        cancel.set()
        worker.join()
    progress.close()

    result = holder[0] if holder else BatchResult(cancelled=True)
    for path in result.outputs:
        print(f"ok    {path}")
    for path, message in result.errors:
        print(f"FAIL  {path}: {message}")
    if args.notify:
        from .linux.notify import notify

        notify(result.outputs, [f"{p.name}: {m}" for p, m in result.errors])
    if result.cancelled:
        print("cancelled", file=sys.stderr)
        return 130
    return 0 if result.ok else 1


def _dry_run(files: list[Path], target: str, opts: Options) -> int:
    ok = True
    for step in plan(files, target, opts):
        if step.error:
            ok = False
            print(f"skip   {step.src}: {step.error}")
        else:
            print(f"would  {step.src} -> {step.output}  [{step.backend}]")
    extras = [f"quality {opts.quality}"]
    if opts.resize:
        extras.append(f"resize {opts.resize}")
    if opts.dpi:
        extras.append(f"{opts.dpi} dpi")
    if opts.strip:
        extras.append("strip metadata")
    print(f"(dry run: nothing written; {', '.join(extras)})")
    return 0 if ok else 1


# ---- formats --------------------------------------------------------------------------


def _formats(args: argparse.Namespace) -> int:
    if args.missing:
        return _formats_missing()
    matrix = registry.matrix()
    if args.files:
        from .core.formats import common_targets

        targets = common_targets(args.files)
        print(", ".join(targets) if targets else "no conversion available for these files")
        return 0 if targets else 1

    for category in CATEGORIES[:-1]:
        rows = [(src, acts) for src, acts in matrix.items() if FORMATS.get(src) == category]
        if not rows:
            continue
        print(category.upper())
        for src, actions in rows:
            formats = [a for a in actions if a not in TOOLS]
            tools = [a for a in actions if a in TOOLS]
            line = ", ".join(formats)
            if tools:
                line += f"   [{', '.join(tools)}]"
            print(f"  {src:>5} -> {line}")
        print()
    print("TOOLS")
    for tool_id, tool in TOOLS.items():
        extra = " (several files -> one)" if tool.batch else ""
        print(f"  {tool_id:<10} {tool.label}{extra}")

    now, every = registry.potential_count()
    print(f"\n{now} conversions available.", end="")
    if every > now:
        print(f" {every - now} more need missing tools: run `dotmorph doctor`.")
    else:
        print()
    return 0


def _formats_missing() -> int:
    current = {src: set(acts) for src, acts in registry.matrix().items()}
    found = False
    for backend in registry.backends():
        if backend.available():
            continue
        extra = {
            src: sorted(acts - current.get(src, set()))
            for src, acts in backend.potential_pairs().items()
            if acts - current.get(src, set())
        }
        if not extra:
            continue
        found = True
        missing = [r for r in backend.requirements if not r.present()]
        print(f"{backend.name}  ({', '.join(r.name for r in missing)} missing)")
        for src, acts in sorted(extra.items()):
            print(f"  {src:>5} -> {', '.join(acts)}")
        if missing:
            print(f"  install: {missing[0].install}")
        print()
    if not found:
        print("Nothing is missing: every conversion DotMorph knows is available here.")
    return 0


# ---- doctor ---------------------------------------------------------------------------

OK, NO = "✔", "✘"


def _doctor() -> int:
    print(f"DotMorph {__version__} on {distro_name()} ({package_manager()})\n")
    missing_cmds: list[str] = []
    for backend in registry.backends():
        ready = backend.available() and bool(backend.pairs())
        mark = OK if ready else NO
        print(f"  {mark} {backend.name:<12} {backend.description}")
        for req in backend.requirements:
            if not req.present():
                print(f"      {NO} {req.name:<10} missing -> {req.install}")
                missing_cmds.append(req.install)
        for req in backend.extras:
            state = OK if req.present() else NO
            hint = "" if req.present() else f" -> {req.install}"
            print(f"      {state} {req.name:<10} optional: {req.purpose}{hint}")

    _doctor_desktop()
    now, every = registry.potential_count()
    print(f"\n{now} of {every} conversions available.")
    if missing_cmds:
        print("Install everything missing:")
        for cmd in dict.fromkeys(missing_cmds):
            print(f"  {cmd}")
    return 0


# ---- Linux integration ----------------------------------------------------------------


def _daemon(args: argparse.Namespace) -> int:
    from .linux import daemon, ipc

    if args.status:
        info = ipc.daemon_running()
        print(f"running (pid {info['pid']})" if info else "not running")
        print(f"autostart: {'on' if daemon.autostart_file().exists() else 'off'}")
        return 0 if info else 1
    if args.stop or args.uninstall:
        stopped = bool(ipc.request({"cmd": "quit"}))
        removed = daemon.remove_autostart() if args.uninstall else False
        print("stopped" if stopped else "was not running")
        if removed:
            print(f"removed {daemon.autostart_file()}")
        return 0
    if args.install:
        print(f"autostart: {daemon.install_autostart()}")
        if not ipc.daemon_running():
            daemon.start_detached()
            print("daemon started")
        return 0
    return daemon.serve(theme=args.theme)


def _integrate(args: argparse.Namespace) -> int:
    from .linux import integrate

    if args.remove:
        removed = integrate.remove()
        for path in removed:
            print(f"removed  {path}")
        print("nothing to remove" if not removed else "done")
        return 0
    for path in integrate.install():
        print(f"wrote    {path}")
    quick = ", ".join(q.label for q in integrate.available_quick())
    print(f"\nRight-click files -> DotMorph ({quick}), or Open With -> DotMorph.")
    print("Nautilus: Scripts -> DotMorph. Thunar: restart it once (thunar -q).")
    return 0


def _hotkey(args: argparse.Namespace) -> int:
    from .linux import hotkey

    try:
        if args.remove:
            print("shortcut removed" if hotkey.remove() else "no DotMorph shortcut found")
            return 0
        result = hotkey.install(args.key, args.force)
    except hotkey.HotkeyError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(result.message)
    print("Copy files in your file manager (Ctrl+C), press the shortcut, pick a format.")
    print("Tip: `dotmorph daemon --install` makes it open instantly.")
    return 0


def _watch(args: argparse.Namespace) -> int:
    from .core.common import ConversionError
    from .linux import watch

    if args.list:
        services = watch.installed_services()
        for path in services:
            print(f"{path.stem:<28} {watch.describe(path)}")
        if not services:
            print("no watch services installed")
        return 0
    if args.uninstall:
        ok = watch.remove_service(args.uninstall)
        print("removed" if ok else f"no service named {args.uninstall}")
        return 0 if ok else 1
    if not args.dirs or not args.to:
        print("usage: dotmorph watch DIR [DIR...] --to TARGET", file=sys.stderr)
        return 2

    opts = Options(out_dir=args.out, quality=min(100, max(1, args.quality)),
                   resize=args.resize, strip=args.strip)
    sources = {s for s in (args.sources or "").split(",") if s.strip()}
    try:
        watcher = watch.Watcher(args.dirs, args.to, sources, opts, recursive=args.recursive,
                                notify=args.notify,
                                log=lambda line: print(line, flush=True))
    except ConversionError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.install:
        dirs = [str(Path(d).expanduser().resolve()) for d in args.dirs]
        rest = ["--to", args.to]
        if args.sources:
            rest += ["--from", args.sources]
        if args.out:
            rest += ["-o", str(args.out.expanduser().resolve())]
        if args.quality != 90:
            rest += ["--quality", str(args.quality)]
        if args.resize:
            rest += ["--resize", args.resize]
        rest += [flag for flag, on in (("--strip", args.strip), ("-r", args.recursive),
                                       ("--notify", args.notify)) if on]
        unit = watch.install_service([*dirs, *rest], args.dirs, normalize_ext(args.to))
        print(f"installed and started {unit.name}")
        print(f"logs: journalctl --user -u {unit.name} -f")
        return 0
    try:
        watcher.run()
    except KeyboardInterrupt:
        pass
    except (OSError, ConversionError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def _doctor_desktop() -> None:
    from .linux import daemon, hotkey, integrate, ipc, watch

    print("\n  Desktop integration")
    running = ipc.daemon_running()
    autostart = daemon.autostart_file().exists()
    print(f"    {OK if running else NO} daemon      "
          f"{'running' if running else 'not running'}, autostart {'on' if autostart else 'off'}"
          f"{'' if running else '  -> dotmorph daemon --install'}")
    menus = integrate.manifest_path().exists()
    print(f"    {OK if menus else NO} file menus  "
          f"{'installed' if menus else 'not installed  -> dotmorph integrate'}")
    key = hotkey.installed()
    print(f"    {OK if key else NO} hotkey      "
          + (f"{key} ({hotkey.desktop()})" if key else
             f"not set ({hotkey.desktop()})  -> dotmorph hotkey"))
    import os
    import shutil

    if os.environ.get("WAYLAND_DISPLAY") and not shutil.which("wl-paste"):
        print(f"    {NO} wl-paste    optional: reads copied files on Wayland  -> "
              "sudo apt install wl-clipboard")
    services = watch.installed_services()
    print(f"    {OK if services else '-'} watch       {len(services)} service(s)")


def _completions(args: argparse.Namespace) -> int:
    from . import completions

    if args.install:
        path, note = completions.install(args.shell, _parser())
        print(f"wrote {path}")
        if note:
            print(note)
        return 0
    sys.stdout.write(completions.generate(args.shell, _parser()))
    return 0


def _whisper(args: argparse.Namespace) -> int:
    from .core import registry
    from .core.backends import whisper

    installed = whisper.installed_models()
    if args.download:
        name = args.download
        if name not in whisper.MODELS:
            print(f"unknown model {name!r}; choose from {', '.join(whisper.MODELS)}",
                  file=sys.stderr)
            return 2
        print(f"downloading the {name} model (~{whisper.MODELS[name]} MB) "
              f"to {whisper.models_dir()}")

        def show(done: int, total: int) -> None:
            if total and sys.stderr.isatty():
                sys.stderr.write(f"\r  {done * 100 // total:3d}%  {done >> 20} / {total >> 20} MB")
                sys.stderr.flush()

        try:
            path = whisper.download(name, show)
        except (OSError, ValueError) as exc:
            print(f"\ndownload failed: {exc}", file=sys.stderr)
            return 1
        print(f"\nsaved {path}")
        registry.refresh()
        if not shutil.which("whisper-cli"):
            print(f"now install whisper-cli: {whisper.WHISPER.install}")
        return 0
    print("Whisper models (multilingual):")
    for name, size in whisper.MODELS.items():
        mark = f"installed: {installed[name]}" if name in installed else ""
        default = " (default)" if name == whisper.DEFAULT_MODEL else ""
        print(f"  {name:<15} {size:>5} MB{default:<10} {mark}")
    cli = shutil.which("whisper-cli") or f"missing -> {whisper.WHISPER.install}"
    print(f"\nwhisper-cli: {cli}")
    if not installed:
        print("no model yet -> dotmorph whisper --download")
    return 0


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    if args.cmd == "completions":
        return _completions(args)
    if args.cmd == "settings":
        from .ui.settings_window import run

        return run()
    if args.cmd == "formats":
        return _formats(args)
    if args.cmd == "doctor":
        return _doctor()
    if args.cmd == "daemon":
        return _daemon(args)
    if args.cmd == "integrate":
        return _integrate(args)
    if args.cmd == "hotkey":
        return _hotkey(args)
    if args.cmd == "watch":
        return _watch(args)
    if args.cmd == "whisper":
        return _whisper(args)
    return _convert(args)

