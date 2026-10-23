from pathlib import Path

import pytest

from dotmorph.core.common import ConversionError, parse_resize, resized_size
from dotmorph.core.formats import (
    category_of,
    common_targets,
    is_batch,
    label_of,
    normalize_ext,
    sort_actions,
    targets_for,
)
from dotmorph.core.system import _parse_os_release, install_command, package_manager


def test_normalize_ext():
    assert normalize_ext(".JPEG") == "jpg"
    assert normalize_ext("png") == "png"
    assert normalize_ext("TIF") == "tiff"
    assert normalize_ext(".markdown") == "md"


def test_targets_for_images():
    assert targets_for(Path("a.png"))[:2] == ["jpg", "webp"]
    assert targets_for(Path("a.jpeg"))[:2] == ["png", "webp"]
    assert "png" not in targets_for(Path("a.png"))
    assert targets_for(Path("a.xyz")) == []


def test_common_targets():
    both = common_targets([Path("a.png"), Path("b.jpg")])
    assert both[0] == "webp" and "png" not in both and "jpg" not in both
    assert "merge-pdf" in both  # batch tool shows up for several files ...
    assert "merge-pdf" not in common_targets([Path("a.png")])  # ... but not for one
    assert common_targets([Path("a.png"), Path("b.xyz")]) == []
    assert common_targets([]) == []


def test_sort_puts_same_category_first_then_tools():
    order = sort_actions({"mp3", "compress", "mkv", "gif", "webm"}, "mp4")
    assert order == ["mkv", "webm", "gif", "mp3", "compress"]
    assert sort_actions({"txt", "png", "jpg"}, "pdf") == ["png", "jpg", "txt"]


def test_labels_and_categories():
    assert label_of("webp") == "WEBP" and label_of("resize-50") == "50%"
    assert category_of("mp3") == "audio" and category_of("compress") == "tools"
    assert is_batch("merge-pdf") and not is_batch("png")


def test_parse_resize():
    assert parse_resize("50%") == ("pct", 50.0, 0, 0)
    assert parse_resize("1920x1080") == ("box", 0.0, 1920, 1080)
    assert parse_resize("1280") == ("w", 0.0, 1280, 0)
    assert resized_size("50%", 200, 100) == (100, 50)
    assert resized_size("100x100", 400, 200) == (100, 50)
    assert resized_size("50", 200, 100) == (50, 25)
    with pytest.raises(ConversionError):
        parse_resize("big")


def test_package_manager_detection():
    assert package_manager(_parse_os_release('ID=kali\nID_LIKE=debian')) == "apt"
    assert package_manager(_parse_os_release('ID="endeavouros"\nID_LIKE=arch')) == "pacman"
    assert package_manager(_parse_os_release("ID=fedora")) == "dnf"
    assert package_manager(_parse_os_release('ID="opensuse-tumbleweed"')) == "zypper"
    pkgs = {"apt": "poppler-utils", "pacman": "poppler"}
    assert install_command(pkgs, "pacman") == "sudo pacman -S poppler"
    assert install_command(pkgs, "dnf") == "sudo dnf install poppler-utils"
    assert install_command({"pip": "pillow-heif"}) == "pip install pillow-heif"
