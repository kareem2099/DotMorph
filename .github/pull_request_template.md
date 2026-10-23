## What and why

<!-- What does this change, and what problem does it solve? Link the issue: "Fixes #123". -->

## How it was tested

<!-- Commands you ran, files you converted, desktop / display server you tried it on. -->

## Checklist

- [ ] `pytest -q` passes (GUI tests run with `QT_QPA_PLATFORM=offscreen`)
- [ ] `ruff check .` is clean
- [ ] `python packaging/build.py check` passes (run `python packaging/build.py assets` if
      commands, options, formats or the version changed)
- [ ] New user-facing text is in `src/dotmorph/i18n.py` with an Arabic translation
- [ ] `CHANGELOG.md` has an entry under the next version
- [ ] Screenshots or a short clip for visual changes to the wheel or the settings window
