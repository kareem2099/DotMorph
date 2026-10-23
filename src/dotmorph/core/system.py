"""Linux distro detection, used to print the right install command."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# package manager -> install command prefix
_INSTALL = {
    "apt": "sudo apt install",
    "dnf": "sudo dnf install",
    "pacman": "sudo pacman -S",
    "zypper": "sudo zypper install",
}

# os-release ID / ID_LIKE -> package manager
_FAMILY = {
    "debian": "apt",
    "ubuntu": "apt",
    "kali": "apt",
    "linuxmint": "apt",
    "pop": "apt",
    "fedora": "dnf",
    "rhel": "dnf",
    "centos": "dnf",
    "arch": "pacman",
    "manjaro": "pacman",
    "endeavouros": "pacman",
    "opensuse": "zypper",
    "suse": "zypper",
}


def _parse_os_release(text: str) -> dict[str, str]:
    data = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            data[key.strip()] = value.strip().strip('"')
    return data


@lru_cache(maxsize=1)
def os_release() -> dict[str, str]:
    for candidate in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            return _parse_os_release(Path(candidate).read_text())
        except OSError:
            continue
    return {}


def package_manager(info: dict[str, str] | None = None) -> str:
    info = os_release() if info is None else info
    ids = [info.get("ID", "")] + info.get("ID_LIKE", "").split()
    for ident in ids:
        for key, manager in _FAMILY.items():
            if ident == key or ident.startswith(key):
                return manager
    return "apt"


def distro_name() -> str:
    info = os_release()
    return info.get("PRETTY_NAME") or info.get("NAME") or "Linux"


def install_command(packages: dict[str, str], manager: str | None = None) -> str:
    """packages: {'apt': 'poppler-utils', 'pacman': 'poppler', 'pip': 'pillow-heif'}."""
    if "pip" in packages:
        return f"pip install {packages['pip']}"
    manager = manager or package_manager()
    name = packages.get(manager) or packages.get("apt", "")
    return f"{_INSTALL[manager]} {name}".strip()
