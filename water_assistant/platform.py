import ctypes
from ctypes import wintypes
from datetime import date
import json
import logging
from pathlib import Path
import queue
import sys
import threading
import urllib.request

from .config import atomic_json


def idle_seconds():
    if sys.platform != "win32":
        return 0

    class LastInput(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    info = LastInput()
    info.cbSize = ctypes.sizeof(info)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        tick = ctypes.windll.kernel32.GetTickCount()
        return ((tick - info.dwTime) & 0xFFFFFFFF) / 1000.0
    return 0


def desktop_locked():
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.SwitchDesktop.argtypes = [wintypes.HANDLE]
    desktop = user32.OpenInputDesktop(0, False, 0x0100)
    if not desktop:
        return True
    try:
        return not bool(user32.SwitchDesktop(desktop))
    finally:
        user32.CloseDesktop(desktop)


def foreground_fullscreen():
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, name, 256)
    if name.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
        return False
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    monitor = user32.MonitorFromWindow(hwnd, 2)
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    bounds = info.rcMonitor
    return (rect.left <= bounds.left and rect.top <= bounds.top and
            rect.right >= bounds.right and rect.bottom >= bounds.bottom)


class WorkdayCalendar:
    """联网只发生在后台；离线返回周一至周五，不阻塞窗口操作。"""

    def __init__(self, path: Path, legacy: Path | None = None):
        self.path = path
        self.cache = {}
        self.requested = set()
        self.results = queue.SimpleQueue()
        for source in (legacy, path):
            if source and source.exists():
                try:
                    raw = json.loads(source.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        self.cache.update({k: v for k, v in raw.items() if type(v) is bool})
                except (OSError, ValueError):
                    logging.warning("工作日缓存无法读取：%s", source)

    def is_workday(self, day: date, smart=True, weekdays_only=True):
        if not weekdays_only:
            return True
        while not self.results.empty():
            key, value = self.results.get_nowait()
            if value is not None:
                self.cache[key] = value
                try:
                    atomic_json(self.path, self.cache)
                except OSError:
                    logging.exception("工作日缓存保存失败")
        key = day.isoformat()
        if smart:
            if key in self.cache:
                return self.cache[key]
            if key not in self.requested:
                self.requested.add(key)
                threading.Thread(target=self._fetch, args=(key,), daemon=True).start()
        return day.weekday() < 5

    def _fetch(self, key):
        value = None
        try:
            request = urllib.request.Request(
                "https://timor.tech/api/holiday/info/" + key,
                headers={"User-Agent": "WaterAssistant/2.0"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.load(response)
            kind = payload.get("type", {}).get("type")
            if type(kind) is int and kind in (0, 1, 2, 3):
                value = kind in (0, 3)
        except Exception:
            logging.info("工作日查询不可用，按本地设置提醒", exc_info=True)
        self.results.put((key, value))
