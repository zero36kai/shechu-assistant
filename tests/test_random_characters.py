from types import SimpleNamespace
from unittest.mock import Mock

from water_assistant.app import Controller
from water_assistant.config import CHARACTERS, Settings
from water_assistant.core import ReminderCycle


def test_eight_random_characters_each_round_and_same_role_after_snooze(monkeypatch):
    shuffle = Mock(side_effect=lambda population, count: list(reversed(population)))
    monkeypatch.setattr("water_assistant.app.random.sample", shuffle)
    controller = SimpleNamespace(
        cycle=ReminderCycle(Settings()), character_pool=[], character_session=None,
        active_character="deepseek", store=Mock(), window=Mock(), dashboard=Mock(),
    )
    controller.store.session_records.return_value = {}
    roles = []
    for _ in range(8):
        controller.cycle.show()
        Controller.display_cycle(controller)
        selected = controller.window.begin.call_args.args[1]
        roles.append(selected)
        controller.cycle.snooze()
        controller.cycle.show()
        Controller.display_cycle(controller)
        assert controller.window.begin.call_args.args[1] == selected
        controller.cycle.dismiss()
    assert set(roles) == set(CHARACTERS) and len(roles) == 8
    shuffle.assert_called_once()
    controller.cycle.show()
    Controller.display_cycle(controller)
    assert shuffle.call_count == 2
