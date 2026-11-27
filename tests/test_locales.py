"""Every language: complete, placeholders intact, plural forms right, nothing malformed."""

import json
import re
from pathlib import Path

import pytest

from dotmorph import i18n
from dotmorph.core.formats import TOOLS

SRC = Path(i18n.__file__).parent
CALL = re.compile(r'''\b(t|tr|trn|tn)\(\s*"((?:[^"\\]|\\.)*)"''')
LAUNCHER = re.compile(r'''\blocalized\(\s*"\w+",\s*"([^"]*)"''')  # .desktop / metainfo text
TRANSLATED = [lang for lang in i18n.LANGUAGES if lang != "en"]


def used_strings() -> tuple[set[str], set[str]]:
    """(plain, counted) English strings the code passes to tr() / t() / trn() / tn()."""
    plain, counted = set(), set()
    for path in [*SRC.rglob("*.py"), *SRC.rglob("*.qml")]:
        for kind, text in CALL.findall(path.read_text(encoding="utf-8")):
            text = text.encode().decode("unicode_escape").encode("latin-1").decode("utf-8") \
                if "\\" in text else text
            (counted if kind in ("trn", "tn") else plain).add(text)
        plain.update(LAUNCHER.findall(path.read_text(encoding="utf-8")))
    plain |= {tool.label for tool in TOOLS.values()}
    plain.add("Convert any file from a radial menu")  # the metainfo summary (build.py)
    plain.discard("Text")  # the example in Theme.qml's comment
    return plain, counted


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"%\d(?!\d)", text))  # Turkish writes 50% as "%50"


def test_catalog_files_are_the_languages():
    files = {p.stem for p in (SRC / "locales").glob("*.json")}
    assert files == set(i18n.LANGUAGES)
    for lang in i18n.LANGUAGES:
        json.loads((SRC / "locales" / f"{lang}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("lang", TRANSLATED)
def test_every_string_is_translated(lang):
    plain, counted = used_strings()
    cat = i18n.catalog(lang)
    missing = sorted(k for k in plain | counted if k not in cat)
    assert not missing, f"{lang} lacks {missing}"
    assert all(isinstance(cat[k], dict) for k in counted), f"{lang}: counted text needs forms"
    assert all(isinstance(cat[k], str) for k in plain - counted), f"{lang}: plain text as forms"


def test_english_has_singulars_for_counted_text():
    _, counted = used_strings()
    en = i18n.catalog("en")
    assert counted <= set(en)
    assert all(set(en[k]) == {"one", "other"} for k in counted)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_placeholders_and_plural_forms(lang):
    needed = {i18n.plural_category(lang, n) for n in range(0, 2001)} | {"other"}
    for key, value in i18n.catalog(lang).items():
        if isinstance(value, dict):
            assert set(value) <= set(i18n.PLURAL_FORMS), (lang, key)
            assert "other" in value, (lang, key)
            # forms other than "one"/"two"/"zero" stand for many numbers: they must show it
            for form, text in value.items():
                assert placeholders(text) <= placeholders(key), (lang, key, form)
                if form in ("few", "many", "other"):
                    assert "%1" in text, (lang, key, form)
            if lang != "ar":  # Arabic leaves out forms that equal "other"
                assert needed <= set(value), (lang, key, needed - set(value))
        else:
            assert placeholders(value) == placeholders(key), (lang, key)
            assert value.strip() == value or key.strip() != key, (lang, key)


@pytest.mark.parametrize(("lang", "cases"), [
    ("en", {0: "other", 1: "one", 2: "other"}),
    ("ar", {0: "zero", 1: "one", 2: "two", 3: "few", 10: "few", 11: "many", 99: "many",
            100: "other", 102: "other", 103: "few", 111: "many"}),
    ("ru", {1: "one", 2: "few", 4: "few", 5: "many", 11: "many", 12: "many", 21: "one",
            22: "few", 25: "many", 111: "many", 101: "one"}),
    ("fr", {0: "one", 1: "one", 2: "other", 1_000_000: "many"}),
    ("pt-BR", {0: "one", 1: "one", 2: "other"}),
    ("de", {0: "other", 1: "one", 2: "other"}),
    ("tr", {1: "one", 2: "other"}),
])
def test_plural_rules(lang, cases):
    assert {n: i18n.plural_category(lang, n) for n in cases} == cases


def test_trn_picks_forms_and_falls_back(monkeypatch):
    i18n.set_language("en")
    assert i18n.trn("%1 files", 1) == "1 file"
    assert i18n.trn("%1 files", 5) == "5 files"
    assert i18n.trn("Converted %1 files, %2 failed", 1, 2) == "Converted 1 file, 2 failed"
    assert i18n.trn("Not a catalog key %1", 3) == "Not a catalog key 3"
    i18n.set_language("ar")
    assert i18n.trn("%1 files", 2) == "ملفان"
    assert i18n.trn("%1 files", 11) == "11 ملفًا"
    i18n.set_language("en")


@pytest.mark.parametrize(("env", "lang"), [
    ("de_DE.UTF-8", "de"), ("pt_BR.UTF-8", "pt-BR"), ("pt_PT.UTF-8", "pt-BR"),
    ("ru_RU", "ru"), ("tr_TR.UTF-8", "tr"), ("es_MX.UTF-8", "es"), ("ar_EG.UTF-8", "ar"),
    ("ja:fr", "fr"), ("ja_JP.UTF-8", "en"), ("C", "en"),
])
def test_system_language(monkeypatch, env, lang):
    monkeypatch.setenv("LANGUAGE", env)
    assert i18n.system_language() == lang
