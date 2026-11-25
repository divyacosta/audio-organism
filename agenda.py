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


# ---- faixas (lanes): a number of the scene follows the day. Each lane has points (minute of the day, value); between two points the
# value is a straight line, before the first and after the last it holds. The agenda writes it once a minute (the page is the editor).
LANE_KEYS = {"bloom": ("Brilho das luzes", 0, 200), "expo": ("Exposição", 50, 200), "react": ("Reatividade ao som", 25, 200)}


def lane_value(points, minute):
    """The value of a lane at a minute of the day, or None when the lane has no points."""
    pts = sorted((int(m), float(v)) for m, v in points)
    if not pts:
        return None
    if minute <= pts[0][0]:
        return pts[0][1]
    if minute >= pts[-1][0]:
        return pts[-1][1]
    for (m0, v0), (m1, v1) in zip(pts, pts[1:]):
        if m0 <= minute <= m1:
            return v0 if m1 == m0 else v0 + (v1 - v0) * (minute - m0) / (m1 - m0)
    return pts[-1][1]


def apply_lanes(cfg, now, lanes=None):
    """Writes every lane's value at this minute into the settings it drives (clamped to the slider's range). `lanes`: the ones that run now."""
    minute = now.tm_hour * 60 + now.tm_min
    for lane in (lanes if lanes is not None else playback(cfg, now)[1]):
        key = lane.get("key")
        if key not in LANE_KEYS:
            continue
        v = lane_value(lane.get("points") or [], minute)
        if v is None:
            continue
        _, lo, hi = LANE_KEYS[key]
        cfg[key] = int(max(lo, min(hi, round(v))))


class LaneTicker:
    """Writes the lanes once per minute, not every frame: a slider the person moves is not fought every frame."""

    def __init__(self):
        self.last = None

    def check(self, now=None):
        now = now or time.localtime()
        key = (now.tm_yday, now.tm_hour, now.tm_min)
        if key == self.last:
            return False
        self.last = key
        return True


# ---- perfis da agenda (ScreenMaster's day profiles): a profile has days and its own rules and lanes. A day covered by a profile uses it;
# the other days use the agenda as it is (the "Padrão"). The page edits one of them at a time (cfg["agenda_edit"]: -1 = the Padrão).
def profiles(cfg):
    return cfg.setdefault("agenda_profiles", [])


def edit_index(cfg):
    i = int(cfg.get("agenda_edit", -1))
    return i if 0 <= i < len(profiles(cfg)) else -1


def edit_rules(cfg):
    i = edit_index(cfg)
    if i < 0:
        return cfg.setdefault("agenda", [])
    return profiles(cfg)[i].setdefault("rules", [])


def edit_lanes(cfg):
    i = edit_index(cfg)
    if i < 0:
        return cfg.setdefault("agenda_lanes", [])
    return profiles(cfg)[i].setdefault("lanes", [])


def playback(cfg, now):
    """The rules and the lanes that run today (at this time): the profile that covers the weekday, or the Padrão."""
    wd = now.tm_wday
    for p in profiles(cfg):
        if wd in (p.get("days") or []):
            return p.get("rules") or [], p.get("lanes") or []
    return cfg.get("agenda") or [], cfg.get("agenda_lanes") or []
