from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import tempfile


CHARACTERS = {
    "deepseek": ("DeepSeek", "#44699b"),
    "chatgpt": ("ChatGPT", "#5f7990"),
    "claude": ("Claude", "#986533"),
    "gemini": ("Gemini", "#7758a6"),
    "glm": ("GLM", "#595264"),
    "grok": ("Grok", "#88632e"),
    "kimi": ("Kimi", "#65678b"),
    "qwen": ("Qwen", "#416b92"),
}


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@dataclass
class Settings:
    interval_minutes: int = 45
    start_hour: int = 9
    end_hour: int = 19
    workdays_only: bool = True
    smart_workday: bool = True
    idle_skip_minutes: int = 5
    snooze_minutes: int = 5
    auto_hide_seconds: int = 60
    character: str = "deepseek"
    pet_height: int = 280
    reduced_motion: bool = False
    position_x: int | None = None
    position_y: int | None = None
    screen_name: str = ""

    def validate(self):
        ranges = {
            "interval_minutes": (1, 240), "start_hour": (0, 23),
            "end_hour": (1, 24), "idle_skip_minutes": (1, 60),
            "snooze_minutes": (1, 60), "auto_hide_seconds": (0, 600),
            "pet_height": (180, 480),
        }
        for key, (low, high) in ranges.items():
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key} 必须是 {low}–{high} 之间的整数")
        if self.start_hour >= self.end_hour:
            raise ValueError("提醒结束时间必须晚于开始时间")
        if self.character not in CHARACTERS:
            raise ValueError("未知角色")
        for key in ("workdays_only", "smart_workday", "reduced_motion"):
            if type(getattr(self, key)) is not bool:
                raise ValueError(f"{key} 必须是布尔值")
        for key in ("position_x", "position_y"):
            value = getattr(self, key)
            if value is not None and (type(value) is not int or abs(value) > 100000):
                raise ValueError("窗口位置无效")
        if not isinstance(self.screen_name, str):
            raise ValueError("显示器名称无效")
        return self

    @classmethod
    def load(cls, path: Path, legacy: Path | None = None):
        warning = ""
        raw = {}
        source = path if path.exists() else legacy
        if source and source.exists():
            try:
                raw = json.loads(source.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("配置必须是对象")
            except (OSError, ValueError) as exc:
                raw = {}
                warning = f"配置未能读取，已使用默认设置：{exc}"
        if source == legacy:
            keys = {"interval_minutes", "start_hour", "end_hour", "workdays_only",
                    "smart_workday", "idle_skip_minutes", "snooze_minutes"}
        else:
            keys = {field.name for field in fields(cls)}
        try:
            return cls(**{k: v for k, v in raw.items() if k in keys}).validate(), warning
        except (TypeError, ValueError) as exc:
            return cls(), f"配置值无效，原文件保留：{exc}"

    def save(self, path: Path):
        self.validate()
        atomic_json(path, asdict(self))
