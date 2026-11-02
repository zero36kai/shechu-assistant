import json
from pathlib import Path
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class CharacterView(QWidget):
    dragged = Signal(QPointF)
    drag_finished = Signal()
    zoom_requested = Signal(int)

    def __init__(self, assets: Path, character="deepseek", parent=None):
        super().__init__(parent)
        self.assets = assets
        self.character = character
        self.state = "idle"
        self.motion_reduced = False
        self.started = time.monotonic()
        self.pointer = None
        self.frames = {}
        self.loaded_character = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("拖动角色移动提醒 · 滚轮调整大小")
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.update)
        self.set_character(character)

    def set_character(self, character):
        if character == self.loaded_character:
            return
        self.character = character
        folder = self.assets / "characters" / character
        self.portrait = QPixmap(str(folder / "portrait.png"))
        self.frames = {}
        manifest = folder / "animation.json"
        if manifest.exists():
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            for name, spec in raw["states"].items():
                self.frames[name] = ([QPixmap(str(folder / f)) for f in spec["frames"]], spec["durations"])
        self.loaded_character = character
        self.set_state("idle")

    def set_state(self, state):
        self.state = state
        self.started = time.monotonic()
        self.update()

    def set_reduced_motion(self, reduced):
        self.motion_reduced = reduced
        if reduced:
            self.timer.stop()
        elif self.isVisible():
            self.timer.start()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.motion_reduced:
            self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        if self.portrait.isNull():
            return
        elapsed = time.monotonic() - self.started
        pixmap = self.portrait
        spec = self.frames.get(self.state) or self.frames.get("idle")
        if spec:
            frames, durations = spec
            if self.state == "idle":
                position = (elapsed * 1000) % sum(durations)
            else:
                position = min(elapsed * 1000, sum(durations) - 1)
            index = 0
            while index < len(durations) - 1 and position >= durations[index]:
                position -= durations[index]
                index += 1
            pixmap = frames[0 if self.motion_reduced else index]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        area = QRectF(0, 0, self.width(), self.height())
        size = pixmap.size().scaled(area.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
        x = (self.width() - size.width()) / 2
        y = self.height() - size.height()
        painter.drawPixmap(QRectF(x, y, size.width(), size.height()), pixmap, QRectF(pixmap.rect()))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pointer = event.globalPosition()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self.pointer is not None:
            delta = event.globalPosition() - self.pointer
            self.pointer = event.globalPosition()
            self.dragged.emit(delta)

    def mouseReleaseEvent(self, event):
        if self.pointer is not None:
            self.pointer = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.drag_finished.emit()

    def wheelEvent(self, event):
        self.zoom_requested.emit(20 if event.angleDelta().y() > 0 else -20)
        event.accept()
