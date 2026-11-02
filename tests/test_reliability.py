from datetime import date, datetime, timedelta, timezone
import json
import sqlite3

import pytest

from water_assistant.config import Settings
from water_assistant.core import ReminderCycle
from water_assistant.platform import WorkdayCalendar
from water_assistant.store import HistoryStore


TZ = timezone(timedelta(hours=8))


@pytest.fixture
def store(tmp_path):
    value = HistoryStore(tmp_path / "history.sqlite3")
    try:
        yield value
    finally:
        value.close()


@pytest.mark.parametrize("paused", [False, True])
def test_manual_snooze_obeys_automatic_eligibility(paused):
    now = [0.0]
    cycle = ReminderCycle(Settings(snooze_minutes=1), lambda: now[0])
    cycle.set_paused(paused)
    assert cycle.show(manual=True)
    session = cycle.session_id
    cycle.snooze()
    for second in range(1, 121):
        now[0] = second
        assert cycle.tick(eligible=paused) is None
    assert not cycle.visible
    assert cycle.session_id == session
    assert cycle.remaining == 60


def test_sleep_does_not_leave_ineligible_automatic_window_visible():
    now = [0.0]
    cycle = ReminderCycle(Settings(), lambda: now[0])
    cycle.show()
    now[0] = 8 * 3600
    assert cycle.tick(eligible=False) == "hide"
    assert not cycle.visible


def test_redo_preserves_original_day_and_undo_evidence(store):
    first = datetime(2026, 11, 2, 23, 59, 59, tzinfo=TZ)
    undone = first + timedelta(seconds=2)
    redone = first + timedelta(minutes=3)
    old_id, _ = store.complete("same-round", "water", first)
    assert store.undo(old_id, undone)
    new_id, changed = store.complete("same-round", "water", redone)
    assert changed and new_id != old_id
    assert store.complete("same-round", "water", redone) == (new_id, False)
    old_rows = store.day_records("2026-11-02")
    assert len(old_rows) == 1
    assert old_rows[0]["occurred_at"] == first.isoformat(timespec="seconds")
    assert old_rows[0]["undone_at"] == undone.isoformat(timespec="seconds")
    assert store.totals("2026-11-02")["water"] == 0
    assert store.totals("2026-11-03")["water"] == 1
    assert not store.undo(old_id, redone)
    assert store.session_records("same-round") == {"water": new_id}


@pytest.mark.parametrize("payload", [
    {"date": None, "water": 1},
    {"date": [2026, 11, 2], "water": 1},
    {"date": "2026-11-02", "water": 2**63},
])
def test_invalid_legacy_is_rejected_without_partial_import(store, tmp_path, payload):
    source = tmp_path / "legacy.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        store.import_legacy(source)
    assert store.db.execute("SELECT COUNT(*) FROM legacy_totals").fetchone()[0] == 0
    assert store.db.execute("SELECT COUNT(*) FROM metadata").fetchone()[0] == 0


def test_disabling_workdays_ignores_cached_holiday_without_network(tmp_path, monkeypatch):
    calendar = WorkdayCalendar(tmp_path / "workdays.json")
    holiday = date(2026, 11, 1)
    calendar.cache[holiday.isoformat()] = False
    monkeypatch.setattr(calendar, "_fetch", lambda _: pytest.fail("不应联网"))
    assert calendar.is_workday(holiday, smart=True, weekdays_only=False)
    assert calendar.requested == set()


def test_database_lock_rolls_back_failed_completion_and_undo(store):
    at = datetime(2026, 11, 2, 10, tzinfo=TZ)
    event_id, _ = store.complete("round", "water", at)
    other = sqlite3.connect(store.path)
    try:
        other.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            store.complete("round", "kegel", at)
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            store.undo(event_id, at)
        assert not store.db.in_transaction
        assert store.session_records("round") == {"water": event_id}
    finally:
        other.close()
    assert store.complete("round", "kegel", at)[1]


def test_old_v2_schema_migration_preserves_ids_dates_and_undo(tmp_path):
    path = tmp_path / "old-v2.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE completions (
            id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('water','kegel')),
            occurred_at TEXT NOT NULL, local_day TEXT NOT NULL, undone_at TEXT,
            UNIQUE(session_id, kind))""")
        db.executemany("INSERT INTO completions VALUES(?,?,?,?,?,?)", [
            (7, "round", "water", "2026-11-02T23:59:59+08:00", "2026-11-02", "2026-11-03T00:00:01+08:00"),
            (8, "round", "kegel", "2026-11-03T00:00:02+08:00", "2026-11-03", None),
        ])
    migrated = HistoryStore(path)
    original = migrated.day_records("2026-11-02")[0]
    assert original["id"] == 7 and original["undone_at"]
    assert migrated.session_records("round") == {"kegel": 8}
    new_id, changed = migrated.complete("round", "water", datetime(2026, 11, 3, 1, tzinfo=TZ))
    assert changed and new_id > 8
    assert migrated.day_records("2026-11-02") == [original]
    migrated.close()
    reopened = HistoryStore(path)
    assert reopened.session_records("round") == {"water": new_id, "kegel": 8}
    assert reopened.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()

