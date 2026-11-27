# Contributing to DotMorph

Thanks for helping. Bug reports, new formats, translations, packaging fixes and docs are all
welcome. DotMorph is part of [DotSuite](https://dotsuite.dev/en).

- **Questions and ideas:** [Discussions](https://github.com/kareem2099/DotMorph/discussions)
- **Bugs and feature requests:** [Issues](https://github.com/kareem2099/DotMorph/issues/new/choose).
  Please include `dotmorph doctor` output.
- **Security problems:** privately, see [SECURITY.md](SECURITY.md).

## Set up

```bash
git clone https://github.com/kareem2099/DotMorph && cd DotMorph
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[gui]' --group dev   # pip 25.1+
dotmorph doctor                 # which engines you have
```

Install the conversion tools you want to work on (`ffmpeg`, `poppler-utils`, `ghostscript`,
`imagemagick`, `pandoc`, `libreoffice`). Tests for tools that aren't installed are skipped.

## Before you open a pull request

```bash
pytest -q                       # GUI tests run offscreen by themselves
ruff check .
python packaging/build.py check # versions agree, generated assets are current
```

If you changed commands, options, formats or the version, regenerate the packaging assets
(desktop files, man page, completions, AppStream metainfo) and commit the result:

```bash
python packaging/build.py assets
```

Tests never touch your real settings: they point the XDG folders at a temporary directory and
fake `gsettings`. Please keep it that way in new tests.

## Where things live

| You want to… | Look at |
|--------------|---------|
| add a format an existing tool can already do | the backend in `src/dotmorph/core/backends/` (its `potential_pairs`) |
| add a whole new tool (engine) | a new `Backend` subclass, registered in `core/backends/__init__.py` |
| add a format to the catalog or change menu order | `src/dotmorph/core/formats.py` |
| add a keep-the-format tool (like `compress`) | `TOOLS` in `formats.py`, then each backend that can do it |
| change the wheel | `src/dotmorph/ui/qml/` (`Wheel.qml`, `RingSector.qml`, `Hub.qml`) |
| change the settings window | `ui/qml/SettingsWindow.qml` + `ui/settings_window.py` |
| change desktop integration | `src/dotmorph/linux/` |
| package or release | `packaging/build.py`, `.github/workflows/release.yml`, `docs/RELEASING.md` |

### Adding a backend, in short

1. Subclass `registry.Backend`:
   - set `name`, `description`, and `requirements` (the tools it needs, with package names
     per distro)
   - implement `potential_pairs()` (everything it could convert) and `run(job)`
2. Write into the scratch folder from `common.workdir()`, then hand the finished file to
   `common.finalize()`. That way half-written files never appear and names never clash.
3. Run external tools through `common.run_tool()`, so cancel, timeouts and progress work.
4. Add a test in `tests/test_backends.py`, guarded with `@needs("the-tool")`.

## Translations

Each language is one JSON file in `src/dotmorph/locales/` (`de.json`, `ru.json`, …). The
English string is the key and the value is the translation. Keep `%1` and `%2` placeholders
(a test checks this).

Text with a count in it has plural forms instead of one string, picked by the language's
[CLDR plural rules](https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html):

```json
"%1 files": {"one": "%1 Datei", "other": "%1 Dateien"}
```

Russian uses `one` / `few` / `many` / `other`, Arabic `zero` / `one` / `two` / `few` / `many`
/ `other`, French and Portuguese count 0 as `one`. The rules are in `i18n.plural_category()`.

To fix a translation, edit the JSON. To add a language:
1. Copy `de.json` to `<code>.json` and translate every value.
2. Add the language to `NATIVE_NAMES` in `i18n.py` (its name in its own language) and, if
   needed, its plural rule to `plural_category()`.
3. If it is written right to left, add it to `RTL_LANGUAGES`.
4. Run `pytest tests/test_locales.py tests/test_settings_ui.py`. They check that nothing is
   missing, that placeholders and plural forms are right, and that every wheel label fits
   its sector (long words shrink, but not below 9 px: pick a shorter word if one fails).

Commands, format names and engine error messages stay English.

## Style

- Python 3.10+. Match the surrounding code; `ruff` settings are in `pyproject.toml`
  (line length 100).
- No Qt imports at module level outside `ui/`, so the CLI stays fast and works without
  PySide6.
- Keep commits focused, and describe *why* in the message.
- Add a line to `CHANGELOG.md` for anything a user would notice.

By contributing you agree that your work is released under the
[Apache 2.0 license](LICENSE), and that you follow the [Code of Conduct](CODE_OF_CONDUCT.md).
