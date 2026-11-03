"""独立于界面的60秒保活；主动退出后停止，异常退出后重新拉起V2。"""
import argparse
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import QCoreApplication, QLockFile

from .app import ROOT, send_command, server_name
from .config import atomic_json


class Heartbeat:
    def __init__(self, data_dir: Path, *, isolated=False, interval_seconds=60):
        self.data_dir = data_dir
        self.isolated = isolated
        self.interval_seconds = interval_seconds
        self.child = None

    def check(self, show=False):
        name = server_name(self.data_dir)
        if send_command(name, "ping"):
            if show:
                send_command(name, "show")
            return "healthy"
        # 不与正在启动或暂未响应的现有实例竞争，也不强杀用户窗口。
        lock = QLockFile(str(self.data_dir / "instance.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            logging.warning("V2未回应心跳，现有实例仍持锁，下轮重试")
            return "unresponsive"
        lock.unlock()
        entry = ([sys.executable] if getattr(sys, "frozen", False) else
                 [str(ROOT / ".venv/Scripts/pythonw.exe"), "-B", str(ROOT / "run_v2.py")])
        command = entry + ["--data-dir", str(self.data_dir)]
        if self.isolated:
            command.append("--isolated")
        if show:
            command.append("--show")
        if self.child is not None:
            self.child.poll()
        self.child = subprocess.Popen(command, cwd=ROOT)
        logging.info("V2已拉起 launcher_pid=%s", self.child.pid)
        return "starting"

    def save_status(self, state):
        atomic_json(self.data_dir / "heartbeat.json", {
            "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "heartbeat_pid": os.getpid(), "state": state, "interval_seconds": self.interval_seconds,
        })


def main(argv=None, *, interval_seconds=60):
    parser = argparse.ArgumentParser(description="社畜小助手心跳保活")
    parser.add_argument("--heartbeat", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args(argv)
    args.data_dir = args.data_dir.resolve()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    application = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    stop = args.data_dir / "heartbeat.stop"
    # 显式启动或下次登录重新启用保活；运行中的正常退出不被复活。
    stop.unlink(missing_ok=True)
    heartbeat = Heartbeat(args.data_dir, isolated=args.isolated, interval_seconds=interval_seconds)
    lock = QLockFile(str(args.data_dir / "heartbeat.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(300):
        heartbeat.check(show=args.show)
        return 0
    handler = RotatingFileHandler(args.data_dir / "heartbeat.log", maxBytes=100_000,
                                  backupCount=1, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[handler])
    logging.info("V2心跳启动 interval=%s", interval_seconds)
    first = True
    try:
        while not stop.exists():
            try:
                state = heartbeat.check(show=first and args.show)
                heartbeat.save_status(state)
            except OSError:
                logging.exception("心跳检查失败，下轮重试")
            first = False
            # 每秒检查主动退出标记，心跳探测维持60秒一次。
            deadline = time.monotonic() + interval_seconds
            while not stop.exists() and time.monotonic() < deadline:
                time.sleep(min(1, max(0, deadline - time.monotonic())))
        heartbeat.save_status("stopped")
        logging.info("V2心跳已按用户退出停止")
    finally:
        lock.unlock()
    return 0
