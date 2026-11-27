"""User-interface text in every language DotMorph speaks.

Source strings are English and double as keys. Each language is one JSON file in
`locales/` (`ar.json`, `de.json`, ...): a key maps to its translation, or, for text with a
count in it, to its CLDR plural forms ({"one": ..., "few": ..., "other": ...}) picked by
`trn()`. Anything missing falls back to English. Format names (PNG, MP4, ...), commands and
engine error messages stay English on purpose.
"""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path

LOCALES = Path(__file__).parent / "locales"
# What the language picker shows: each language in its own name, in this order.
NATIVE_NAMES = {
    "en": "English",
    "ar": "العربية",
    "de": "Deutsch",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
    "pt-BR": "Português (Brasil)",
    "ru": "Русский",
    "tr": "Türkçe",
}
LANGUAGES = tuple(NATIVE_NAMES)
RTL_LANGUAGES = {"ar"}
PLURAL_FORMS = ("zero", "one", "two", "few", "many", "other")

_current: str | None = None


@cache
def catalog(lang: str) -> dict[str, str | dict[str, str]]:
    path = LOCALES / f"{lang}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def plural_category(lang: str, n: int) -> str:
    """CLDR plural category of a whole number (all DotMorph ever counts is files)."""
    n = abs(int(n))
    base = lang.split("-")[0]
    if base == "ar":
        if n in (0, 1, 2):
            return ("zero", "one", "two")[n]
        if 3 <= n % 100 <= 10:
            return "few"
        if 11 <= n % 100 <= 99:
            return "many"
        return "other"
    if base == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    if base in ("fr", "pt"):
        if n in (0, 1):
            return "one"
        return "many" if n % 1_000_000 == 0 else "other"
    if base in ("it", "es") and n and n % 1_000_000 == 0:
        return "many"
    return "one" if n == 1 else "other"  # en, de, it, es, tr


def match(value: str) -> str | None:
    """A locale name ("de_DE.UTF-8", "pt_BR", "pt", "ar") -> one of LANGUAGES, or None."""
    tag = value.split(".")[0].split("@")[0].replace("_", "-")
    if not tag:
        return None
    for lang in LANGUAGES:
        if lang.lower() == tag.lower():
            return lang
    base = tag.split("-")[0].lower()
    return next((lang for lang in LANGUAGES if lang.split("-")[0] == base), None)


def system_language() -> str:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            # LANGUAGE may be a list ("de:en"): the first language we have wins
            for part in value.split(":") if var == "LANGUAGE" else [value]:
                if found := match(part):
                    return found
            return "en"
    return "en"


def resolve(setting: str | None) -> str:
    """'auto' or a language code -> a language DotMorph has."""
    if setting in LANGUAGES:
        return setting
    return system_language()


def current() -> str:
    global _current
    if _current is None:
        from .settings import load

        _current = resolve(load().language)
    return _current


def set_language(setting: str | None) -> str:
    global _current
    _current = resolve(setting)
    return _current


def _fill(text: str, args: tuple[object, ...]) -> str:
    for i, value in enumerate(args, start=1):
        text = text.replace(f"%{i}", str(value))
    return text


def _pick(value: str | dict[str, str] | None, lang: str, n: int) -> str | None:
    if isinstance(value, dict):
        return value.get(plural_category(lang, n)) or value.get("other")
    return value


def tr(text: str, *args: object) -> str:
    """Translate, then fill %1, %2, ... like Qt's arg()."""
    value = catalog(current()).get(text)
    return _fill(value if isinstance(value, str) else text, args)


def trn(text: str, n: int, *args: object) -> str:
    """Translate text with a count in it: %1 is `n`, chosen by the language's plural rules."""
    lang = current()
    out = _pick(catalog(lang).get(text), lang, n) or _pick(catalog("en").get(text), "en", n)
    return _fill(out or text, (n, *args))


def is_rtl(lang: str | None = None) -> bool:
    return (lang or current()) in RTL_LANGUAGES
