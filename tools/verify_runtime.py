"""在全新隔离目录验证真实 Qt 进程、并发启动和 IPC，不写生产数据。"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = Path(sys.argv[1]).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    command = [str(ROOT / ".venv/Scripts/pythonw.exe"), "-B", str(ROOT / "run_v2.py"),
               "--data-dir", str(folder), "--isolated"]
    processes = [subprocess.Popen(command, cwd=ROOT) for _ in range(2)]
    try:
        log = folder / "assistant.log"
        deadline = time.monotonic() + 12
        while not log.exists() or "V2 started" not in log.read_text(encoding="utf-8"):
            if time.monotonic() > deadline:
                raise RuntimeError("隔离实例未按时启动")
            time.sleep(.1)
        time.sleep(.5)
        survivors = [p for p in processes if p.poll() is None]
        assert len(survivors) == 1, "冷启动竞争产生了多个实例"
        exits = []
        for _ in range(3):
            result = subprocess.run(command + ["--command", "remind"], cwd=ROOT, timeout=12)
            assert result.returncode == 0
            exits.append(result.returncode)
        subprocess.run(command + ["--command", "close"], cwd=ROOT, check=True, timeout=12)
        subprocess.run(command + ["--command", "quit"], cwd=ROOT, check=True, timeout=12)
        for process in processes:
            process.wait(timeout=12)
        messages = log.read_text(encoding="utf-8")
        assert messages.count("V2 started") == 1
        assert messages.count("reminder_shown") == 1
        assert "reminder_dismissed" in messages
        assert "ERROR" not in messages
        with sqlite3.connect(folder / "history.sqlite3") as db:
            rows = db.execute("SELECT COUNT(*) FROM completions").fetchone()[0]
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        assert rows == 0 and integrity == "ok"
        report = dict(cold_start_processes=2, surviving_instances=1,
                      cold_start_exit_codes=[p.returncode for p in processes],
                      duplicate_ipc_exit_codes=exits, started_log_count=1,
                      repeated_remind_log_count=1, close_then_quit=True,
                      completion_rows=rows, integrity_check=integrity)
        output = ROOT / "docs/evidence/运行进程验收.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    finally:
        for process in processes:
            if process.poll() is None:
                subprocess.run(command + ["--command", "quit"], cwd=ROOT, timeout=12)
                process.wait(timeout=12)


if __name__ == "__main__":
    main()
