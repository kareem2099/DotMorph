"""Edge dock: drag the wheel against a screen edge and it becomes a slim tab there.

Modes:
  free    the full wheel, anywhere (560 x 560 window)
  docked  a slim tab glued to the left or right edge
  peek    a half wheel opening out of that edge (hover / click / drag files over the tab)

The side and height on the edge are remembered (settings.json), so the daemon brings the
tab back after every login.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, QRect, Signal, Slot
from PySide6.QtGui import QCursor, QGuiApplication

WHEEL = 560  # full wheel window
WHEEL_R = 248  # radius of the wheel's backdrop disc
TAB_W, TAB_H = 46, 156
PEEK_W = 344  # hub + rings on one side of the centre
SNAP = 14  # px: the disc this close to an edge docks it


class Dock(QObject):
    modeChanged = Signal()
    dismissed = Signal()  # right-click on the tab: hide (daemon) or quit

    def __init__(self, bridge, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._window = None  # set by attach() once QML has created it
        self._bridge = bridge
        self._mode = "free"

    def attach(self, window) -> None:
        self._window = window

    # ---- state for QML ------------------------------------------------------------------
    @Property(str, notify=modeChanged)
    def mode(self) -> str:
        return self._mode

    @Property(str, notify=modeChanged)
    def side(self) -> str:
        return self._bridge.settings.dock_side or "left"

    @property
    def docked(self) -> bool:
        return self._mode != "free"

    # ---- geometry -----------------------------------------------------------------------
    def _area(self) -> QRect:
        screen = self._window.screen() or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _edge_y(self, height: int) -> int:
        area = self._area()
        centre = area.top() + self._bridge.settings.dock_y * area.height()
        return int(min(max(centre - height / 2, area.top()), area.bottom() - height + 1))

    def _apply(self) -> None:
        area = self._area()
        left = self.side == "left"
        if self._mode == "docked":
            w, h = TAB_W, TAB_H
        elif self._mode == "peek":
            w, h = PEEK_W, min(WHEEL, area.height())
        else:
            w = h = WHEEL
        x = area.left() if left else area.right() - w + 1
        if self._mode == "free":  # leave the edge, a little inward
            x = area.left() + 24 if left else area.right() - w - 24
        self._window.setGeometry(x, self._edge_y(h), w, h)

    def _set_mode(self, mode: str) -> None:
        changed = mode != self._mode
        self._mode = mode
        self._apply()
        if changed:
            self.modeChanged.emit()

    # ---- slots ----------------------------------------------------------------------------
    @Slot()
    def dragEnded(self) -> None:
        """After the free wheel was moved: snap to an edge if its disc touches one."""
        if self._mode != "free":
            return
        g = self._window.geometry()
        area = self._area()
        cx, cy = g.x() + g.width() / 2, g.y() + g.height() / 2
        if cx - WHEEL_R <= area.left() + SNAP:
            side = "left"
        elif cx + WHEEL_R >= area.right() - SNAP:
            side = "right"
        else:
            return
        self._bridge.update_settings(
            dock_side=side, dock_y=(cy - area.top()) / max(1, area.height())
        )
        self._set_mode("docked")

    @Slot()
    def peek(self) -> None:
        if self._mode != "free":
            self._set_mode("peek")

    @Slot()
    def collapse(self) -> None:
        if self._mode == "peek":
            self._set_mode("docked")

    @Slot(float)
    def slide(self, dy: float) -> None:
        """Move the tab along its edge."""
        area = self._area()
        s = self._bridge.settings
        s.dock_y = min(1.0, max(0.0, s.dock_y + dy / max(1, area.height())))
        self._apply()

    @Slot()
    def slideEnded(self) -> None:
        self._bridge.update_settings(dock_y=self._bridge.settings.dock_y)

    @Slot()
    def undock(self) -> None:
        """Pulled away from the edge: back to the full wheel, centred on the pointer."""
        self._bridge.update_settings(dock_side="")
        self._mode = "free"
        pos = QCursor.pos()
        area = self._area()
        x = min(max(pos.x() - WHEEL // 2, area.left()), area.right() - WHEEL)
        y = min(max(pos.y() - WHEEL // 2, area.top()), area.bottom() - WHEEL)
        self._window.setGeometry(x, y, WHEEL, WHEEL)
        self.modeChanged.emit()

    def forget(self) -> None:
        """Undocked from the settings window: drop the tab (the daemon hides the wheel)."""
        if self._mode == "free":
            return
        self._mode = "free"
        self.modeChanged.emit()
        if self._window is not None:
            self._window.hide()
            self._window.setGeometry(self._window.x(), self._window.y(), WHEEL, WHEEL)
        self._bridge.menuHidden()

    @Slot()
    def dismiss(self) -> None:
        self.dismissed.emit()

    def restore(self, open_wheel: bool) -> bool:
        """Start in the saved dock (if any). Returns True when docked."""
        if not self._bridge.settings.dock_side:
            return False
        self._set_mode("peek" if open_wheel else "docked")
        self.modeChanged.emit()
        return True
