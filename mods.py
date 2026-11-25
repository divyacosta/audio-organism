"""A música controla: the settings of a scene that follow the music.

A scene keeps two dicts:
  mods    key -> {"src": source, "lo": value, "hi": value}: a number that moves between lo and hi with a part of the music (instead of staying fixed)
  cycles  key -> {"opts": [values], "when": moment}: a choice that alternates between the values picked, at every beat, bar, phrase or drop

`Mods.apply` gives the scene as it is in this frame (a copy with those keys changed; the stored scene is never written). The director calls it once per frame
and everything that reads the scene on screen (the picture, the Acabamento, the overlay, the thumbnails) sees the moved values."""

SOURCES = (("Graves", "bass"), ("Médios", "mid"), ("Agudos", "high"), ("Batida", "kick"), ("Energia", "energy"))
WHEN = (("Batida", 0), ("Compasso", 1), ("Frase", 2), ("Drop", 3))
MOD_KEYS = ("m_psx", "m_psy", "m_pox", "m_poy", "m_decay", "m_thick", "m_funnel", "m_glass", "gen_p1", "gen_p2", "gen_p3", "react", "bloom", "expo",
            "fin_bright", "fin_contrast", "fin_sat", "fin_gamma", "scr_vig", "img_pix", "ov_size", "ov_op", "bg_int", "bg_speed")     # the numbers the picture reads from the scene every frame
CYCLE_KEYS = ("scene_palette", "scene_visual", "img_style", "scene_bg", "fin_temp", "m_round", "ov_pos")                         # the choices that can alternate


def signal(an, src):
    """0..1 of a source of the music."""
    name = SOURCES[max(0, min(len(SOURCES) - 1, int(src)))][1]
    v = float(getattr(an, name, 0.0) or 0.0)
    return max(0.0, min(1.0, v))


class Mods:
    def __init__(self):
        self.env = {}          # (scene, key) -> the smoothed signal (it rises fast and falls slower, so the picture does not shake)
        self.idx = {}          # (scene, key) -> which of the picked values is on now
        self.beat = None

    def apply(self, sc, an, dt, ev=()):
        mods, cyc = sc.get("mods") or {}, sc.get("cycles") or {}
        beat = int(getattr(an, "beat_n", 0) or 0)
        beat_ev = self.beat is not None and beat != self.beat
        self.beat = beat
        if not mods and not cyc:
            return sc
        out = dict(sc)
        for k, m in mods.items():
            if k not in sc:
                continue
            v = signal(an, m.get("src", 0))
            key = (id(sc), k)
            e = self.env.get(key, v)
            e += (v - e) * min(1.0, dt * (14.0 if v > e else 4.0))
            self.env[key] = e
            lo, hi = float(m.get("lo", sc[k])), float(m.get("hi", sc[k]))
            val = lo + (hi - lo) * e
            out[k] = int(round(val)) if isinstance(sc[k], int) and not isinstance(sc[k], bool) else val
        for k, c in cyc.items():
            opts = list(c.get("opts") or [])
            if not opts:
                continue
            w = int(c.get("when", 2))
            trig = (w == 0 and beat_ev) or (w == 1 and bool(getattr(an, "bar_event", False))) or (w == 2 and "phrase" in ev) or (w == 3 and "drop" in ev)
            key = (id(sc), k)
            i = self.idx.get(key, 0)
            if trig:
                i = (i + 1) % len(opts)
            self.idx[key] = i
            out[k] = opts[i % len(opts)]
        return out


def label(key, m):
    """One line of the Ligações page for a key that follows the music."""
    return f"{SOURCES[int(m.get('src', 0)) % len(SOURCES)][0]}  ·  de {m.get('lo')} a {m.get('hi')}"
