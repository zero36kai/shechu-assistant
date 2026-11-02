"""真实隔离进程验证：重复保活、防重、崩溃重启与主动退出停止。"""
from datetime import datetime
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

from PySide6.QtCore import QCoreApplication, QLockFile

from water_assistant.app import ROOT, send_command, server_name
from water_assistant.store import HistoryStore


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.1)
    raise AssertionError("隔离心跳验收等待超时")


def main():
    folder = Path(sys.argv[1]).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    app = QCoreApplication([])
    store = HistoryStore(folder / "history.sqlite3")
    store.complete("persisted-before-crash", "water", datetime.now().astimezone())
    store.close()
    code = "from water_assistant.heartbeat import main; raise SystemExit(main(interval_seconds=1))"
    command = [sys.executable, "-B", "-c", code, "--heartbeat", "--data-dir", str(folder), "--isolated"]
    processes = [subprocess.Popen(command, cwd=ROOT) for _ in range(2)]
    name = server_name(folder)
    try:
        wait_for(lambda: send_command(name, "ping"))
        wait_for(lambda: sum(p.poll() is None for p in processes) == 1)
        old_pid = QLockFile(str(folder / "instance.lock")).getLockInfo()[0]
        assert old_pid > 0
        started = time.monotonic()
        os.kill(old_pid, signal.SIGTERM)
        def restarted():
            info = QLockFile(str(folder / "instance.lock")).getLockInfo()
            return info[0] if info[0] > 0 and info[0] != old_pid and send_command(name, "ping") else None
        new_pid = wait_for(restarted)
        recovery = round(time.monotonic() - started, 2)
        assert send_command(name, "quit")
        for process in processes:
            process.wait(timeout=15)
        time.sleep(2)
        assert not send_command(name, "ping")
        status = json.loads((folder / "heartbeat.json").read_text(encoding="utf-8"))
        assert status["state"] == "stopped"
        with sqlite3.connect(folder / "history.sqlite3") as db:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            assert db.execute("SELECT COUNT(*) FROM completions").fetchone()[0] == 1
            assert integrity == "ok"
        messages = (folder / "assistant.log").read_text(encoding="utf-8")
        assert messages.count("V2 started") == 2
        assert "reminder_shown" not in messages
        result = dict(test_interval_seconds=1, production_interval_seconds=60,
                      heartbeat_instances=1, app_pid_before_crash=old_pid,
                      app_pid_after_recovery=new_pid, crash_recovery_seconds=recovery,
                      explicit_quit_stops_heartbeat=True, exit_codes=[p.returncode for p in processes],
                      persisted_rows=1, integrity_check=integrity, unwanted_reminder_count=0)
        output = ROOT / "docs/evidence/V2心跳进程验收.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        send_command(name, "quit")
        (folder / "heartbeat.stop").touch()
        for process in processes:
            if process.poll() is None:
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
