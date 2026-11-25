"""Regras por programa (ScreenMaster's): when a program is in front, the picture can change scene and the agenda can pause (useful for games).

`current()` says which program is in front right now (its exe name, lower case; "" when unknown). The loop asks it about twice a second,
`Watch.update()` applies the rules and gives them back when the program leaves the front. Windows only: elsewhere it always answers "".
"""
import ctypes
import os
from ctypes import wintypes

OWN = {os.path.basename(os.path.abspath(os.environ.get("VIS_OWN_EXE", "") or "MusicVisualizer.exe")).lower(), "musicvisualizer.exe", "python.exe", "pythonw.exe"}
_PROCESS_QUERY_LIMITED = 0x1000


def current():
    """The exe name of the program in the front, lower case, or "" (no window, or not Windows, or not allowed to ask)."""
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value or pid.value == os.getpid():
            return ""
        h = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return ""
            return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return ""


class Watch:
    """Keeps the rules working: the program in front picks its scene (and may pause the agenda); when it leaves the front, the scene it
    replaced comes back. `last` is the last program in front that is not this one (what the Adicionar of the rules page adds)."""

    def __init__(self):
        self.active = None           # the rule that is applied now: (process, scene it replaced or None)
        self.paused = False          # the agenda is paused by the rule that is applied

    def update(self, cfg, play_scene):
        exe = current()
        if exe and exe not in OWN:
            cfg["last_fg_app"] = exe
        rules = cfg.get("app_rules") or []
        hit = next((r for r in rules if str(r.get("process", "")).lower() == exe), None) if exe and exe not in OWN else None
        if hit is not None:
            if self.active is None or self.active[0] != hit.get("process"):
                if self.active is not None:
                    self._leave(play_scene)
                changed = hit.get("scene") is not None
                self.active = (hit.get("process"), int(cfg.get("scene_edit", 0)) if changed else None)
                if changed:
                    play_scene(int(hit["scene"]))
            self.paused = bool(hit.get("pause"))
        elif self.active is not None:
            self._leave(play_scene)

    def _leave(self, play_scene):
        _, back = self.active
        self.active = None
        self.paused = False
        if back is not None:
            play_scene(back)
