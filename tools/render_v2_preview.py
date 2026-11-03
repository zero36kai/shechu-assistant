"""导出真实控件与 API 帧的离屏预览，不作为实机操作证据。"""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from water_assistant.config import Settings
from water_assistant.ui import ReminderWindow


ROOT = Path(__file__).resolve().parents[1]


def main():
    application = QApplication([])
    # Qt offscreen 不自动枚举 Windows 字体；显式载入后才能正确导出中文。
    for font in Path("C:/Windows/Fonts").glob("msyh*.ttc"):
        QFontDatabase.addApplicationFont(str(font))
    window = ReminderWindow(Settings(auto_hide_seconds=0), ROOT / "assets/v2")
    window.begin({})
    application.processEvents()
    window.character.timer.stop()
    window.return_idle.stop()
    images, delays = [], []
    for state, records, message in (
        ("wave", {}, "来陪你喝口水"),
        ("idle", {}, "两项可以分别打卡"),
        ("water", {"water": 1}, "喝水已记录"),
        ("idle", {"water": 1}, "另一项可以随后完成"),
        ("stretch", {"water": 1, "kegel": 2}, "两项已保存，点记录收起"),
    ):
        window.set_records(records)
        window.feedback.setText(message)
        window.character.set_state(state)
        elapsed = 0
        for duration in window.character.frames[state][1]:
            with patch("water_assistant.animation.time.monotonic",
                       return_value=window.character.started + (elapsed + 1) / 1000):
                window.repaint()
                data = QBuffer()
                data.open(QIODevice.OpenModeFlag.WriteOnly)
                window.grab().save(data, "PNG")
                images.append(Image.open(BytesIO(bytes(data.data()))).convert("RGBA"))
            delays.append(duration)
            elapsed += duration
    output = ROOT / "docs/evidence"
    output.mkdir(parents=True, exist_ok=True)
    images[0].save(output / "V2提醒动作预览.webp", save_all=True,
                   append_images=images[1:], duration=delays, loop=0, lossless=True)
    window.set_records({})
    window.feedback.setText("两项可以分别打卡")
    window.character.set_state("idle")
    window.character.set_reduced_motion(True)
    window.grab().save(str(output / "V2提醒-280.png"))
    window.apply_settings(replace(window.settings, pet_height=180))
    application.processEvents()
    window.grab().save(str(output / "V2提醒-180.png"))
    window.hide()
    print(f"离屏导出 {len(images)} 帧，{sum(delays)}ms；尺寸472×398与303×256")


if __name__ == "__main__":
    main()
