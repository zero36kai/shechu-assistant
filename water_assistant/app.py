import argparse
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import logging
import random
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sqlite3
import sys

from PySide6.QtCore import QLockFile, QObject, Qt, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .config import CHARACTERS, Settings
from .core import ReminderCycle
from .platform import WorkdayCalendar, desktop_locked, foreground_fullscreen, idle_seconds
from .store import HistoryStore
from .ui import Dashboard, ReminderWindow, app_icon


ROOT = Path(__file__).resolve().parent.parent


class Controller(QObject):
    def __init__(self, application, data_dir: Path, *, isolated=False):
        super().__init__()
        self.application = application
        self.data_dir = data_dir
        self.settings_path = data_dir / "settings.json"
        self.settings, warning = Settings.load(self.settings_path, None if isolated else ROOT / "config.json")
        self.store = HistoryStore(data_dir / "history.sqlite3")
        if not isolated:
            try:
                self.store.import_legacy(ROOT / "data.json")
            except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                warning = "旧数据暂未导入，原文件保留：" + str(exc)
                logging.exception("旧数据导入失败")
        self.cycle = ReminderCycle(self.settings)
        self.character_pool = []
        self.character_session = None
        self.active_character = self.settings.character
        self.calendar = WorkdayCalendar(data_dir / "workdays.json", None if isolated else ROOT / "holiday_cache.json")
        self.window = ReminderWindow(self.settings, ROOT / "assets" / "v2")
        self.dashboard = Dashboard(self.settings, ROOT / "assets" / "v2", self.store)
        self.window.dismissed.connect(self.dismiss)
        self.window.snoozed.connect(self.snooze)
        self.window.completed.connect(self.complete)
        self.window.history_requested.connect(lambda: self.show_dashboard(1))
        self.window.geometry_saved.connect(self.save_position)
        self.window.height_changed.connect(lambda value: self.update_settings(replace(self.settings, pet_height=value)))
        self.window.interacted.connect(self.cycle.interact)
        self.dashboard.reminder_requested.connect(lambda: self.show_reminder(manual=True))
        self.dashboard.pause_requested.connect(self.toggle_pause)
        self.dashboard.settings_saved.connect(self.update_settings)
        self.dashboard.character_selected.connect(self.preview_character)
        self.dashboard.undo_requested.connect(self.undo)
        self.dashboard.close_reminders_requested.connect(self.dismiss)
        self.dashboard.reset_position_requested.connect(self.reset_position)
        self.dashboard.apply_settings(self.settings)
        self.dashboard.home_error.setText(warning)
        self.menu = QMenu()
        self.menu.addAction("社畜小助手", self.show_dashboard)
        self.menu.addAction("显示提醒 / 打卡", lambda: self.show_reminder(manual=True))
        self.menu.addAction("历史记录", lambda: self.show_dashboard(1))
        self.menu.addAction("角色与外观", lambda: self.show_dashboard(2))
        self.menu.addSeparator()
        self.pause_action = self.menu.addAction("暂停提醒", self.toggle_pause)
        self.menu.addAction("关闭全部提醒", self.dismiss)
        self.menu.addSeparator()
        self.menu.addAction("退出", self.quit)
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("社畜小助手")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        self.last_reason = ""
        self.refresh_counter = 0
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.refresh()
        application.aboutToQuit.connect(self.shutdown)

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_dashboard()

    def eligibility(self):
        now = datetime.now().astimezone()
        if desktop_locked():
            return False, "锁屏中，暂停计时"
        if not self.settings.start_hour <= now.hour < self.settings.end_hour:
            return False, "当前不在提醒时段"
        if not self.calendar.is_workday(now.date(), self.settings.smart_workday, self.settings.workdays_only):
            return False, "今天休息，暂停提醒"
        if idle_seconds() >= self.settings.idle_skip_minutes * 60:
            return False, "离开电脑，暂停计时"
        if not self.window.isVisible() and foreground_fullscreen():
            return False, "全屏使用中，暂停提醒"
        return True, ""

    def tick(self):
        try:
            eligible, reason = self.eligibility()
            if reason != self.last_reason:
                logging.info("reminder_eligibility eligible=%s reason=%s remaining_seconds=%.0f",
                             eligible, reason or "ready", self.cycle.remaining)
            self.last_reason = reason
            action = self.cycle.tick(eligible)
            if action == "show":
                self.display_cycle()
            elif action == "hide":
                self.window.hide()
                logging.info("reminder_hidden reason=%s", self.last_reason or "auto_hide")
            self.refresh_counter += 1
            if action or self.refresh_counter % 10 == 0:
                self.refresh()
        except Exception:
            logging.exception("提醒调度异常")
            self.dashboard.home_error.setText("调度出现异常，已保留日志。关闭提醒和退出仍可使用。")

    def display_cycle(self):
        if self.character_session != self.cycle.session_id:
            if not self.character_pool:
                self.character_pool = random.sample(tuple(CHARACTERS), len(CHARACTERS))
            self.active_character = self.character_pool.pop()
            self.character_session = self.cycle.session_id
        try:
            records = self.store.session_records(self.cycle.session_id)
        except (sqlite3.Error, OSError):
            logging.exception("读取本次记录失败")
            records = {}
        self.window.begin(records, self.active_character)
        self.dashboard.show_character(self.active_character)
        logging.info("reminder_shown session=%s manual=%s", self.cycle.session_id, self.cycle.manual)

    def show_reminder(self, manual=False):
        if self.cycle.show(manual=manual):
            self.display_cycle()
        elif not self.window.isVisible() or self.window.isMinimized():
            self.display_cycle()
        self.refresh()

    def dismiss(self):
        # 关闭先于任何可能失败的文件操作和界面刷新。
        self.window.hide()
        self.cycle.dismiss()
        logging.info("reminder_dismissed")
        self.refresh()

    def snooze(self):
        self.window.hide()
        self.cycle.snooze()
        logging.info("reminder_snoozed")
        self.refresh()

    def toggle_pause(self):
        self.window.hide()
        self.cycle.set_paused(not self.cycle.paused)
        self.pause_action.setText("恢复提醒" if self.cycle.paused else "暂停提醒")
        self.refresh()

    def complete(self, kind):
        if not self.cycle.visible or self.cycle.session_id is None:
            return
        self.cycle.interact()
        previous = dict(self.window.records)
        records = dict(previous)
        try:
            now = datetime.now().astimezone()
            if kind in previous:
                self.store.undo(previous[kind], now)
                records.pop(kind)
                message = "已撤销这一次记录。"
                state = "idle"
            else:
                event_id, _ = self.store.complete(self.cycle.session_id, kind, now)
                records[kind] = event_id
                message = "喝水已记录，还可以做另一项。" if kind == "water" else "提肛已记录，还可以做另一项。"
                state = "water" if kind == "water" else "stretch"
            self.window.set_records(records)
            if len(records) == 2:
                message = "已分别保存，可随时关闭。"
            self.window.show_feedback(message, state)
            logging.info("completion_changed session=%s kind=%s", self.cycle.session_id, kind)
        except (sqlite3.Error, OSError) as exc:
            logging.exception("打卡保存失败")
            self.window.set_records(previous)
            self.window.show_feedback("未保存，请重试。仍可关闭。", error=True)
        self.refresh()

    def undo(self, event_id):
        try:
            self.store.undo(event_id, datetime.now().astimezone())
            self.window.set_records({kind: saved_id for kind, saved_id in self.window.records.items()
                                     if saved_id != event_id})
            self.refresh()
        except (sqlite3.Error, OSError):
            logging.exception("撤销记录失败")
            self.dashboard.history_note.setText("撤销未保存，请稍后重试。")

    def update_settings(self, settings):
        try:
            settings.save(self.settings_path)
        except (OSError, ValueError) as exc:
            logging.exception("保存设置失败")
            self.dashboard.settings_notice.setText("未保存：" + str(exc))
            self.dashboard.home_error.setText("设置未保存，仍使用之前的设置。")
            self.window.show_feedback("设置未保存，仍可关闭。", error=True)
            self.dashboard.apply_settings(self.settings)
            return False
        interval_changed = settings.interval_minutes != self.settings.interval_minutes
        self.settings = settings
        self.cycle.settings = settings
        if interval_changed and not self.cycle.visible and not self.cycle.snoozed:
            self.cycle.remaining = settings.interval_minutes * 60
        self.window.apply_settings(settings)
        self.dashboard.apply_settings(settings)
        self.dashboard.settings_notice.setText("已保存")
        self.refresh()
        return True

    def save_position(self, x, y, screen_name):
        self.update_settings(replace(self.settings, position_x=x, position_y=y, screen_name=screen_name))

    def preview_character(self, character):
        if self.update_settings(replace(self.settings, character=character)):
            self.active_character = character
            self.window.current_character = character
            self.window.character.set_character(character)
            self.dashboard.show_character(character)

    def reset_position(self):
        if self.update_settings(replace(self.settings, position_x=None, position_y=None, screen_name="")):
            self.window.place()
            self.show_reminder(manual=True)

    def show_dashboard(self, page=0):
        self.dashboard.go(page if type(page) is int else 0)
        self.refresh()
        self.dashboard.setWindowState(self.dashboard.windowState() & ~Qt.WindowState.WindowMinimized)
        self.dashboard.show()
        self.dashboard.raise_()
        self.dashboard.activateWindow()

    def refresh(self):
        try:
            self.dashboard.refresh(self.cycle, self.last_reason)
            totals = self.store.totals(datetime.now().date().isoformat())
            self.tray.setToolTip(f"社畜小助手 · 喝水 {totals['water']} 次 · 提肛 {totals['kegel']} 次")
        except (sqlite3.Error, OSError):
            logging.exception("刷新记录失败")
            self.dashboard.home_error.setText("记录暂时无法读取，关闭和退出仍可使用。")

    def command(self, command):
        if command == "quit":
            self.quit()
        elif command == "close":
            self.dismiss()
        elif command == "remind":
            self.show_reminder(manual=True)
        else:
            self.show_dashboard()

    def quit(self):
        try:
            (self.data_dir / "heartbeat.stop").write_text("user quit", encoding="utf-8")
        except OSError:
            logging.exception("停止心跳标记保存失败")
        self.window.hide()
        self.dashboard.hide()
        self.application.quit()

    def shutdown(self):
        self.timer.stop()
        self.tray.hide()
        self.window.hide()
        try:
            self.store.close()
        except (sqlite3.Error, OSError):
            logging.exception("退出时关闭数据库失败")


def server_name(data_dir):
    return "water-assistant-v2-" + hashlib.sha256(str(data_dir.resolve()).lower().encode()).hexdigest()[:20]


def send_command(name, command):
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(400):
        return False
    socket.write(command.encode("ascii"))
    socket.waitForBytesWritten(400)
    if command == "ping":
        ready = socket.bytesAvailable() or socket.waitForReadyRead(1500)
        result = bool(ready) and bytes(socket.readAll()) == b"pong"
        socket.disconnectFromServer()
        return result
    socket.disconnectFromServer()
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="社畜小助手")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--remind", action="store_true")
    parser.add_argument("--command", choices=("show", "remind", "close", "quit", "ping"))
    parser.add_argument("--isolated", action="store_true", help="不导入旧版数据，用于独立验收")
    args = parser.parse_args(argv)
    args.data_dir = args.data_dir.resolve()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName("WaterAssistantV2")
    application.setQuitOnLastWindowClosed(False)
    application.setWindowIcon(app_icon())
    name = server_name(args.data_dir)
    command = args.command or ("remind" if args.remind else "show" if args.show else "ping")
    if send_command(name, command):
        return 0
    if args.command == "ping":
        return 1
    if args.command in ("close", "quit"):
        return 0
    lock = QLockFile(str(args.data_dir / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(300):
        return 1
    handler = RotatingFileHandler(args.data_dir / "assistant.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[handler])
    controller = Controller(application, args.data_dir, isolated=args.isolated)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    QLocalServer.removeServer(name)
    if not server.listen(name):
        controller.shutdown()
        lock.unlock()
        return 1

    def accept():
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            def receive(socket=connection):
                payload = bytes(socket.readAll())[:32].decode("ascii", errors="ignore")
                if payload == "ping":
                    socket.write(b"pong")
                    socket.flush()
                else:
                    controller.command(payload)
                socket.disconnectFromServer()
            connection.readyRead.connect(receive)
            connection.disconnected.connect(connection.deleteLater)
            if connection.bytesAvailable():
                receive()

    server.newConnection.connect(accept)
    if args.show or args.command == "show" or not QSystemTrayIcon.isSystemTrayAvailable():
        controller.show_dashboard()
    if args.remind or args.command == "remind":
        controller.show_reminder(manual=True)
    logging.info("V2 started isolated=%s", args.isolated)
    result = application.exec()
    server.close()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
