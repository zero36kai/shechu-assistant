from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

import run_v2
from water_assistant import heartbeat


@pytest.mark.parametrize("args,expected", [
    ([], ["--heartbeat", "--show"]),
    (["--heartbeat"], ["--heartbeat"]),
    (["--data-dir", "portable-data"], ["--data-dir", "portable-data"]),
    (["--command", "quit"], ["--command", "quit"]),
])
def test_frozen_entry_opens_once_and_does_not_recurse(args, expected, monkeypatch):
    gui = Mock(return_value=0)
    guard = Mock(return_value=0)
    monkeypatch.setattr(run_v2.sys, "frozen", True, raising=False)
    monkeypatch.setattr("water_assistant.app.main", gui)
    monkeypatch.setattr(heartbeat, "main", guard)
    assert run_v2.main(args) == 0
    used, unused = (guard, gui) if "--heartbeat" in expected else (gui, guard)
    used.assert_called_once_with(expected)
    unused.assert_not_called()


@pytest.mark.parametrize("frozen", [False, True])
def test_heartbeat_launches_correct_entry_with_data_directory(tmp_path, monkeypatch, frozen):
    application = QApplication.instance() or QApplication([])
    spawn = Mock()
    monkeypatch.setattr(heartbeat, "send_command", Mock(return_value=False))
    monkeypatch.setattr(heartbeat.subprocess, "Popen", spawn)
    monkeypatch.setattr(heartbeat.sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(heartbeat.sys, "executable", str(tmp_path / "ShechuAssistant.exe"))
    assert heartbeat.Heartbeat(tmp_path, isolated=True).check(show=True) == "starting"
    command = spawn.call_args.args[0]
    if frozen:
        assert command == [str(tmp_path / "ShechuAssistant.exe"), "--data-dir", str(tmp_path), "--isolated", "--show"]
    else:
        assert Path(command[0]).name == "pythonw.exe"
        assert command[1:3] == ["-B", str(heartbeat.ROOT / "run_v2.py")]
        assert command[3:] == ["--data-dir", str(tmp_path), "--isolated", "--show"]
    assert "--heartbeat" not in command
