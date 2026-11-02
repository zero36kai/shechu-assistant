from types import SimpleNamespace
from unittest.mock import Mock

from water_assistant.app import Controller
from water_assistant.heartbeat import Heartbeat


def test_healthy_heartbeat_does_not_show_or_spawn(tmp_path, monkeypatch):
    ping = Mock(return_value=True)
    spawn = Mock()
    monkeypatch.setattr("water_assistant.heartbeat.send_command", ping)
    monkeypatch.setattr("water_assistant.heartbeat.subprocess.Popen", spawn)
    heartbeat = Heartbeat(tmp_path)
    assert heartbeat.check() == "healthy"
    assert heartbeat.check() == "healthy"
    assert [call.args[1] for call in ping.call_args_list] == ["ping", "ping"]
    spawn.assert_not_called()


def test_manual_launch_shows_existing_v2_once(tmp_path, monkeypatch):
    ping = Mock(return_value=True)
    monkeypatch.setattr("water_assistant.heartbeat.send_command", ping)
    assert Heartbeat(tmp_path).check(show=True) == "healthy"
    assert [call.args[1] for call in ping.call_args_list] == ["ping", "show"]


def test_quit_marks_stop_before_exiting(tmp_path):
    application = Mock()
    application.quit.side_effect = lambda: (tmp_path / "heartbeat.stop").read_text(encoding="utf-8")
    controller = SimpleNamespace(data_dir=tmp_path, window=Mock(), dashboard=Mock(), application=application)
    Controller.quit(controller)
    assert (tmp_path / "heartbeat.stop").read_text(encoding="utf-8") == "user quit"
    controller.window.hide.assert_called_once()
    application.quit.assert_called_once()
