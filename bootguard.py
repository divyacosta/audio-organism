"""Startup guard: a graphics driver that hangs (or crashes) while the shaders are being built must not trap the person on the loading window.

A hung `create_render_pipeline` cannot be cancelled from inside the process, so the guard works across launches and by relaunching:

  start()      before the picture window is made: reads what happened the last time. An attempt that never reached "frames are on the
               screen" (hung and killed, or crashed) counts against the video engine it used; the next engine is picked from the ones
               not yet blamed. When both were blamed it stops switching (auto engine, lowest quality) so it can never loop.
  adapter()    the renderer tells which engine it really got (the "auto" choice is only known once the adapter exists)
  tick()       called while the loading window is up: after TIMEOUT seconds the engine is blamed and the program starts again by itself
  ok()         a few seconds of real frames (or a normal quit): the attempt is over, nothing is blamed

The verdicts live in boot.json next to settings.json and are forgotten when the version changes. The person's own choice
(Sistema > Motor de vídeo) is never rewritten: the guard only overrides it for the run.
"""
import json
import os
import subprocess
import sys
import time

import settings
from version import VERSION

ORDER = ("Vulkan", "D3D12")
TIMEOUT = float(os.environ.get("VIS_BOOT_TIMEOUT", "120"))          # seconds of loading window before the engine is given up on (VIS_BOOT_TIMEOUT: tests)
FRAMES_OK = 90                                                      # frames on the screen before an attempt counts as good

_t0 = None
_on = False


def _path():
    return os.path.join(settings.APPDIR, "boot.json")


def _read():
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write(d):
    try:
        os.makedirs(settings.APPDIR, exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, _path())
    except Exception:
        pass


def choose(bad, pref):
    """Which engine to ask for, given the engines already blamed and the person's choice (None = automatic).
    Returns (engine or None for automatic, exhausted)."""
    good = [b for b in ORDER if b not in bad]
    if not good:
        return None, True
    if pref in good:
        return pref, False
    if pref is None and not bad:
        return None, False
    return good[0], False


def enabled():
    return _on


def start(pref):
    """Call once, before the renderer exists. `pref` is the engine the person asked for ("Vulkan", "D3D12" or None).
    Returns (engine to force or None, notice text or None, safe mode)."""
    global _t0, _on
    _t0, _on = time.perf_counter(), True
    st = _read()
    if st.get("version") != VERSION:                                 # a new version, maybe a new driver: forget the old verdicts
        st = {"version": VERSION, "bad": []}
    bad = [b for b in st.get("bad", []) if b in ORDER]
    last = st.get("attempt")
    if isinstance(last, dict) and last.get("version") == VERSION:    # the last attempt never reached the screen
        who = last.get("actual") or last.get("forced")
        if who in ORDER and who not in bad:
            bad.append(who)
    engine, exhausted = choose(bad, pref)
    notice = None
    if exhausted:
        notice = "Nenhum motor de vídeo respondeu: usando o automático com qualidade Baixo"
    elif bad and engine != pref:
        names = " e ".join(bad)
        notice = f"{names} não respondeu na abertura anterior: usando {engine or 'o automático'}"
    st["bad"] = bad
    st["safe"] = exhausted
    st["attempt"] = dict(version=VERSION, forced=engine, actual=None, ts=time.time())
    _write(st)
    return engine, notice, exhausted


def adapter(backend):
    """The renderer got its adapter: remember which engine it is (the automatic choice becomes a name)."""
    if not _on:
        return
    st = _read()
    att = st.get("attempt")
    if isinstance(att, dict):
        att["actual"] = str(backend) if str(backend) in ORDER else None
        _write(st)


def ok():
    """The attempt worked (or the person quit normally): nothing is blamed. Cheap to call many times."""
    global _on
    if not _on:
        return
    _on = False
    st = _read()
    if "attempt" in st:
        st.pop("attempt", None)
        _write(st)


def _relaunch():
    """Start the program again, apart from this process, and let the new one wait for the single-instance lock."""
    args = [sys.executable]
    if not getattr(sys, "frozen", False):
        args.append(os.path.abspath(sys.argv[0]))
    args += [a for a in sys.argv[1:] if a != "--fallback"] + ["--fallback"]
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"                      # a one-file exe started from itself must unpack on its own, not reuse this one's folder
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0       # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, env=env, creationflags=flags, close_fds=True)


def give_up(reason=""):
    """Blame the engine of the attempt in progress and start again with the other one. Returns False when it cannot (nothing to blame, or both
    engines were already blamed): the caller then keeps going as before. When it can, this process ends here and does not return."""
    if not _on:
        return False
    st = _read()
    att = st.get("attempt") if isinstance(st.get("attempt"), dict) else {}
    who = att.get("actual") or att.get("forced")
    bad = [b for b in st.get("bad", []) if b in ORDER]
    if who not in ORDER:
        return False
    if who not in bad:
        bad.append(who)
    st["bad"] = bad
    st.pop("attempt", None)
    st["last_reason"] = reason[:160]
    _write(st)
    if len([b for b in ORDER if b not in bad]) == 0:                 # both blamed: no third option, stop here and run without a timeout
        return False
    try:
        _relaunch()
    except Exception:
        return False
    os._exit(0)                                                     # not sys.exit: a thread stuck inside the driver would hold the process open


def tick():
    """Call while the loading window is shown. After TIMEOUT seconds without the shaders being ready, the engine is given up on."""
    if _on and _t0 is not None and time.perf_counter() - _t0 > TIMEOUT:
        give_up("tempo esgotado na abertura")


def wait_for_lock(try_lock, tries=40, pause=0.5):
    """The program started by give_up() must wait for the old process to release the single-instance lock. `try_lock()` is True when it got it."""
    for _ in range(tries):
        if try_lock():
            return True
        time.sleep(pause)
    return False
