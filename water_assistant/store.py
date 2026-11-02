from datetime import datetime
import json
from pathlib import Path
import sqlite3


KINDS = ("water", "kegel")


class HistoryStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, timeout=0.25)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS completions (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('water','kegel')),
                occurred_at TEXT NOT NULL,
                local_day TEXT NOT NULL,
                undone_at TEXT
            );
            CREATE INDEX IF NOT EXISTS completions_day ON completions(local_day);
            CREATE TABLE IF NOT EXISTS legacy_totals (
                local_day TEXT PRIMARY KEY,
                water INTEGER NOT NULL CHECK(water >= 0),
                kegel INTEGER NOT NULL CHECK(kegel >= 0),
                imported_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        # 旧 V2 的整表唯一约束会迫使重做覆盖撤销记录；原行原样迁移。
        old_unique = any(
            index["origin"] == "u" and
            [column["name"] for column in self.db.execute(
                'PRAGMA index_info("' + index["name"].replace('"', '""') + '")'
            )] == ["session_id", "kind"]
            for index in self.db.execute("PRAGMA index_list(completions)")
        )
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if old_unique:
                self.db.execute("""CREATE TABLE completions_v2 (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('water','kegel')),
                    occurred_at TEXT NOT NULL,
                    local_day TEXT NOT NULL,
                    undone_at TEXT
                )""")
                self.db.execute("INSERT INTO completions_v2 SELECT * FROM completions")
                self.db.execute("DROP TABLE completions")
                self.db.execute("ALTER TABLE completions_v2 RENAME TO completions")
            self.db.execute("CREATE INDEX IF NOT EXISTS completions_day ON completions(local_day)")
            self.db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS completions_active
                ON completions(session_id, kind) WHERE undone_at IS NULL""")

    def complete(self, session_id: str, kind: str, at: datetime):
        if kind not in KINDS or not session_id:
            raise ValueError("无效的打卡")
        stamp, day = at.isoformat(timespec="seconds"), at.date().isoformat()
        with self.db:
            row = self.db.execute(
                "SELECT id FROM completions WHERE session_id=? AND kind=? AND undone_at IS NULL",
                (session_id, kind),
            ).fetchone()
            if row:
                return row["id"], False
            cursor = self.db.execute(
                "INSERT INTO completions(session_id,kind,occurred_at,local_day) VALUES(?,?,?,?)",
                (session_id, kind, stamp, day),
            )
            return cursor.lastrowid, True

    def undo(self, event_id: int, at: datetime):
        with self.db:
            cursor = self.db.execute(
                "UPDATE completions SET undone_at=? WHERE id=? AND undone_at IS NULL",
                (at.isoformat(timespec="seconds"), event_id),
            )
        return cursor.rowcount == 1

    def session_records(self, session_id: str):
        return {row["kind"]: row["id"] for row in self.db.execute(
            "SELECT id,kind FROM completions WHERE session_id=? AND undone_at IS NULL",
            (session_id,),
        )}

    def day_records(self, day: str):
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM completions WHERE local_day=? ORDER BY occurred_at DESC,id DESC", (day,)
        )]

    def totals(self, day: str):
        totals = {"water": 0, "kegel": 0, "legacy_water": 0, "legacy_kegel": 0}
        for row in self.db.execute(
            "SELECT kind,COUNT(*) AS n FROM completions WHERE local_day=? AND undone_at IS NULL GROUP BY kind",
            (day,),
        ):
            totals[row["kind"]] = row["n"]
        legacy = self.db.execute("SELECT * FROM legacy_totals WHERE local_day=?", (day,)).fetchone()
        if legacy:
            for kind in KINDS:
                totals[kind] += legacy[kind]
                totals["legacy_" + kind] = legacy[kind]
        return totals

    def days(self):
        return [row[0] for row in self.db.execute(
            "SELECT local_day FROM completions UNION SELECT local_day FROM legacy_totals ORDER BY local_day DESC"
        )]

    def import_legacy(self, path: Path):
        if self.db.execute("SELECT 1 FROM metadata WHERE key='legacy_import'").fetchone():
            return False
        if not path.exists():
            return False
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("旧版数据格式无效")
        if not isinstance(raw.get("date"), str):
            raise ValueError("旧版日期无效")
        day = datetime.strptime(raw["date"], "%Y-%m-%d").date().isoformat()
        water, kegel = raw.get("water", 0), raw.get("kegel", 0)
        if any(type(n) is not int or not 0 <= n <= 2**63 - 1 for n in (water, kegel)):
            raise ValueError("旧版计数无效")
        with self.db:
            self.db.execute(
                "INSERT INTO legacy_totals VALUES(?,?,?,?)",
                (day, water, kegel, datetime.now().astimezone().isoformat(timespec="seconds")),
            )
            self.db.execute("INSERT INTO metadata VALUES('legacy_import',?)", (str(path),))
        return True

    def close(self):
        self.db.close()
