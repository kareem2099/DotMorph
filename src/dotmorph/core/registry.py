"""Backend registry: builds the live conversion matrix from the tools installed right now.

Backends are tried in order; the first one that can do `src -> action` wins, so Pillow
handles PNG -> JPG even though ImageMagick could too.
"""

from __future__ import annotations

import ctypes.util
import importlib.util
import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .common import Context, ConversionError, Job, Options
from .formats import FORMATS, sort_actions
from .system import install_command


@dataclass(frozen=True)
class Requirement:
    tool: str  # executable on PATH, "py:module" (Python package) or "lib:name" (shared library)
    packages: dict[str, str] = field(default_factory=dict)  # package manager -> package
    purpose: str = ""

    def present(self) -> bool:
        if self.tool.startswith("py:"):
            return importlib.util.find_spec(self.tool[3:]) is not None
        if self.tool.startswith("lib:"):
            return ctypes.util.find_library(self.tool[4:]) is not None
        return shutil.which(self.tool) is not None

    @property
    def install(self) -> str:
        return install_command(self.packages)

    @property
    def name(self) -> str:
        prefix, sep, rest = self.tool.partition(":")
        return rest if sep and prefix in ("py", "lib") else self.tool


class Backend:
    name = ""
    description = ""
    requirements: tuple[Requirement, ...] = ()  # all needed for the backend to work
    extras: tuple[Requirement, ...] = ()  # optional, each unlocks more formats

    def available(self) -> bool:
        return all(r.present() for r in self.requirements)

    def potential_pairs(self) -> dict[str, set[str]]:
        """Everything this backend could do with all of its tools installed."""
        return {}

    def pairs(self) -> dict[str, set[str]]:
        """What it can do right now. Override when it depends on probed capabilities."""
        return self.potential_pairs() if self.available() else {}

    def run(self, job: Job) -> list[Path]:
        raise NotImplementedError

    def run_batch(
        self, srcs: Sequence[Path], action: str, opts: Options, ctx: Context
    ) -> list[Path]:
        raise ConversionError(f"{self.name} cannot run {action} on several files")


def backends() -> list[Backend]:
    from .backends import ALL

    return ALL


@lru_cache(maxsize=1)
def _table() -> dict[str, dict[str, Backend]]:
    table: dict[str, dict[str, Backend]] = {}
    for backend in backends():
        try:
            pairs = backend.pairs()
        except Exception:  # a broken tool must never take the whole app down
            continue
        for src, actions in pairs.items():
            slot = table.setdefault(src, {})
            for action in actions:
                slot.setdefault(action, backend)
    return table


def refresh() -> None:
    """Forget probed capabilities (after installing a tool, and in tests)."""
    _table.cache_clear()
    for backend in backends():
        clear = getattr(backend, "clear_cache", None)
        if clear:
            clear()


def actions_for(fmt: str) -> list[str]:
    return sort_actions(_table().get(fmt, {}), fmt)


def backend_for(fmt: str, action: str) -> Backend | None:
    return _table().get(fmt, {}).get(action)


def matrix() -> dict[str, list[str]]:
    """source format -> actions, in catalog order."""
    table = _table()
    order = {ext: i for i, ext in enumerate(FORMATS)}
    return {
        src: actions_for(src)
        for src in sorted(table, key=lambda s: (order.get(s, len(order)), s))
        if table[src]
    }


def missing_for(fmt: str, action: str) -> list[Requirement]:
    """Tools that would make `fmt -> action` possible, if any."""
    for backend in backends():
        if action in backend.potential_pairs().get(fmt, set()):
            missing = [r for r in backend.requirements if not r.present()]
            if missing:
                return missing
    return []


def potential_count() -> tuple[int, int]:
    """(conversions available now, conversions possible with everything installed)."""
    now = sum(len(v) for v in _table().values())
    every: dict[str, set[str]] = {src: set(acts) for src, acts in _table().items()}
    for backend in backends():
        if backend.available():  # gaps from its build options can't be fixed by installing it
            continue
        for src, actions in backend.potential_pairs().items():
            every.setdefault(src, set()).update(actions)
    return now, max(now, sum(len(v) for v in every.values()))
