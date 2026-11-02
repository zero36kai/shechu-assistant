from dataclasses import dataclass
import time
from uuid import uuid4

from .config import Settings


class ReminderCycle:
    """一个倒计时、一张提醒；时间源可替换以复现休眠和跨天。"""

    def __init__(self, settings: Settings, clock=time.monotonic):
        self.settings = settings
        self.clock = clock
        self.last_tick = clock()
        self.remaining = settings.interval_minutes * 60.0
        self.visible = False
        self.paused = False
        self.snoozed = False
        self.session_id = None
        self.visible_elapsed = 0.0
        self.manual = False

    def show(self, manual=False):
        if self.visible:
            return False
        if self.session_id is None:
            self.session_id = uuid4().hex
        self.visible = True
        self.manual = manual
        self.snoozed = False
        self.visible_elapsed = 0
        self.last_tick = self.clock()
        return True

    def dismiss(self):
        self.visible = False
        self.snoozed = False
        self.session_id = None
        self.remaining = self.settings.interval_minutes * 60.0
        self.visible_elapsed = 0
        self.manual = False
        self.last_tick = self.clock()

    def snooze(self):
        if not self.visible:
            return
        self.visible = False
        self.snoozed = True
        self.manual = False
        self.remaining = self.settings.snooze_minutes * 60.0
        self.last_tick = self.clock()

    def set_paused(self, paused: bool):
        self.paused = paused
        self.dismiss()

    def interact(self):
        self.visible_elapsed = 0

    def tick(self, eligible: bool):
        now = self.clock()
        elapsed = max(0, now - self.last_tick)
        self.last_tick = now
        if not self.manual and (self.paused or not eligible):
            if self.visible:
                self.dismiss()
                return "hide"
            return None
        # 先收起失效提醒，再忽略挂起/休眠期间的计时，避免补发。
        if elapsed > 30:
            return None
        if self.visible:
            self.visible_elapsed += elapsed
            timeout = self.settings.auto_hide_seconds
            if timeout and self.visible_elapsed >= timeout:
                self.dismiss()
                return "hide"
        else:
            self.remaining = max(0, self.remaining - elapsed)
            if self.remaining == 0:
                self.show()
                return "show"
        return None


@dataclass(frozen=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int


def clamp_position(x: int, y: int, width: int, height: int, area: Bounds):
    return (
        min(max(x, area.x), area.x + max(0, area.width - width)),
        min(max(y, area.y), area.y + max(0, area.height - height)),
    )
