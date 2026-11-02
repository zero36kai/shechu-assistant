from datetime import datetime, timezone, timedelta
import json
import sqlite3

import pytest

from water_assistant.store import HistoryStore


TZ = timezone(timedelta(hours=8))


@pytest.fixture
def store(tmp_path):
    value = HistoryStore(tmp_path / "history.sqlite3")
    yield value
    value.close()


def test_two_independent_completions_and_duplicate_click(store):
    now = datetime(2026, 11, 2, 10, tzinfo=TZ)
    first_id, changed = store.complete("one", "water", now)
    assert changed
    assert store.totals("2026-11-02")["kegel"] == 0
    assert store.complete("one", "water", now) == (first_id, False)
    store.complete("one", "kegel", now)
    assert store.totals("2026-11-02")["water"] == 1
    assert store.totals("2026-11-02")["kegel"] == 1


def test_midnight_uses_each_click_date_and_survives_restart(tmp_path):
    path = tmp_path / "history.sqlite3"
    store = HistoryStore(path)
    store.complete("one", "water", datetime(2026, 11, 2, 23, 59, tzinfo=TZ))
    store.complete("one", "kegel", datetime(2026, 11, 3, 0, 1, tzinfo=TZ))
    store.close()
    store = HistoryStore(path)
    assert store.totals("2026-11-02")["water"] == 1
    assert store.totals("2026-11-02")["kegel"] == 0
    assert store.totals("2026-11-03")["water"] == 0
    assert store.totals("2026-11-03")["kegel"] == 1
    store.close()


def test_undo_is_retained_and_redo_is_exactly_once(store):
    now = datetime(2026, 11, 2, 10, tzinfo=TZ)
    event_id, _ = store.complete("one", "water", now)
    assert store.undo(event_id, now)
    assert not store.undo(event_id, now)
    assert store.totals("2026-11-02")["water"] == 0
    assert store.day_records("2026-11-02")[0]["undone_at"]
    new_id, changed = store.complete("one", "water", now)
    assert changed and new_id != event_id
    assert len(store.day_records("2026-11-02")) == 2
    assert store.complete("one", "water", now) == (new_id, False)
    assert store.totals("2026-11-02")["water"] == 1


def test_legacy_import_does_not_invent_timestamps(store, tmp_path):
    old = tmp_path / "data.json"
    original = json.dumps({"date": "2026-11-02", "water": 6, "kegel": 2})
    old.write_text(original, encoding="utf-8")
    assert store.import_legacy(old)
    assert not store.import_legacy(old)
    assert store.day_records("2026-11-02") == []
    assert store.totals("2026-11-02") == {
        "water": 6, "kegel": 2, "legacy_water": 6, "legacy_kegel": 2
    }
    assert old.read_text(encoding="utf-8") == original


def test_failed_write_is_not_reported_as_saved(store):
    store.db.execute("PRAGMA query_only=ON")
    with pytest.raises(sqlite3.OperationalError):
        store.complete("one", "water", datetime.now(TZ))
    assert store.session_records("one") == {}


def test_other_reader_independently_reconciles_totals(store):
    now = datetime(2026, 11, 2, 10, tzinfo=TZ)
    for i in range(5):
        store.complete(str(i), "water", now)
    event_id, _ = store.complete("k", "kegel", now)
    store.undo(event_id, now)
    with sqlite3.connect(store.path) as reader:
        assert reader.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert reader.execute("SELECT COUNT(*) FROM completions WHERE undone_at IS NULL").fetchone()[0] == 5
