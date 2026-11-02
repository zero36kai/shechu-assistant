from water_assistant.config import Settings
from water_assistant.core import Bounds, ReminderCycle, clamp_position


class Clock:
    value = 0
    def __call__(self):
        return self.value
    def step(self, seconds=1):
        self.value += seconds


def advance(cycle, clock, seconds, eligible=True):
    events = []
    for _ in range(seconds):
        clock.step()
        event = cycle.tick(eligible)
        if event:
            events.append(event)
    return events


def test_one_reminder_and_no_stacking():
    clock = Clock()
    cycle = ReminderCycle(Settings(interval_minutes=1, auto_hide_seconds=0), clock)
    assert advance(cycle, clock, 60) == ["show"]
    original = cycle.session_id
    assert advance(cycle, clock, 600) == []
    assert not cycle.show()
    assert cycle.session_id == original


def test_repeated_snooze_has_one_deadline_and_retains_session():
    clock = Clock()
    cycle = ReminderCycle(Settings(snooze_minutes=1), clock)
    cycle.show()
    session = cycle.session_id
    for _ in range(8):
        cycle.snooze()
        assert not cycle.visible
        assert advance(cycle, clock, 59) == []
        assert advance(cycle, clock, 1) == ["show"]
        assert cycle.session_id == session


def test_pause_cancels_snooze_and_no_delayed_popup():
    clock = Clock()
    cycle = ReminderCycle(Settings(interval_minutes=1, snooze_minutes=1), clock)
    cycle.show()
    cycle.snooze()
    cycle.set_paused(True)
    assert advance(cycle, clock, 600) == []
    cycle.set_paused(False)
    assert advance(cycle, clock, 59) == []
    assert advance(cycle, clock, 1) == ["show"]


def test_away_and_sleep_do_not_accumulate_reminders():
    clock = Clock()
    cycle = ReminderCycle(Settings(interval_minutes=1), clock)
    advance(cycle, clock, 30)
    assert advance(cycle, clock, 3600, eligible=False) == []
    assert cycle.remaining == 30
    clock.step(8 * 3600)
    assert cycle.tick(True) is None
    assert cycle.remaining == 30
    assert advance(cycle, clock, 30) == ["show"]


def test_auto_hide_is_not_completion_and_resets_interval():
    clock = Clock()
    cycle = ReminderCycle(Settings(interval_minutes=1, auto_hide_seconds=20), clock)
    cycle.show()
    assert advance(cycle, clock, 20) == ["hide"]
    assert cycle.session_id is None
    assert cycle.remaining == 60


def test_bounds_support_negative_screen_coordinates():
    screen = Bounds(-1920, 0, 1920, 1040)
    assert clamp_position(-100, -30, 600, 400, screen) == (-600, 0)
    assert clamp_position(-2200, 1000, 600, 400, screen) == (-1920, 640)
