"""Cheap timers for the performance report (report.py). Everything is a no-op until `ON` is set, so the program pays nothing for them.

    prof.mark_start()          # a stage begins: the clock of the laps starts here
    ...work...
    prof.mark("GPU/buffers")   # the time since the last mark (or mark_start) goes to this name
    prof.add("GPU/entregar", seconds)

Names are "Stage/part": the report groups them by the text before the slash."""
import time

ON = False
_acc = {}
_last = 0.0


def mark_start():
    global _last
    if ON:
        _last = time.perf_counter()


def mark(name):
    global _last
    if ON:
        now = time.perf_counter()
        _acc[name] = _acc.get(name, 0.0) + now - _last
        _last = now


def add(name, seconds):
    if ON:
        _acc[name] = _acc.get(name, 0.0) + seconds


def reset():
    _acc.clear()


def totals():
    return dict(_acc)
