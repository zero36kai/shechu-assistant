from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image, ImageChops
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from water_assistant.config import Settings
from water_assistant.ui import ReminderWindow


@pytest.fixture(scope="module")
def application():
    app = QApplication.instance() or QApplication([])
    for font in Path("C:/Windows/Fonts").glob("msyh*.ttc"):
        QFontDatabase.addApplicationFont(str(font))
    return app


@pytest.fixture
def reminder(application):
    window = ReminderWindow(Settings(), Path(__file__).resolve().parents[1] / "assets/v2")
    yield window
    window.hide()
    window.deleteLater()
    application.processEvents()


def test_whole_composition_scales_and_controls_remain_inside(reminder, application):
    reminder.show()
    application.processEvents()
    sizes = []
    for height in (180, 280, 480):
        reminder.apply_settings(replace(reminder.settings, pet_height=height))
        application.processEvents()
        assert reminder.card.geometry().center().x() < reminder.character.geometry().center().x()
        assert reminder.card.y() < reminder.character.y()
        sizes.append((reminder.character.height(), reminder.card.width(), reminder.heading.font().pixelSize()))
        for widget in (reminder.close_button, reminder.water_button, reminder.kegel_button,
                       reminder.snooze_button, reminder.history_button):
            assert reminder.card.rect().contains(widget.geometry())
            assert widget.fontMetrics().horizontalAdvance(widget.text()) <= widget.width()
        assert reminder.heading.fontMetrics().horizontalAdvance(reminder.heading.text()) <= reminder.heading.width()
    assert all(sizes[0][i] < sizes[1][i] < sizes[2][i] for i in range(3))
    for character, bubble, font in sizes:
        assert bubble / character == pytest.approx(274 / 280, abs=.01)
        assert font / character == pytest.approx(18 / 280, abs=.005)


def test_both_actions_are_independent_and_not_counted_by_dismiss(reminder, application):
    completed = []
    dismissed = []
    reminder.completed.connect(completed.append)
    reminder.dismissed.connect(lambda: dismissed.append(True))
    reminder.begin({})
    application.processEvents()
    QTest.mouseClick(reminder.water_button, Qt.MouseButton.LeftButton)
    reminder.set_records({"water": 7})
    assert reminder.water_button.isChecked() and not reminder.kegel_button.isChecked()
    QTest.mouseClick(reminder.kegel_button, Qt.MouseButton.LeftButton)
    reminder.set_records({"water": 7, "kegel": 8})
    assert reminder.water_button.isChecked() and reminder.kegel_button.isChecked()
    reminder.close()
    assert not reminder.isVisible()
    assert dismissed == [True]
    assert completed == ["water", "kegel"]


def test_missing_monitor_and_offscreen_position_recovers(reminder, application):
    reminder.apply_settings(replace(reminder.settings, position_x=90000, position_y=-90000, screen_name="removed-monitor"))
    reminder.place()
    screen = QApplication.screenAt(reminder.frameGeometry().center())
    assert screen is not None
    assert screen.availableGeometry().contains(reminder.geometry())


def test_real_generated_frames_and_reduced_motion(reminder, application):
    assert set(reminder.character.frames) == {"idle", "wave", "water", "stretch"}
    for frames, durations in reminder.character.frames.values():
        assert len(frames) == len(durations)
        assert all(not frame.isNull() for frame in frames)
        assert all(duration > 0 for duration in durations)
    reminder.begin({})
    application.processEvents()
    assert reminder.character.timer.isActive()
    reminder.character.set_reduced_motion(True)
    assert not reminder.character.timer.isActive()


def test_resizing_preserves_random_character(reminder, application):
    reminder.begin({}, "qwen")
    reminder.apply_settings(replace(reminder.settings, pet_height=320))
    assert reminder.character.character == "qwen"


def test_bubble_never_covers_any_character_action_at_all_sizes(reminder, application):
    assets = Path(__file__).resolve().parents[1] / "assets/v2"
    for height in (180, 280, 480):
        reminder.apply_settings(replace(reminder.settings, pet_height=height))
        application.processEvents()
        bubble = Image.open(assets / "bubble.png").getchannel("A").transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        bubble = bubble.resize((reminder.card.width(), reminder.card.height()), Image.Resampling.LANCZOS)
        bubble_mask = Image.new("L", (reminder.width(), reminder.height()))
        bubble_mask.paste(bubble, (reminder.card.x(), reminder.card.y()))
        bubble_mask = bubble_mask.point(lambda value: 255 if value > 32 else 0)
        for frame in (assets / "characters").glob("*/*/*.png"):
            character = Image.open(frame).getchannel("A")
            character.thumbnail((reminder.character.width(), reminder.character.height()), Image.Resampling.LANCZOS)
            mask = Image.new("L", bubble_mask.size)
            x = reminder.character.x() + (reminder.character.width() - character.width) // 2
            y = reminder.character.y() + reminder.character.height() - character.height
            mask.paste(character, (x, y))
            mask = mask.point(lambda value: 255 if value > 32 else 0)
            assert ImageChops.multiply(bubble_mask, mask).getbbox() is None, (height, str(frame))
