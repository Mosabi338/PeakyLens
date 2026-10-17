"""System tray icon and its right-click menu."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def make_icon() -> QIcon:
    """Draw a simple round 'P' icon in code so the project needs no image files."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#7c6cf0"))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 60, 60)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Segoe UI", 30, QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "P")
    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    open_requested = Signal()
    history_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self):
        super().__init__(make_icon())
        self.setToolTip("PeakyLens")

        menu = QMenu()
        for text, signal in (
            ("Open", self.open_requested),
            ("History", self.history_requested),
            ("Settings", self.settings_requested),
            ("Quit", self.quit_requested),
        ):
            action = QAction(text, menu)
            action.triggered.connect(signal.emit)
            menu.addAction(action)
        self._menu = menu  # keep a reference or Python may delete the menu
        self.setContextMenu(menu)

        self.activated.connect(self._on_activated)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.open_requested.emit()