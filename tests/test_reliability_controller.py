from datetime import datetime, timedelta, timezone
from types import MethodType, SimpleNamespace
from unittest.mock import Mock
import sqlite3

import pytest

from water_assistant.app import Controller
from water_assistant.config import Settings
from water_assistant.core import ReminderCycle
from water_assistant.store import HistoryStore


@pytest.fixture
def controller(tmp_path):
    store = HistoryStore(tmp_path / "history.sqlite3")
    window = Mock()
    window.records = {}
    window.set_records.side_effect = lambda records: setattr(window, "records", dict(records))
    value = SimpleNamespace(
        store=store, window=window, cycle=ReminderCycle(Settings()),
        dashboard=Mock(), tray=Mock(), timer=Mock(), application=Mock(),
        pause_action=Mock(), last_reason="",
    )
    value.refresh = MethodType(Controller.refresh, value)
    value.cycle.show(manual=True)
    try:
        yield value
    finally:
        store.close()


def test_committed_completion_remains_confirmed_if_followup_read_fails(controller, monkeypatch):
    monkeypatch.setattr(controller.store, "session_records", Mock(side_effect=sqlite3.OperationalError("read failed")))
    Controller.complete(controller, "water")
    rows = controller.store.db.execute("SELECT id FROM completions WHERE undone_at IS NULL").fetchall()
    assert len(rows) == 1
    assert controller.window.records == {"water": rows[0][0]}
    assert controller.window.show_feedback.call_args.kwargs.get("error") is not True


def test_committed_undo_remains_confirmed_if_followup_read_fails(controller, monkeypatch):
    at = datetime(2026, 11, 2, 10, tzinfo=timezone(timedelta(hours=8)))
    event_id, _ = controller.store.complete(controller.cycle.session_id, "water", at)
    controller.window.records = {"water": event_id}
    monkeypatch.setattr(controller.store, "session_records", Mock(side_effect=sqlite3.OperationalError("read failed")))
    Controller.undo(controller, event_id)
    assert controller.store.totals("2026-11-02")["water"] == 0
    assert controller.window.records == {}


@pytest.mark.parametrize("action", ["dismiss", "snooze", "toggle_pause"])
@pytest.mark.parametrize("failure", [sqlite3.OperationalError("database unavailable"), OSError("disk unavailable")])
def test_storage_failure_does_not_escape_close_paths(controller, monkeypatch, action, failure):
    def failing_read(*_):
        controller.window.hide.assert_called()
        assert not controller.cycle.visible
        raise failure
    monkeypatch.setattr(controller.store, "totals", failing_read)
    getattr(Controller, action)(controller)
    assert controller.store.db.execute("SELECT COUNT(*) FROM completions").fetchone()[0] == 0


def test_shutdown_closes_window_even_if_database_close_fails(controller, monkeypatch):
    monkeypatch.setattr(controller.store, "close", Mock(side_effect=sqlite3.OperationalError("close failed")))
    Controller.shutdown(controller)
    controller.timer.stop.assert_called_once()
    controller.tray.hide.assert_called_once()
    controller.window.hide.assert_called_once()
    controller.store.db.close()

