from dataclasses import replace
from datetime import date, datetime
import math
from pathlib import Path

from PySide6.QtCore import QDate, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .animation import CharacterView
from .config import CHARACTERS
from .core import Bounds, clamp_position


STYLE = """
QWidget { font-family: 'Microsoft YaHei UI'; font-size: 13px; color: #263440; }
QWidget#dashboard { background: #f4f6f7; }
QFrame#card, QFrame#panel { background: #ffffff; border: 1px solid #e0e5e8; border-radius: 18px; }
QFrame#card QLabel, QFrame#panel QLabel { background: transparent; }
QLabel#muted { color: #64727d; }
QLabel#small { color: #64727d; font-size: 12px; }
QLabel#heading { font-size: 24px; font-weight: 600; }
QLabel#section { font-size: 16px; font-weight: 600; }
QLabel#number { font-family: 'Segoe UI'; font-size: 32px; font-weight: 400; }
QLabel#error { color: #ad3939; font-size: 12px; }
QPushButton { background: #ffffff; border: 1px solid #d9e0e4; border-radius: 8px; padding: 8px 14px; }
QPushButton:hover { background: #f0f4f6; border-color: #879aa7; }
QPushButton:pressed { background: #e3ebef; }
QPushButton:focus { border: 2px solid #527c95; }
QPushButton:disabled { color: #73808a; background: #f3f5f6; border-color: #e1e6e9; }
QPushButton#primary { background: #273b47; color: white; border-color: #273b47; }
QPushButton#primary:hover { background: #3b5362; }
QPushButton#ghost { background: transparent; border: none; padding: 6px 9px; color: #536572; }
QPushButton#ghost:hover { background: #e8eef1; }
QPushButton#close { background: transparent; border: none; font-size: 21px; padding: 0; }
QPushButton#close:hover { background: #f9e6e5; color: #a13d37; }
QPushButton#checkin { text-align: left; padding: 11px 14px; font-size: 14px; background: #f7f9fa; }
QPushButton#checkin:checked { background: #eaf3ef; border-color: #9ebfb1; color: #315b4a; }
QPushButton#nav { text-align: left; border: none; background: transparent; padding: 11px 14px; }
QPushButton#nav:checked { background: #e5ebee; font-weight: 600; }
QPushButton#character { padding: 8px; border-radius: 12px; background: #fafbfc; }
QPushButton#character:checked { border: 2px solid #597d93; background: #edf3f6; }
QSpinBox, QComboBox, QDateEdit { min-height: 30px; padding: 3px 9px; border: 1px solid #cbd6dc; border-radius: 6px; background: white; }
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 24px; }
QSlider::groove:horizontal { height: 4px; background: #dce5e9; border-radius: 2px; }
QSlider::handle:horizontal { width: 16px; height: 16px; margin: -6px 0; background: #456d86; border-radius: 8px; }
QSlider::sub-page:horizontal { background: #456d86; border-radius: 2px; }
QCheckBox { spacing: 9px; padding: 5px 0; }
QCheckBox::indicator { width: 16px; height: 16px; }
QTableWidget { background: white; border: none; gridline-color: #edf0f2; selection-background-color: #eaf0f3; selection-color: #263440; }
QHeaderView::section { background: white; color: #64727d; border: none; border-bottom: 1px solid #e8edef; padding: 10px 8px; }
QScrollArea { border: none; background: transparent; }
QToolTip { background: #253a47; color: white; border: none; padding: 6px; }
"""


def label(text, name="", wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback=None, name=""):
    widget = QPushButton(text)
    if name:
        widget.setObjectName(name)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        widget.clicked.connect(callback)
    return widget


def app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#487a97"))
    path = QPainterPath()
    path.moveTo(32, 4)
    path.cubicTo(24, 17, 10, 29, 10, 39)
    path.cubicTo(10, 67, 54, 67, 54, 39)
    path.cubicTo(54, 29, 40, 17, 32, 4)
    painter.drawPath(path)
    painter.setPen(QPen(QColor("#ffffff"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawArc(19, 32, 26, 20, 200 * 16, 130 * 16)
    painter.end()
    return QIcon(pixmap)


class DragHeader(QWidget):
    moved = Signal(QPoint)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.anchor = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.anchor = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.anchor is not None:
            current = event.globalPosition().toPoint()
            self.moved.emit(current - self.anchor)
            self.anchor = current

    def mouseReleaseEvent(self, event):
        if self.anchor is not None:
            self.anchor = None
            self.finished.emit()


class BubbleFrame(DragHeader):
    def __init__(self, image, parent):
        super().__init__()
        self.setParent(parent)
        self.image = QPixmap(str(image)).transformed(QTransform().scale(-1, 1))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self.image)


class ReminderWindow(QWidget):
    dismissed = Signal()
    snoozed = Signal()
    completed = Signal(str)
    history_requested = Signal()
    geometry_saved = Signal(int, int, str)
    height_changed = Signal(int)
    interacted = Signal()

    def __init__(self, settings, assets: Path):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("社畜小助手 · 提醒")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.settings = settings
        self.records = {}
        self.current_character = settings.character
        self.character = CharacterView(assets, settings.character, self)
        self.character.dragged.connect(lambda delta: self.move(self.pos() + delta.toPoint()))
        self.character.drag_finished.connect(self.finish_move)
        self.character.zoom_requested.connect(self.zoom)
        self.card = BubbleFrame(assets / "bubble.png", self)
        self.card.moved.connect(lambda delta: self.move(self.pos() + delta))
        self.card.finished.connect(self.finish_move)
        self.heading = QLabel("喝口水，歇一下", self.card)
        self.heading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.message = QLabel(self.card)
        self.message.hide()
        self.feedback = QLabel("两项可以分别打卡", self.card)
        self.feedback.setWordWrap(True)
        self.feedback.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.water_button = button("喝好了", lambda: self.completed.emit("water"))
        self.kegel_button = button("提肛了", lambda: self.completed.emit("kegel"))
        self.snooze_button = button("稍后", self.snoozed.emit, "quiet")
        self.history_button = button("记录", self.history_requested.emit, "quiet")
        self.close_button = button("×", self.dismissed.emit, "close")
        self.close_button.setAccessibleName("关闭提醒")
        self.close_button.setToolTip("关闭提醒（Esc），不计为完成")
        self.smaller = button("−", lambda: self.zoom(-20), "quiet")
        self.larger = button("＋", lambda: self.zoom(20), "quiet")
        self.smaller.setAccessibleName("缩小提醒")
        self.larger.setAccessibleName("放大提醒")
        for widget in (self.water_button, self.kegel_button, self.snooze_button,
                       self.history_button, self.close_button, self.smaller, self.larger):
            widget.setParent(self.card)
        self.water_button.setCheckable(True)
        self.kegel_button.setCheckable(True)
        self.escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape.activated.connect(self.dismissed.emit)
        self.return_idle = QTimer(self)
        self.return_idle.setSingleShot(True)
        self.return_idle.timeout.connect(lambda: self.character.set_state("idle"))
        self.apply_settings(settings)
        for screen in QApplication.screens():
            screen.availableGeometryChanged.connect(self.reflow)
        QApplication.instance().screenRemoved.connect(self.reflow)
        QApplication.instance().screenAdded.connect(self.screen_added)

    def screen_added(self, screen):
        screen.availableGeometryChanged.connect(self.reflow)
        self.reflow()

    def reflow(self, *_):
        self.apply_settings(self.settings)

    def apply_settings(self, settings):
        if settings.character != self.settings.character:
            self.current_character = settings.character
        self.settings = settings
        self.character.set_character(self.current_character)
        self.character.set_reduced_motion(settings.reduced_motion)
        area = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        self.scale = min(settings.pet_height / 280, (area.width() - 16) / 472, (area.height() - 16) / 398)
        scale = self.scale
        def rect(widget, x, y, w, h):
            widget.setGeometry(round(x*scale), round(y*scale), round(w*scale), round(h*scale))
        self.setFixedSize(round(472*scale), round(398*scale))
        rect(self.character, 242, 110, 230, 280)
        rect(self.card, 0, 0, 274, 178)
        rect(self.heading, 30, 26, 174, 25)
        rect(self.close_button, 217, 23, 26, 26)
        rect(self.feedback, 30, 52, 212, 35)
        rect(self.water_button, 30, 90, 99, 28)
        rect(self.kegel_button, 136, 90, 99, 28)
        rect(self.snooze_button, 28, 122, 77, 23)
        rect(self.history_button, 107, 122, 48, 23)
        rect(self.smaller, 177, 122, 26, 23)
        rect(self.larger, 208, 122, 26, 23)
        self.snooze_button.setText(f"{settings.snooze_minutes}分钟后")
        self.setStyleSheet(f"""
            QWidget {{ font-family: 'Microsoft YaHei UI'; color:#32536c; font-size:{16*scale:.2f}px; background:transparent; }}
            QPushButton {{ background:#e9f5fc; border:1px solid #abcce2; border-radius:{9*scale:.2f}px; padding:0; }}
            QPushButton:hover {{ background:#d5edfc; }}
            QPushButton:checked {{ background:#d9f0e4; border-color:#91baa3; color:#356249; }}
            QPushButton:focus {{ border:1px solid #537e9b; }}
            QPushButton#quiet, QPushButton#close {{ background:transparent; border:none; }}
            QPushButton#quiet:hover {{ background:#e5f1fa; }}
            QPushButton#close {{ font-size:{25*scale:.2f}px; }}
            QPushButton#close:hover {{ background:#fbe8e9; color:#a43f49; }}
        """)
        self.heading.setStyleSheet(f"font-size:{18*scale:.2f}px;font-weight:600;background:transparent;")
        self.feedback.setStyleSheet(f"font-size:{14*scale:.2f}px;color:#647b8d;background:transparent;")
        self.ensure_visible()

    def zoom(self, delta):
        self.interacted.emit()
        self.height_changed.emit(min(480, max(180, self.settings.pet_height + delta)))

    def ensure_visible(self, *_):
        screens = QApplication.screens()
        screen = next((s for s in screens if s.availableGeometry().contains(self.frameGeometry().center())), None)
        if screen is None:
            screen = next((s for s in screens if s.name() == self.settings.screen_name), QApplication.primaryScreen())
        rect = screen.availableGeometry()
        self.move(*clamp_position(self.x(), self.y(), self.width(), self.height(),
                                 Bounds(rect.x(), rect.y(), rect.width(), rect.height())))

    def finish_move(self):
        self.ensure_visible()
        self.interacted.emit()
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        self.geometry_saved.emit(self.x(), self.y(), screen.name())

    def place(self):
        screen = next((s for s in QApplication.screens() if s.name() == self.settings.screen_name), QApplication.primaryScreen())
        rect = screen.availableGeometry()
        if self.settings.position_x is None or self.settings.position_y is None:
            self.move(rect.right() - self.width() - 16, rect.bottom() - self.height() - 16)
        else:
            self.move(self.settings.position_x, self.settings.position_y)
        self.ensure_visible()

    def begin(self, records, character=None):
        if character is not None:
            self.current_character = character
            self.character.set_character(character)
        self.set_records(records)
        self.feedback.setText("两项可以分别打卡")
        self.place()
        self.character.set_state("wave")
        self.return_idle.start(1600)
        self.showNormal()
        self.raise_()

    def set_records(self, records):
        self.records = dict(records)
        for kind, widget, text in (("water", self.water_button, "喝好了"), ("kegel", self.kegel_button, "提肛了")):
            widget.setChecked(kind in records)
            widget.setText("已记录 ✓" if kind in records else text)
            widget.setToolTip("点击撤销这一次记录" if kind in records else ("记录喝水一次" if kind == "water" else "记录提肛一次"))
        self.heading.setText("都做好啦！" if len(records) == 2 else "喝口水，歇一下")

    def show_feedback(self, text, state="idle", error=False):
        self.feedback.setText(text)
        self.feedback.setStyleSheet(f"font-size:{14*self.scale:.2f}px;color:{'#b44747' if error else '#647b8d'};background:transparent;")
        self.character.set_state(state)
        self.return_idle.start(2500)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.dismissed.emit()

    def hideEvent(self, event):
        self.return_idle.stop()
        super().hideEvent(event)


class Dashboard(QWidget):
    reminder_requested = Signal()
    pause_requested = Signal()
    settings_saved = Signal(object)
    character_selected = Signal(str)
    undo_requested = Signal(int)
    close_reminders_requested = Signal()
    reset_position_requested = Signal()

    def __init__(self, settings, assets: Path, store):
        super().__init__()
        self.settings = settings
        self.assets = assets
        self.current_character = settings.character
        self.store = store
        self.setObjectName("dashboard")
        self.setWindowTitle("社畜小助手")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(STYLE)
        self.resize(1020, 730)
        self.setMinimumSize(780, 640)
        shell = QHBoxLayout(self)
        shell.setContentsMargins(20, 24, 24, 24)
        shell.setSpacing(24)
        nav = QVBoxLayout()
        brand = label("社畜小助手", "section")
        nav.addWidget(brand)
        nav.addWidget(label("V2 · 桌面陪伴", "small"))
        nav.addSpacing(30)
        self.pages = QStackedWidget()
        self.nav_buttons = []
        for i, text in enumerate(("今天", "历史记录", "角色与外观", "提醒设置")):
            widget = button(text, lambda checked=False, index=i: self.go(index), "nav")
            widget.setCheckable(True)
            widget.setFixedWidth(156)
            nav.addWidget(widget)
            self.nav_buttons.append(widget)
        nav.addStretch()
        self.pause_button = button("暂停提醒", self.pause_requested.emit)
        nav.addWidget(self.pause_button)
        nav.addWidget(button("关闭全部提醒", self.close_reminders_requested.emit, "ghost"))
        nav.addWidget(label("记录保存在这台电脑", "small"))
        shell.addLayout(nav)
        shell.addWidget(self.pages, 1)
        self.build_home()
        self.build_history()
        self.build_characters()
        self.build_settings()
        self.go(0)

    def page(self, title, subtitle):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(label(title, "heading"))
        layout.addWidget(label(subtitle, "muted", True))
        self.pages.addWidget(page)
        return page, layout

    def build_home(self):
        _, layout = self.page("把两件小事，留一点时间", "喝水与提肛分别记录。每一次完成，都有迹可循。")
        top = QHBoxLayout()
        top.setSpacing(16)
        companion_panel = QFrame()
        companion_panel.setObjectName("panel")
        companion_layout = QVBoxLayout(companion_panel)
        companion_layout.setContentsMargins(12, 14, 12, 16)
        self.preview = CharacterView(self.assets, self.settings.character)
        self.preview.setMinimumSize(230, 255)
        self.preview.setMaximumHeight(300)
        self.preview.set_reduced_motion(self.settings.reduced_motion)
        companion_layout.addWidget(self.preview, 1)
        self.companion_name = label("", "section")
        self.companion_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        companion_layout.addWidget(self.companion_name)
        companion_layout.addWidget(button("叫她出来", self.reminder_requested.emit, "primary"))
        top.addWidget(companion_panel, 1)
        stats = QFrame()
        stats.setObjectName("panel")
        right = QVBoxLayout(stats)
        right.setContentsMargins(24, 22, 24, 22)
        right.addWidget(label("今天的记录", "section"))
        self.today_date = label("", "small")
        right.addWidget(self.today_date)
        counts = QHBoxLayout()
        self.water_count = label("0", "number")
        self.kegel_count = label("0", "number")
        for title, value in (("喝水 · 次", self.water_count), ("提肛 · 次", self.kegel_count)):
            block = QVBoxLayout()
            block.addWidget(label(title, "muted"))
            block.addWidget(value)
            counts.addLayout(block)
        right.addLayout(counts)
        right.addSpacing(18)
        self.next_label = label("", "section", True)
        right.addWidget(self.next_label)
        self.status_note = label("只在设置的时段提醒", "muted", True)
        right.addWidget(self.status_note)
        right.addStretch()
        right.addWidget(button("查看今天的明细", lambda: self.go(1)))
        top.addWidget(stats, 1)
        layout.addLayout(top)
        recent_panel = QFrame()
        recent_panel.setObjectName("panel")
        recent_layout = QVBoxLayout(recent_panel)
        recent_layout.setContentsMargins(20, 16, 20, 16)
        recent_layout.addWidget(label("最近完成", "section"))
        self.recent = label("还没有逐次记录，完成后会显示在这里。", "muted", True)
        self.recent.setMinimumHeight(74)
        recent_layout.addWidget(self.recent)
        layout.addWidget(recent_panel)
        self.home_error = label("", "error", True)
        layout.addWidget(self.home_error)
        layout.addStretch()

    def build_history(self):
        _, layout = self.page("每一次，都记得", "按实际完成时间归档。撤销会保留痕迹，不计入完成次数。")
        filters = QHBoxLayout()
        filters.addWidget(label("日期", "muted"))
        self.history_date = QDateEdit(QDate.currentDate())
        self.history_date.setCalendarPopup(True)
        self.history_date.setDisplayFormat("yyyy-MM-dd")
        self.history_date.dateChanged.connect(self.refresh_history)
        filters.addWidget(self.history_date)
        filters.addStretch()
        self.history_summary = label("", "muted")
        filters.addWidget(self.history_summary)
        layout.addLayout(filters)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("完成时间", "事项", "记录", "操作"))
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(3, 90)
        layout.addWidget(self.table, 1)
        self.history_note = label("", "small", True)
        layout.addWidget(self.history_note)

    def build_characters(self):
        _, layout = self.page("八位伙伴，轮流陪你", "每轮随机出场，八位一轮不重复；点击角色可以预览。")
        grid = QGridLayout()
        grid.setSpacing(12)
        self.character_buttons = {}
        for i, (key, (model, _)) in enumerate(CHARACTERS.items()):
            widget = button(model, lambda checked=False, c=key: self.character_selected.emit(c), "character")
            widget.setCheckable(True)
            widget.setMinimumSize(124, 148)
            widget.setIcon(QIcon(str(self.assets / "characters" / key / "portrait.png")))
            from PySide6.QtCore import QSize
            widget.setIconSize(QSize(65, 114))
            widget.setToolTip(f"预览 {model}")
            grid.addWidget(widget, i // 4, i % 4)
            self.character_buttons[key] = widget
        layout.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(label("角色高度", "section"))
        self.height_slider = QSlider(Qt.Orientation.Horizontal)
        self.height_slider.setRange(180, 480)
        self.height_slider.setValue(self.settings.pet_height)
        self.height_value = label(f"{self.settings.pet_height} px", "muted")
        self.height_slider.valueChanged.connect(lambda v: self.height_value.setText(f"{v} px"))
        self.height_slider.sliderReleased.connect(lambda: self.settings_saved.emit(replace(self.settings, pet_height=self.height_slider.value())))
        row.addWidget(self.height_slider, 1)
        row.addWidget(self.height_value)
        layout.addLayout(row)
        self.reduced_motion = QCheckBox("减少动态，只显示静止角色")
        self.reduced_motion.setChecked(self.settings.reduced_motion)
        self.reduced_motion.toggled.connect(lambda v: self.settings_saved.emit(replace(self.settings, reduced_motion=v)))
        layout.addWidget(self.reduced_motion)
        actions = QHBoxLayout()
        actions.addWidget(button("预览当前提醒", self.reminder_requested.emit, "primary"))
        actions.addWidget(button("放回右下角", self.reset_position_requested.emit))
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(label("拖动角色即可移动提醒，滚轮或提醒上的 ＋ / − 可直接调整大小。", "small", True))
        layout.addStretch()

    def build_settings(self):
        _, layout = self.page("让提醒，合你的节奏", "保存后生效。暂停、关闭和稍后都不会生成完成记录。")
        panel = QFrame()
        panel.setObjectName("panel")
        form = QFormLayout(panel)
        form.setContentsMargins(24, 22, 24, 22)
        form.setSpacing(16)
        self.fields = {}
        for key, title, low, high, suffix in (
            ("interval_minutes", "提醒间隔", 1, 240, " 分钟"),
            ("start_hour", "开始时间", 0, 23, ":00"),
            ("end_hour", "结束时间", 1, 24, ":00"),
            ("snooze_minutes", "稍后提醒", 1, 60, " 分钟"),
            ("idle_skip_minutes", "离开电脑后暂停计时", 1, 60, " 分钟"),
            ("auto_hide_seconds", "提醒自动收起", 0, 600, " 秒"),
        ):
            field = QSpinBox()
            field.setRange(low, high)
            field.setSuffix(suffix)
            field.setValue(getattr(self.settings, key))
            if key == "auto_hide_seconds":
                field.setSpecialValueText("不自动收起，可随时关闭")
            self.fields[key] = field
            form.addRow(title, field)
        self.workdays = QCheckBox("仅工作日提醒")
        self.workdays.setChecked(self.settings.workdays_only)
        form.addRow("工作日", self.workdays)
        self.smart_days = QCheckBox("识别节假日和调休补班")
        self.smart_days.setChecked(self.settings.smart_workday)
        form.addRow("节假日", self.smart_days)
        layout.addWidget(panel)
        layout.addWidget(label("锁屏、离开电脑或全屏应用时暂停自动提醒。网络不可用时按本地工作日设置运行。", "small", True))
        actions = QHBoxLayout()
        actions.addWidget(button("保存设置", self.save_form, "primary"))
        self.settings_notice = label("", "muted", True)
        actions.addWidget(self.settings_notice, 1)
        layout.addLayout(actions)
        layout.addStretch()

    def save_form(self):
        values = {key: widget.value() for key, widget in self.fields.items()}
        values.update(workdays_only=self.workdays.isChecked(), smart_workday=self.smart_days.isChecked())
        candidate = replace(self.settings, **values)
        try:
            candidate.validate()
        except ValueError as exc:
            self.settings_notice.setText(str(exc))
            return
        self.settings_saved.emit(candidate)

    def go(self, index):
        self.pages.setCurrentIndex(index)
        for i, widget in enumerate(self.nav_buttons):
            widget.setChecked(i == index)
        if index == 1:
            self.refresh_history()

    def apply_settings(self, settings):
        if settings.character != self.settings.character:
            self.current_character = settings.character
        self.settings = settings
        self.show_character(self.current_character)
        self.preview.set_reduced_motion(settings.reduced_motion)
        for key, widget in self.character_buttons.items():
            widget.setChecked(key == settings.character)
        self.height_slider.blockSignals(True)
        self.height_slider.setValue(settings.pet_height)
        self.height_slider.blockSignals(False)
        self.height_value.setText(f"{settings.pet_height} px")
        self.reduced_motion.blockSignals(True)
        self.reduced_motion.setChecked(settings.reduced_motion)
        self.reduced_motion.blockSignals(False)

    def show_character(self, character):
        self.current_character = character
        self.preview.set_character(character)
        self.companion_name.setText(CHARACTERS[character][0])

    def refresh(self, cycle, reason=""):
        today = date.today().isoformat()
        totals = self.store.totals(today)
        self.today_date.setText(today)
        self.water_count.setText(str(totals["water"]))
        self.kegel_count.setText(str(totals["kegel"]))
        self.pause_button.setText("恢复提醒" if cycle.paused else "暂停提醒")
        if cycle.paused:
            state = "已暂停提醒"
        elif cycle.visible:
            state = "提醒正在桌面上"
        elif reason:
            state = reason
        else:
            minutes = max(1, math.ceil(cycle.remaining / 60))
            state = f"约 {minutes} 分钟后提醒"
        self.next_label.setText(state)
        self.status_note.setText(f"{self.settings.start_hour:02d}:00—{self.settings.end_hour:02d}:00 · 每 {self.settings.interval_minutes} 分钟")
        recent = [row for row in self.store.day_records(today) if row["undone_at"] is None][:3]
        self.recent.setText("\n\n".join(
            f"{datetime.fromisoformat(row['occurred_at']).strftime('%H:%M')}    {'喝水' if row['kind']=='water' else '提肛'}完成一次"
            for row in recent
        ) or "还没有逐次记录，完成后会显示在这里。")
        if self.pages.currentIndex() == 1:
            self.refresh_history()

    def refresh_history(self, *_):
        day = self.history_date.date().toString("yyyy-MM-dd")
        rows = self.store.day_records(day)
        totals = self.store.totals(day)
        self.history_summary.setText(f"喝水 {totals['water']} 次 · 提肛 {totals['kegel']} 次")
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (datetime.fromisoformat(row["occurred_at"]).strftime("%H:%M:%S"),
                      "喝水" if row["kind"] == "water" else "提肛", "已撤销" if row["undone_at"] else "已完成")
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if row["undone_at"]:
                    item.setForeground(QColor("#75828b"))
                self.table.setItem(index, column, item)
            if row["undone_at"] is None:
                undo = button("撤销", lambda checked=False, event_id=row["id"]: self.undo_requested.emit(event_id), "ghost")
                self.table.setCellWidget(index, 3, undo)
            else:
                self.table.removeCellWidget(index, 3)
                self.table.setItem(index, 3, QTableWidgetItem("—"))
            self.table.setRowHeight(index, 49)
        notes = []
        if not rows:
            notes.append("这一天没有逐次记录。")
        self.history_note.setText("\n".join(notes))
