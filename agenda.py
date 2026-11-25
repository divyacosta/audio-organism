"""The agenda: rules by time of day and day of the week that bring a scene to the picture at that time (ScreenMaster's "agenda").

A rule is a dict: {"time": "HH:MM", "days": [0..6] (Monday = 0), "scene": index, "on": True}.
`due(agenda, now)` returns the rules that fire at this minute (once per minute, see `Ticker`)."""
import time


def parse_time(text):
    """"HH:MM" to minutes since midnight, or None when it is not a time."""
    try:
        h, m = str(text).strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return h * 60 + m
    except (ValueError, AttributeError):
        pass
    return None


def due(agenda, now):
    """The rules that fire at the minute of `now` (a struct_time or anything with tm_hour, tm_min and tm_wday)."""
    minute = now.tm_hour * 60 + now.tm_min
    out = []
    for rule in agenda or []:
        if not rule.get("on", True):
            continue
        if parse_time(rule.get("time")) != minute:
            continue
        days = rule.get("days")
        if days and now.tm_wday not in days:
            continue
        out.append(rule)
    return out


class Ticker:
    """Remembers the last minute it looked at, so a rule fires once per minute even though the loop runs many times a second."""

    def __init__(self):
        self.last = None

    def check(self, agenda, now=None):
        now = now or time.localtime()
        key = (now.tm_yday, now.tm_hour, now.tm_min)
        if key == self.last:
            return []
        self.last = key
        return due(agenda, now)
