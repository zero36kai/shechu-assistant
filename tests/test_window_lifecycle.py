from datetime import datetime
import ctypes
from ctypes import wintypes
import sys

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from water_assistant.app import Controller
from water_assistant.config import Settings


@pytest.fixture
def controller(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    Settings(start_hour=0, end_hour=24, workdays_only=False).save(tmp_path / "settings.json")
    value = Controller(application, tmp_path, isolated=True)
    value.timer.stop()
    monkeypatch.setattr(value, "eligibility", lambda: (True, ""))
    value.now = 0.0
    value.cycle.clock = lambda: value.now
    value.cycle.last_tick = value.now
    yield value
    value.shutdown()
    value.dashboard.hide()
    value.window.deleteLater()
    value.dashboard.deleteLater()
    application.processEvents()


def test_automatic_reminder_recovers_after_previous_window_was_minimized(controller):
    controller.show_reminder(manual=True)
    controller.window.showMinimized()
    controller.application.processEvents()
    assert controller.window.isMinimized()
    controller.dismiss()
    controller.cycle.remaining = 1
    controller.now += 1
    controller.tick()
    controller.application.processEvents()
    assert controller.cycle.visible and not controller.cycle.manual
    assert controller.window.isVisible()
    assert not controller.window.isMinimized()
    assert controller.store.day_records(datetime.now().date().isoformat()) == []


@pytest.mark.parametrize("maximized", [False, True])
def test_tray_history_restores_minimized_dashboard_without_recording(controller, maximized):
    controller.show_dashboard()
    if maximized:
        controller.dashboard.showMaximized()
    controller.dashboard.showMinimized()
    controller.application.processEvents()
    assert controller.dashboard.isMinimized()
    controller.show_reminder(manual=True)
    session = controller.cycle.session_id
    next(action for action in controller.menu.actions() if action.text() == "历史记录").trigger()
    controller.application.processEvents()
    assert controller.dashboard.pages.currentIndex() == 1
    assert controller.dashboard.isVisible()
    assert not controller.dashboard.isMinimized()
    assert controller.dashboard.isMaximized() == maximized
    assert controller.cycle.session_id == session
    assert controller.store.session_records(session) == {}


@pytest.mark.parametrize("action", ["记录", "稍后"])
@pytest.mark.parametrize("selected", [(), ("water",), ("kegel",), ("water", "kegel")])
def test_reminder_actions_hide_without_opening_dashboard_or_adding_records(controller, action, selected):
    controller.show_reminder(manual=True)
    session = controller.cycle.session_id
    for kind in selected:
        widget = controller.window.water_button if kind == "water" else controller.window.kegel_button
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    records = controller.store.session_records(session)
    assert set(records) == set(selected)
    widget = next(button for button in controller.window.findChildren(QPushButton) if button.text() == action)
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    controller.application.processEvents()
    assert not controller.window.isVisible()
    assert not controller.cycle.visible
    assert not controller.dashboard.isVisible()
    assert controller.store.session_records(session) == records
    if action == "记录":
        assert controller.cycle.session_id is None
        assert not controller.cycle.snoozed
        assert controller.cycle.remaining == controller.settings.interval_minutes * 60
    else:
        assert controller.cycle.session_id == session
        assert controller.cycle.snoozed
        assert controller.cycle.remaining == controller.settings.snooze_minutes * 60
        for _ in range(controller.settings.snooze_minutes * 60):
            controller.now += 1
            controller.tick()
        assert controller.window.isVisible()
        assert controller.window.records == records
        assert controller.cycle.session_id == session
        assert not controller.dashboard.isVisible()


def test_size_is_saved_from_dashboard_and_wheel_leaves_it_unchanged(controller):
    controller.show_reminder(manual=True)
    controller.dashboard.height_slider.setValue(320)
    controller.dashboard.height_slider.sliderReleased.emit()
    assert controller.settings.pet_height == 320
    saved, warning = Settings.load(controller.settings_path)
    assert saved.pet_height == 320 and not warning
    size = controller.window.size()
    for delta in (120, -120):
        event = QWheelEvent(QPointF(20, 20), QPointF(20, 20), QPoint(), QPoint(0, delta),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(controller.window.character, event)
        assert controller.settings.pet_height == 320
        assert controller.window.size() == size
    assert {widget.text() for widget in controller.window.findChildren(QPushButton)} == {
        "喝好了", "提肛了", "记录", "稍后", "×"}


def test_reminder_is_a_tool_window_and_dashboard_remains_a_regular_window(controller):
    assert controller.window.windowType() == Qt.WindowType.Tool
    assert controller.window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert controller.window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert controller.dashboard.windowType() == Qt.WindowType.Window


def test_manual_reopen_restores_current_reminder_and_preserves_completion(controller):
    controller.show_reminder(manual=True)
    controller.complete("water")
    session = controller.cycle.session_id
    records = dict(controller.window.records)
    controller.window.showMinimized()
    controller.application.processEvents()
    assert controller.window.isMinimized()
    controller.show_reminder(manual=True)
    controller.application.processEvents()
    assert controller.window.isVisible() and not controller.window.isMinimized()
    assert controller.cycle.session_id == session
    assert controller.window.records == records
    assert controller.store.session_records(session) == records


def test_native_windows_reminder_is_excluded_from_taskbar(controller):
    if sys.platform != "win32" or controller.application.platformName() != "windows":
        pytest.skip("需要真实 Windows Qt 窗口")
    controller.show_reminder(manual=True)
    controller.application.processEvents()
    get_style = ctypes.windll.user32.GetWindowLongW
    get_style.argtypes = [wintypes.HWND, ctypes.c_int]
    get_style.restype = wintypes.LONG
    style = get_style(int(controller.window.winId()), -20)
    assert style & 0x00000080, "缺少 WS_EX_TOOLWINDOW"
    assert not style & 0x00040000, "不应设置 WS_EX_APPWINDOW"
