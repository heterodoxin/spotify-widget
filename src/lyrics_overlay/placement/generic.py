"""Windows, macOS and X11: Qt positions the window itself."""
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QGuiApplication

from lyrics_overlay.placement.base import Monitor, Placement


class GenericPlacement(Placement):
    flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
    if sys.platform.startswith(('linux', 'freebsd')):
        # Unmanaged X11 windows stay above fullscreen apps and never take focus.
        flags |= Qt.X11BypassWindowManagerHint

    def __init__(self):
        self.widget = None

    def monitors(self):
        result = {}
        for screen in QGuiApplication.screens():
            full, free = screen.geometry(), screen.availableGeometry()
            result[screen.name()] = Monitor(full.x(), full.y(), full.width(), full.height(), free.left()-full.left(),
                                            free.top()-full.top(), full.right()-free.right(), full.bottom()-free.bottom())
        return result

    def focused(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        return screen.name() if screen else ''

    def cursor(self):
        point = QCursor.pos()
        return float(point.x()), float(point.y())

    def attach(self, widget):
        self.widget = widget
        return True

    def detach(self):
        self.widget = None

    def move(self, x, y):
        if self.widget is not None:
            self.widget.move(x, y)
