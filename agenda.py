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


# ---- the edits of the agenda, as the page of Sistema does them (each one is a click)
DAY_CHOICES = [[], [0, 1, 2, 3, 4], [5, 6], [0], [1], [2], [3], [4], [5], [6]]
DAY_NAMES = {(): "Todos os dias", (0, 1, 2, 3, 4): "Dias úteis", (5, 6): "Fim de semana",
             (0,): "Segunda", (1,): "Terça", (2,): "Quarta", (3,): "Quinta", (4,): "Sexta", (5,): "Sábado", (6,): "Domingo"}


def day_label(rule):
    return DAY_NAMES.get(tuple(rule.get("days") or []), "Dias escolhidos")


def clock(rule):
    m = parse_time(rule.get("time")) or 0
    return f"{m // 60:02d}:{m % 60:02d}"


def new_rule(scene=0):
    return {"time": "09:00", "days": [], "scene": int(scene), "on": True}


def apply(agenda, op, i, scenes=1):
    """One click on the agenda: op is "time", "scene", "days", "on", "del" or "add". Returns the agenda (changed in place)."""
    if op == "add":
        agenda.append(new_rule())
        return agenda
    if not 0 <= i < len(agenda):
        return agenda
    rule = agenda[i]
    if op == "time":
        m = ((parse_time(rule.get("time")) or 0) + 30) % 1440
        rule["time"] = f"{m // 60:02d}:{m % 60:02d}"
    elif op == "scene":
        rule["scene"] = (int(rule.get("scene", 0)) + 1) % max(1, scenes)
    elif op == "days":
        choices = [tuple(d) for d in DAY_CHOICES]
        cur = choices.index(tuple(rule.get("days") or [])) if tuple(rule.get("days") or []) in choices else 0
        rule["days"] = list(DAY_CHOICES[(cur + 1) % len(DAY_CHOICES)])
    elif op == "on":
        rule["on"] = not rule.get("on", True)
    elif op == "del":
        del agenda[i]
    return agenda
