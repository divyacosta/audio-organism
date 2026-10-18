"""Procedural director for the 3D scenes.

It watches the music (build-up, drop, breakdown, change of musical part, phrase boundaries) and
(1) picks the scene and the colour theme and (2) continuously modulates the scene:

  opening            Facetas, red theme
  drop               explosion, swap to the other scene, flash hides the cut
  breakdown          swap scene (cut)
  build-up / change of part / phrase
                     same scene, next colour theme (Facetas: red -> blue -> white -> ...; Estrela: new neon palette)
  continuous         complexity, speed, zoom and collapse follow the build-up; explosion decays after a drop

Every new look re-rolls the seed, so no two looks are the same.
"""
import math
import random

GENS = ["Facetas", "Estrela"]
# Scenes: (engine, profile, name). Engine 0 = the Facetas engine, 1 = Estrela. Profiles re-dress the Facetas engine:
#   0 Facetas, 1 Tunel (techno), 2 Catedral (trance), 3 Impacto (EDM), 4 Palco (pop)
SCENES = [(0, 0, "Facetas"), (0, 5, "Estrela"), (0, 1, "Túnel"), (0, 2, "Catedral"), (0, 3, "Impacto"), (0, 4, "Palco")]
# which scene suits which genre (indices of SCENES)
# Default image style of each scene (STYLES in menu.py: 1 = 3D, 2 = neon, 3 = holograma)
SCENE_STYLE = [1, 2, 3, 1, 1, 1]
# Automatic style: weights of each style (ids as in STYLES of menu.py: 1 3D, 2 Neon, 3 Holograma, 4 Raio X, 5 Cromado, 6 Aquarela, 7 Duotom)
# by part of the music. Calm parts get soft, quiet looks; loud parts get glowing or metallic ones; build-ups get the thin, tense ones.
AUTO_STYLE = {
    "CALM":        {6: 3, 4: 2, 3: 2, 1: 1, 5: 1},
    "BREAKDOWN":   {6: 3, 4: 2, 3: 2, 1: 1, 5: 1},
    "GROOVE":      {1: 3, 2: 2, 3: 2, 7: 1, 5: 1, 6: 1},
    "HIGH ENERGY": {2: 3, 5: 2, 7: 2, 1: 2, 3: 1},
    "DROP":        {2: 3, 5: 2, 7: 2, 1: 2, 3: 1},
    "BUILD-UP":    {3: 3, 4: 2, 2: 2, 7: 1},
}
GENRE_SCENE = {"techno": 2, "trance": 3, "edm": 4, "pop": 5}
GENRE_NAMES = {"techno": "techno", "trance": "trance", "edm": "EDM", "pop": "pop", "?": "?"}
GREY, DARK = (0.17, 0.18, 0.21), (0.05, 0.05, 0.07)
ACCENTS = {"vermelho": (1.0, 0.05, 0.18), "ciano": (0.0, 0.85, 1.0), "branco": (1.0, 1.0, 1.0)}
# kaleidoscope cuts each profile likes (indices of SYM_NAMES), and how much it cuts / changes colour (1 = the Facetas rate)
PROF_MODES = {0: None, 1: [3, 2, 4], 2: [3, 7], 3: [0, 5, 2], 4: [1, 6, 5], 5: [4, 2, 3, 5]}
PROF_CUTS = {0: 1.0, 1: 0.35, 2: 0.5, 3: 1.7, 4: 0.8, 5: 1.0}
# camera: menu levels -> physical values (see menu.CAM_*)
CAM_ORBIT = (0.0, 0.06, 0.12, 0.25)           # yaw swing, rad
CAM_SPIN = (0.0, 0.0, 0.14)                   # roll speed, rad/s
CAM_SWAY = (0.0, 0.07, 0.0)                   # roll swing, rad
CAM_SHAKE = (0.0, 0.5, 1.0)
CAM_PUNCH = (0.0, 0.05, 0.10)
CAM_FUNNEL = (0.0, 0.6, 1.0, 1.4)
# automatic camera: which preset values to follow in each part of the music (same numbers as menu.CAM_PRESETS)
CAM_AUTO_SETS = {
    1: dict(cam_orbit=2, cam_roll=0, cam_shake=0, cam_punch=0, cam_funnel=1, cam_fov_min=60, cam_fov_max=80, cam_fov_var=1, cam_sync=2),
    2: dict(cam_orbit=1, cam_roll=1, cam_shake=2, cam_punch=2, cam_funnel=3, cam_fov_min=80, cam_fov_max=115, cam_fov_var=2, cam_sync=1),
    3: dict(cam_orbit=1, cam_roll=2, cam_shake=0, cam_punch=0, cam_funnel=3, cam_fov_min=85, cam_fov_max=105, cam_fov_var=1, cam_sync=0),
}
# which cfg keys each switch of the "Auto" tab controls
CAM_GROUPS = {"orbit": ("cam_orbit",), "roll": ("cam_roll",), "shake": ("cam_shake",), "punch": ("cam_punch",), "funnel": ("cam_funnel",),
              "fov": ("cam_fov_min", "cam_fov_max", "cam_fov_var"), "sync": ("cam_sync",)}
MV_GROUPS = {"speed": ("mv_speed",), "rot": ("mv_rot", "mv_dir"), "pulse": ("mv_pulse", "mv_one"), "cuts": ("mv_cuts",), "inertia": ("mv_inertia",)}
# automatic movement: the preset that follows each part of the music (same numbers as menu.MV_PRESETS)
MV_AUTO_SETS = {
    "calm": dict(mv_speed=0, mv_rot=1, mv_dir=0, mv_pulse=0, mv_one=False, mv_cuts=0, mv_inertia=2),
    "groove": dict(mv_speed=1, mv_rot=2, mv_dir=2, mv_pulse=1, mv_one=False, mv_cuts=0, mv_inertia=2),
    "high": dict(mv_speed=2, mv_rot=3, mv_dir=2, mv_pulse=3, mv_one=False, mv_cuts=2, mv_inertia=0),
    "build": dict(mv_speed=3, mv_rot=2, mv_dir=2, mv_pulse=2, mv_one=True, mv_cuts=1, mv_inertia=1),
}
PROF_FUNNEL = {0: 0.0, 1: 0.55, 2: 0.15, 3: 0.10, 4: 0.0, 5: 0.35}
# Palco palette: pop pastels and bright candy colours
POP = {"rosa": (1.0, 0.42, 0.72), "ciano": (0.25, 0.88, 1.0), "amarelo": (1.0, 0.88, 0.35), "lilás": (0.70, 0.52, 1.0), "menta": (0.45, 1.0, 0.78), "coral": (1.0, 0.48, 0.42)}
# Impacto palette: hot, saturated colours that punch against black or white
HOT = {"magenta": (1.0, 0.08, 0.55), "laranja": (1.0, 0.42, 0.0), "amarelo": (1.0, 0.88, 0.05), "ciano": (0.0, 0.88, 1.0), "verde": (0.1, 1.0, 0.35), "vermelho": (1.0, 0.05, 0.1)}
# Catedral palette: stained glass, blue / violet / gold in three universes, over a near-black blue room
GLASS = {"azul": (0.10, 0.25, 1.0), "violeta": (0.55, 0.15, 1.0), "ouro": (1.0, 0.72, 0.18), "ciano": (0.15, 0.75, 1.0)}
ROOMS = [(0.0, 0.0, 0.03), (0.02, 0.0, 0.05), (0.0, 0.01, 0.04)]

# Facetas themes: (face, side, edge highlight). Red, blue and white take turns as the dominant colour.
THEMES = [
    [(1.00, 0.03, 0.24), (0.05, 0.25, 1.00), (1.00, 1.00, 1.00)],      # red panels, blue sides
    [(0.05, 0.24, 1.00), (1.00, 0.03, 0.24), (1.00, 1.00, 1.00)],      # blue panels, red sides
    [(0.92, 0.94, 1.00), (1.00, 0.03, 0.24), (0.10, 0.35, 1.00)],      # white panels, red sides, blue edge
]
THEME_NAMES = ["vermelho", "azul", "branco"]

# Estrela palettes
PALETTES = [
    [(0.30, 1.0, 0.25), (0.55, 0.22, 1.0), (0.85, 1.0, 0.92)],     # green / violet / white
    [(0.10, 0.90, 1.0), (1.0, 0.20, 0.85), (1.0, 0.90, 0.20)],     # cyan / magenta / yellow
    [(1.0, 0.08, 0.12), (0.12, 0.28, 1.0), (0.10, 0.90, 1.0)],     # red / blue / cyan
    [(0.15, 0.85, 0.80), (1.0, 0.55, 0.20), (1.0, 0.93, 0.82)],    # teal / orange / warm white
]


def _ss(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


BASE = {"vermelho": (1.00, 0.03, 0.24), "azul": (0.05, 0.25, 1.00), "branco": (1.00, 1.00, 1.00), "preto": (0.0, 0.0, 0.0)}
SYM_NAMES = ["espelho 4x", "espelho lateral", "radial 6", "radial 8", "radial 5", "diagonal", "espelho vertical", "radial 12"]
# one-sided kaleidoscopes (left/right only = 1, top/bottom only = 6) are drawn more often than the rest
SYM_W = [3, 5, 2, 2, 2, 2, 5, 0]


class NeonDirector:
    def __init__(self):
        self.scene = 0                 # index into SCENES (opening scene: Facetas)
        self.style_auto, self.style_t = 1, 0.0     # automatic image style (an id of STYLES) and time since it last changed
        # genre estimate (heuristic, refreshed every few seconds): tempo, how much of the sound sits in the mids, tempo confidence,
        # drops and long build-ups seen so far
        self.g_bpm, self.g_mid, self.g_conf, self.g_t = 0.0, 0.3, 0.0, 0.0
        self.g_drops, self.g_build_s, self.g_age = 0, 0.0, 0.0
        self.genre = "?"
        self.genre_scores = {}
        self.gen = 0
        self.prof = 0                  # profile of the Facetas engine
        self.theme = 0                 # red
        self.tension_now = 0.0
        self._restyle = False
        self._hc = False               # a hard cut happened this frame (the motion-blur trail is cleared)
        self.tr = None                 # running change of universe: the old elements shrink away, the new ones grow in
        self.layer_scale = [1.0] * 12
        self.layer_var = [0] * 12        # colour variant per layer (0..2); a few layers change colour on the beat in GROOVE
        self.var_step, self.var_off = -1, random.randrange(16)
        self.cam_p = dict(orbit=0.0, spin=0.0, sway=0.0, shake=0.0, punch=0.0, funnel=1.0, fov=90.0)
        self.cam_roll = 0.0
        self.rot_a = 0.0               # accumulated layer rotation (rad)
        self.cam_auto = 3
        self.cam_auto_t = 0.0
        self.mv_auto, self.mv_auto_t = "groove", 0.0
        self.funnel = 0.0              # 0..1: the funnel effect (layers converge and sink, the camera is pulled in)
        # Three universes (red / blue / white majority), each with its own kaleidoscope cut. Large / medium / small layers each belong to
        # one universe; that assignment, the colours of every universe and the background change with hard cuts on the beat.
        self.upals = [list(t) for t in THEMES]
        self.modes = [0, 2, 3]
        self.tiers = [0, 1, 2]
        self.bg = (0.0, 0.0, 0.0)
        self.bg_name = "preto"
        self.cut_cd, self.cut_beat = 0.0, 0
        self.pal = 0
        self.seed = [random.random() for _ in range(4)]
        self.pending = None            # (gen, style) waiting for the fade-out
        self.fade = 1.0
        self.phase = "idle"            # idle | down | up
        self.age = 0.0
        self.why = "início"
        self.flow_t = random.random() * 50
        self.travel = 0.0
        self.explode = 0.0
        self.build = 0.0
        self.log = []
        # event tracking
        self.prev_bd = False
        self.prev_build = False
        self.last_beat = 0
        self.stable, self.cand, self.cand_t = None, None, 0.0

    # ------------------------------------------------------------------ looks
    def note(self, text):
        self.log.append(text)
        self.log = self.log[-6:]

    def look_name(self):
        if self.gen == 0 and self.prof != 0:
            return f"{SCENES[self.scene][2]} · {' '.join(str(k + 1) for k in self.tiers)}"
        if self.gen == 0:
            return f"{GENS[0]} · G/M/P {' '.join(str(k + 1) for k in self.tiers)} · fundo {self.bg_name}"
        return GENS[1]

    def new_look(self, gen, why, style):
        self.pending = (gen, style)
        self.why = why
        if style == "now":
            self._apply()
        else:
            self.phase = "down"
        self.note(f"{why}: {self.look_name() if style == 'now' else SCENES[gen][2]}")

    def duo_colors(self):
        """The two colours of the duotone: the dark one is a deep shade of the large layers' side colour, the light one their face colour.
        They follow the universes, so they change with every colour cut on the beat."""
        u = self.upals[self.tiers[0]]
        dark = tuple(c * 0.20 for c in u[1])
        light = tuple(min(1.0, c * 1.05) for c in u[0])
        return (dark, light)

    def pick_style(self):
        """Automatic image style: drawn by the part of the music (AUTO_STYLE), favouring the scene's own style, never the one just used."""
        part = "BUILD-UP" if (self.why == "build-up" or self.tension_now > 0.5) else self.feat_state
        w = dict(AUTO_STYLE.get(part, AUTO_STYLE["GROOVE"]))
        d = SCENE_STYLE[self.scene]
        w[d] = w.get(d, 0) + 2
        w.pop(self.style_auto, None)
        if not w:
            return self.style_auto
        self.style_auto = random.choices(list(w), weights=list(w.values()))[0]
        self.style_t = 0.0
        self._hc = True
        return self.style_auto

    def pop_hardcut(self):
        hc, self._hc = self._hc, False
        return hc

    def roll_colors(self):
        """Hard cut of the colours: the background takes one of black / red / blue / white and every universe re-draws its face, side and
        edge colours from the other colours, so the elements never disappear into the background."""
        self._hc = True
        if self.prof == 1:                                           # TUNEL: dark grey ribs, black room, one accent colour per universe
            acc = random.sample(list(ACCENTS), 3)
            self.bg_name, self.bg = "preto", (0.0, 0.0, 0.0)
            for k in range(3):
                self.upals[k] = [GREY, DARK, ACCENTS[acc[k]]]
            return
        if self.prof == 2:                                           # CATEDRAL: stained-glass palettes
            order = random.sample(list(GLASS), 4)
            self.bg_name, self.bg = "azul profundo", random.choice(ROOMS)
            for k in range(3):
                self.upals[k] = [GLASS[order[k]], GLASS[order[(k + 1) % 4]], GLASS[order[(k + 2) % 4]]]
            return
        if self.prof == 3:                                           # IMPACTO: hot colours; the background cuts hard between black, white and a hot colour
            roll = random.random()
            if roll < 0.45:
                self.bg_name, bgc = "preto", (0.0, 0.0, 0.0)
            elif roll < 0.67:
                self.bg_name, bgc = "branco", (0.95, 0.95, 0.96)
            else:
                self.bg_name = random.choice(list(HOT))
                bgc = tuple(c * 0.9 for c in HOT[self.bg_name])
            self.bg = bgc
            pool = [n for n in HOT if n != self.bg_name]
            random.shuffle(pool)
            for k in range(3):
                a, b, c = pool[(k * 2) % len(pool)], pool[(k * 2 + 1) % len(pool)], pool[(k * 2 + 2) % len(pool)]
                edge = (0.05, 0.05, 0.06) if self.bg_name == "branco" else (1.0, 1.0, 1.0)
                self.upals[k] = [HOT[a], HOT[b], edge]
            return
        if self.prof == 4:                                           # PALCO: pastel faces over a soft background
            roll = random.random()
            if roll < 0.30:
                self.bg_name, self.bg = "branco", (0.97, 0.96, 0.98)
            elif roll < 0.55:
                self.bg_name, self.bg = "noite", (0.07, 0.04, 0.14)
            else:
                self.bg_name = random.choice(list(POP))
                self.bg = tuple(c * 0.55 for c in POP[self.bg_name])
            pool = [n for n in POP if n != self.bg_name]
            random.shuffle(pool)
            ink = (0.10, 0.06, 0.18) if self.bg_name == "branco" else (1.0, 1.0, 1.0)
            for k in range(3):
                self.upals[k] = [POP[pool[(k * 2) % len(pool)]], POP[pool[(k * 2 + 1) % len(pool)]], ink]
            return
        if self.prof == 5:                                           # ESTRELA: neon palettes (three colours each), mostly in a black room
            pals = random.sample(PALETTES, 3)
            for k in range(3):
                self.upals[k] = [tuple(c) for c in pals[k]]
            self.bg_name, self.bg = ("preto", (0.0, 0.0, 0.0)) if random.random() < 0.7 else ("noite", (0.0, 0.01, 0.05))
            return
        names = list(BASE)
        weights = [18, 24, 24, 20]                                  # preto, vermelho, azul, branco -> order of BASE below
        order = ["preto", "vermelho", "azul", "branco"]
        w = [0 if n == self.bg_name else wt for n, wt in zip(order, weights)]
        self.bg_name = random.choices(order, weights=w)[0]
        self.bg = tuple(c * 0.92 for c in BASE[self.bg_name])
        pool = [n for n in ("vermelho", "azul", "branco") if n != self.bg_name]
        if self.bg_name != "preto":
            pool.append("preto")
        for k in range(3):
            r = pool[:]
            random.shuffle(r)
            if self.bg_name == "preto" and random.random() < 0.7 and "branco" in r:      # a light edge shows best on black
                r.remove("branco")
                r.append("branco")
            if self.bg_name == "branco" and "preto" in r:                                  # a dark edge shows best on white
                r.remove("preto")
                r.append("preto")
            self.upals[k] = [BASE[r[0]], BASE[r[1]], BASE[r[2]]]

    def roll_universes(self):
        w, modes = list(SYM_W), []
        pool = PROF_MODES.get(self.prof)
        if pool:                                                      # the profile's favourite cuts
            w = [(SYM_W[k] if k in pool else 0) for k in range(len(SYM_NAMES))]
        for _ in range(3):                                           # every universe gets a different kaleidoscope cut, one-sided ones favoured
            m = random.choices(range(len(SYM_NAMES)), weights=w)[0]
            modes.append(m)
            w[m] = 0
            if sum(w) <= 0 and pool:                                # a small pool: let the universes share cuts
                w = [(SYM_W[k] + 1 if k in pool else 0) for k in range(len(SYM_NAMES))]
        self.modes = modes
        order = [0, 1, 2]
        random.shuffle(order)
        self.tiers = order

    def swap_tier(self):
        """A size tier (small most often) changes universe. It is a transition, not a cut: the elements of the current universe shrink
        away, then the elements of the other universe (its own colours and kaleidoscope) grow in. The layers after the tier share its
        frame of reference, so they go through the same shrink and growth; that keeps them from jumping when the frame changes."""
        if self.tr is not None:
            return
        tier = random.choices([0, 1, 2], weights=[20, 35, 45])[0]
        new = random.choice([k for k in range(3) if k != self.tiers[tier]])
        self.tr = dict(tier=tier, new=new, t=0.0, switched=False)

    def step_transition(self, dt):
        tr = self.tr
        if tr is None:
            self.layer_scale = [1.0] * 12
            return
        tr["t"] += dt
        first = tr["tier"] * 4
        t_sw = 0.35 + (11 - first) * 0.05
        if not tr["switched"] and tr["t"] >= t_sw:
            self.tiers[tr["tier"]] = tr["new"]
            tr["switched"] = True
        sc = [1.0] * 12
        done = True
        ease = lambda x: x * x * (3.0 - 2.0 * x)
        for j in range(first, 12):
            if not tr["switched"]:
                pv = max(0.0, min(1.0, (tr["t"] - (11 - j) * 0.05) / 0.35))
                sc[j] = 1.0 - ease(pv)
                done = False
            else:
                pg = max(0.0, min(1.0, (tr["t"] - t_sw - (j - first) * 0.06) / 0.40))
                sc[j] = ease(pg)
                if pg < 1.0:
                    done = False
        self.layer_scale = sc
        if done:
            self.tr = None
            self.layer_scale = [1.0] * 12

    def _apply(self):
        sc, _ = self.pending
        self._hc = True
        self._restyle = True
        self.scene = sc
        self.gen, self.prof = SCENES[sc][0], SCENES[sc][1]
        self.theme = (self.theme + 1) % len(THEMES)         # themes alternate in order
        self.roll_universes()
        self.roll_colors()
        self.tr = None
        self.layer_scale = [1.0] * 12
        self.layer_var = [0] * 12
        self.var_off = random.randrange(16)                      # a new look re-draws which layers sit on which step
        self.cut_cd = 1.5
        self.pal = random.choice([p for p in range(len(PALETTES)) if p != self.pal])
        self.seed = [random.random() for _ in range(4)]
        self.age = 0.0
        self.pending = None

    # ----------------------------------------------------------------- events
    def detect(self, dt, an):
        ev = set()
        if an.drop_event:
            ev.add("drop")
        bd = an.state == "BREAKDOWN"
        if bd and not self.prev_bd:
            ev.add("breakdown")
        self.prev_bd = bd
        if an.tension > 0.55 and not self.prev_build:
            ev.add("buildup")
            self.prev_build = True
        elif an.tension < 0.35:
            self.prev_build = False
        if an.phrase_event:                                   # the phrase (8 bars, counted from the downbeat) starts now
            ev.add("phrase")
        self.last_beat = an.beat_n
        st = an.state if an.state in ("CALM", "GROOVE", "HIGH ENERGY") else None
        if st is not None:
            if st == self.cand:
                self.cand_t += dt
            else:
                self.cand, self.cand_t = st, 0.0
            if self.cand_t > 2.0 and self.stable != st:
                if self.stable is not None:
                    ev.add("change")
                self.stable = st
        return ev

    # ----------------------------------------------------------------- genre and scene choice
    def update_genre(self, dt, an):
        """Rough genre guess from tempo, mid-range share, tempo confidence, drops and long build-ups. It is a heuristic: it will be wrong
        for plenty of songs, which is why the scene can always be forced in the menu."""
        self.g_age += dt
        if an.bpm > 0:
            self.g_bpm += (an.bpm - self.g_bpm) * (1.0 - math.exp(-dt / 6.0)) if self.g_bpm else an.bpm - self.g_bpm
        tot = an.bass + an.mid + an.high + 1e-6
        self.g_mid += (an.mid / tot - self.g_mid) * (1.0 - math.exp(-dt / 8.0))
        self.g_conf += (an.conf - self.g_conf) * (1.0 - math.exp(-dt / 6.0))
        if an.drop_event:
            self.g_drops += 1
        if an.tension > 0.5:
            self.g_build_s += dt
        self.g_t += dt
        if self.g_t < 3.0 or self.g_age < 20.0 or self.g_bpm <= 0:
            return
        self.g_t = 0.0
        b, m, c = self.g_bpm, self.g_mid, self.g_conf
        sc = {
            "techno": (1.0 if 118 <= b <= 138 else 0.0) + 0.5 * (c > 0.7) + (0.6 if self.g_drops == 0 else 0.0) + (0.6 if m < 0.30 else 0.0) + (0.3 if self.g_build_s < 8 else 0.0),
            "trance": (1.0 if 130 <= b <= 146 else 0.0) + (0.8 if self.g_build_s >= 14 else 0.3 * (self.g_build_s >= 7)) + (0.3 if self.g_drops >= 1 else 0.0) + (0.4 if 0.2 < m < 0.4 else 0.0),
            "edm": (0.9 if 122 <= b <= 134 else 0.0) + (1.0 if self.g_drops >= 2 else 0.6 * (self.g_drops == 1)) + (0.4 if self.g_build_s >= 4 else 0.0) + (0.4 if m < 0.40 else 0.0),
            "pop": (0.9 if 85 <= b <= 124 else 0.0) + (1.0 if m >= 0.38 else 0.0) + (0.6 if self.g_drops == 0 else 0.0) + (0.3 if c > 0.5 else 0.0),
        }
        self.genre_scores = sc
        best = max(sc, key=sc.get)
        if sc[best] >= 1.6:
            self.genre = best

    def pick_scene(self, an):
        """A change of scene: with a genre guess, mostly that genre's scene (never the same one twice in a row), the rest from the others;
        """
        cands = [k for k in range(len(SCENES)) if k != self.scene]
        w = []
        for k in cands:
            wt = 1.0
            if self.genre in GENRE_SCENE:
                wt = 5.0 if k == GENRE_SCENE[self.genre] else (1.0 if SCENES[k][2] in ("Facetas", "Estrela") else 0.4)
            w.append(wt)
        if self.genre in GENRE_SCENE and self.scene != GENRE_SCENE[self.genre] and random.random() < 0.6:
            return GENRE_SCENE[self.genre]
        return random.choices(cands, weights=w)[0]

    def intensity_calm(self):
        return self.feat_state in ("CALM", "BREAKDOWN", "SILENCE")

    def resolve_auto(self, cfg, an, dt):
        """The settings the rest of the frame uses: where a mode is Auto, the parameters that the Auto tab includes come from the
        automatic choice for the current part of the music; the ones it leaves out keep the user's own value."""
        c = dict(cfg)
        if int(c.get("camera", 0)) == 4:
            self.cam_auto_t += dt
            if self.cam_auto_t > 12.0:                       # at least 12 s per choice
                want = 2 if (self.explode > 0.3 or self.build > 0.6) else (1 if an.energy < 0.35 else 3)
                if want != self.cam_auto:
                    self.cam_auto, self.cam_auto_t = want, 0.0
            s = CAM_AUTO_SETS[self.cam_auto]
            for grp, keys in CAM_GROUPS.items():
                if c.get("auto_cam_" + grp, True):
                    for k in keys:
                        c[k] = s[k]
            c["camera"] = 5
        if int(c.get("movement", 0)) == 5:
            self.mv_auto_t += dt
            if self.mv_auto_t > 8.0:
                if an.tension > 0.5 and an.state not in ("SILENCE", "DROP"):
                    want = "build"
                elif an.state in ("HIGH ENERGY", "DROP"):
                    want = "high"
                elif an.state in ("CALM", "BREAKDOWN", "SILENCE"):
                    want = "calm"
                else:
                    want = "groove"
                if want != self.mv_auto:
                    self.mv_auto, self.mv_auto_t = want, 0.0
            s = MV_AUTO_SETS[self.mv_auto]
            for grp, keys in MV_GROUPS.items():
                if c.get("auto_mv_" + grp, True):
                    for k in keys:
                        c[k] = s[k]
            c["movement"] = 6
        return c

    # ----------------------------------------------------------------- update
    def update(self, dt, an, cfg):
        self.age += dt
        E = an.energy
        cfg = self.resolve_auto(cfg, an, dt)
        ev = self.detect(dt, an)
        self.feat_state = an.state
        self.update_genre(dt, an)
        self.tension_now = an.tension
        self.style_t += dt
        forced = int(cfg.get("effect", 0)) - 1            # -1 auto, otherwise an index into SCENES
        forced = forced if forced < len(SCENES) else -1

        def scene_for(swap):
            if forced >= 0:
                return forced
            if not cfg.get("auto_scene", True):             # the Auto tab leaves the scene out: it stays where it is
                return self.scene
            if not swap:
                return self.scene
            return self.pick_scene(an)

        if forced >= 0 and self.scene != forced and self.pending is None and self.phase == "idle":
            self.new_look(forced, "manual", "cut")
        elif "drop" in ev:
            self.new_look(scene_for(True), "drop", "now")
            self.explode = 1.0
        elif "breakdown" in ev:
            self.new_look(scene_for(True), "breakdown", "cut")
        elif "buildup" in ev:
            self.new_look(scene_for(False), "build-up", "cut")
        elif "change" in ev:
            self.new_look(scene_for(False), "mudança de parte", "cut")
        elif "phrase" in ev and self.age > 18.0 and self.phase == "idle":
            self.new_look(scene_for(False), "frase", "cut")
        elif "phrase" in ev and self.style_t > 24.0 and cfg.get("style", 8) == 8 and cfg.get("auto_style", True):       # automatic style also changes inside a long look
            self.pick_style()
        if getattr(self, "_restyle", False) and self.pending is None:
            self._restyle = False
            if cfg.get("style", 8) == 8 and cfg.get("auto_style", True):
                self.pick_style()

        # hard cuts on the beat: a size tier jumps to another universe, or all colours (elements AND background) are re-drawn.
        # Every 2 beats in loud passages, every 4 normally, every 8 when calm; never closer than 1.2 s
        self.cut_cd = max(0.0, self.cut_cd - dt)
        if an.beat_n != self.cut_beat and cfg.get("auto_cuts", True):
            self.cut_beat = an.beat_n
            calm = max(0.0, min(1.0, (0.35 - E) / 0.2))
            period = (2 if E > 0.6 else (4 if calm < 0.3 else 8)) * (1 if PROF_CUTS[self.prof] >= 1 else 2)
            mvc = int(cfg.get("mv_cuts", 1))
            period = max(1, int(round(period * (2.0, 1.0, 0.5)[mvc])))
            if (self.gen == 0 and self.pending is None and self.phase == "idle" and self.cut_cd <= 0 and (an.bar_n * 4 + an.beat_in_bar if an.bar_n >= 0 else an.beat_n) % period == 0
                    and self.age > 4.0 and random.random() < (0.5, 0.8, 0.95)[int(cfg.get("mv_cuts", 1))]):
                self.cut_cd = 1.2
                if random.random() < 0.55 * min(1.0, PROF_CUTS[self.prof] * 1.6):
                    self.roll_colors()
                else:
                    self.swap_tier()

        # a new phrase starts: that is where the ear expects the picture to change, so colours / universes are re-drawn on the downbeat
        if (an.phrase_event and self.pending is None and self.phase == "idle" and self.cut_cd <= 0 and self.age > 4.0
                and an.state not in ("SILENCE",) and cfg.get("auto_cuts", True) and random.random() < 0.9):
            self.cut_cd = 1.2
            if random.random() < 0.6:
                self.roll_colors()
            else:
                self.swap_tier()
        self.step_transition(dt)
        # Step sequencer on the BPM: every layer owns a slot of the bar (4/4). On its slot it changes colour (its universe's face / side /
        # edge colours rotate one place, hard cut), so some elements change on beat 1, others on beat 2, 3 and 4, like a drum pattern.
        #   calm / breakdown   only beats 1 and 3, a quarter of the elements per step
        #   groove             every beat of the bar
        #   high energy / drop every 8th note (two steps per beat)
        #   build-up           16th notes, the pattern speeds up with the tension
        #   silence            nothing
        e_n = max(0.0, min(1.0, (E - 0.10) / 0.55))                          # energy, 0..1
        beat_q = max(0.0, min(1.0, an.conf)) * (0.4 + 0.6 * min(1.0, an.kick))   # how firm the beat is: tempo confidence and live kick
        p_change = (0.06 + 0.54 * e_n * (0.3 + 0.7 * beat_q)) * PROF_CUTS[self.prof]                  # lower energy and weaker beat: much rarer changes
        st_res = {"CALM": 2, "BREAKDOWN": 2, "GROOVE": 4, "HIGH ENERGY": 8, "DROP": 8, "SILENCE": 0}.get(an.state, 4)
        if an.tension > 0.5 and an.state not in ("SILENCE", "DROP"):
            st_res = 16
        if st_res and cfg.get("auto_vars", True) and self.gen == 0 and self.pending is None and self.phase == "idle":
            per_beat = 1 if st_res <= 4 else (2 if st_res == 8 else 4)          # steps per beat
            sub = min(per_beat - 1, int(an.phase * per_beat)) if per_beat > 1 else 0
            step = an.beat_in_bar * per_beat + sub                              # position in the bar, 0 .. 4 * per_beat - 1
            if step != self.var_step:
                self.var_step = step
                if st_res > 2 or an.beat_in_bar in (0, 2):                     # calm: only beats 1 and 3
                    slots = 4 * per_beat
                    for i in range(12):
                        if (i * 3 + self.var_off) % slots == step:               # this layer's slot in the bar
                            if random.random() < p_change:                       # only now and then: more often with energy and a strong beat
                                self.layer_var[i] = (self.layer_var[i] + 1) % 3

        # fade state machine for cut transitions
        if self.phase == "down":
            self.fade = max(0.0, self.fade - dt / 0.10)
            if self.fade <= 0.0:
                if self.pending:
                    self._apply()
                self.phase = "up"
        elif self.phase == "up":
            self.fade = min(1.0, self.fade + dt / 0.25)
            if self.fade >= 1.0:
                self.phase = "idle"

        # continuous procedural modulation by the build-up
        # MOVEMENT options (see menu.MV_*): overall speed, layer rotation, inertia, kick pulse
        inert = (0.4, 1.0, 2.2)[int(cfg.get("mv_inertia", 1))]                     # time-constant factor of the slow smoothings
        sp_i = int(cfg.get("mv_speed", 1))
        speed = (0.5, 1.0, 1.8)[sp_i] if sp_i < 3 else 0.45 + 1.4 * min(1.0, E / 0.6)
        self.build += (an.tension - self.build) * (1.0 - math.exp(-dt / (0.35 * inert)))
        self.explode *= math.exp(-dt / (0.9 * math.sqrt(inert)))
        if an.drop_event:
            self.explode = 1.0
        b = self.build
        alive = an.alive
        complexity = max(0.45, min(1.0, 0.45 + 0.55 * b + 0.30 * E))               # always enough layers to fill the screen
        self.flow_t += dt * speed * (0.25 + 1.3 * an.e_fast + 1.0 * an.drop_b) * (0.3 + 0.7 * alive)
        self.travel += dt * speed * (0.30 + 1.2 * E + 4.0 * b + 6.0 * self.explode) * (0.3 + 0.7 * alive)
        self.rot_a += dt * (0.0, 0.05, 0.10, 0.25)[int(cfg.get("mv_rot", 2))] * (1.0 + 0.6 * b) * speed * (0.3 + 0.7 * alive)
        t = self.flow_t
        # funnel: it opens during build-ups and drops (the picture is sucked toward the centre), and breathes lightly with the energy
        # a slow breathing keeps the camera drifting in and out at all times, so the movement is always there to see
        ft = min(1.0, 0.30 * (0.5 + 0.5 * math.sin(t * 0.45)) + 0.95 * b + 0.8 * self.explode + 0.25 * max(0.0, E - 0.4)) if cfg.get("cam_funnel", 2) > 0 else 0.0
        if self.prof == 3:
            ft += 0.45 * an.kick                                     # Impacto: the camera punches in on every kick
        ft = max(ft, PROF_FUNNEL[self.prof]) if self.gen == 0 else ft
        self.funnel += (ft - self.funnel) * (1.0 - math.exp(-dt / ((0.5 if ft > self.funnel else 1.4) * inert)))
        if True:                                            # camera: preset 0 is the fixed front view
            c = cfg
            sync = int(c.get("cam_sync", 0))
            cyc = an.bar_phase if sync == 1 else (an.phrase_phase if sync == 2 else None)      # position in the bar / phrase, 0..1
            lo, hi = float(c.get("cam_fov_min", 90)), float(c.get("cam_fov_max", 90))
            var = c.get("cam_fov_var", 0)
            if var == 1:
                drive = 0.5 + 0.5 * math.sin(t * 0.3 if cyc is None else 2.0 * math.pi * cyc)
            elif var == 2:
                drive = min(1.0, 0.45 * E + 0.7 * b + 0.8 * self.explode + 0.25 * an.kick)
            else:
                drive = 0.5
            tgt = dict(orbit=CAM_ORBIT[c.get("cam_orbit", 0)], spin=CAM_SPIN[c.get("cam_roll", 0)], sway=CAM_SWAY[c.get("cam_roll", 0)],
                       shake=CAM_SHAKE[c.get("cam_shake", 0)], punch=CAM_PUNCH[c.get("cam_punch", 0)], funnel=CAM_FUNNEL[c.get("cam_funnel", 2)],
                       fov=lo + (hi - lo) * drive)
            k = 1.0 - math.exp(-dt / ((0.35 if var == 2 else 1.5) * inert))
            cp = self.cam_p
            for key in cp:
                cp[key] += (tgt[key] - cp[key]) * k
            self.cam_roll += dt * cp["spin"]
            self.cam_roll = (self.cam_roll + math.pi) % (2.0 * math.pi) - math.pi          # a full turn looks the same: keep it in -pi..pi
            if tgt["spin"] == 0.0:                                                        # spin off: the image settles back to level
                self.cam_roll *= math.exp(-dt / 0.8)
            if cyc is None:
                roll = self.cam_roll + cp["sway"] * math.sin(t * 0.5)
                yaw = cp["orbit"] * math.sin(t * 0.16)
                pitch = 0.5 * cp["orbit"] * math.sin(t * 0.11 + 1.0)
                sh = cp["shake"] * 0.010 * an.kick
                accent = 1.0
            else:                                                       # in time: one swing per bar (or per phrase), the punch strongest on the one
                roll = self.cam_roll + cp["sway"] * math.sin(2.0 * math.pi * cyc)
                yaw = cp["orbit"] * math.sin(2.0 * math.pi * cyc)
                pitch = 0.5 * cp["orbit"] * math.cos(2.0 * math.pi * cyc)
                sh = cp["shake"] * 0.010 * max(an.kick, 0.8 * an.mel_hit)          # the tremor follows the melody notes too
                accent = 1.0 if an.beat_in_bar == 0 else 0.55
            yaw += sh * math.sin(t * 61.0)
            pitch += sh * math.cos(t * 53.0)
            zoom = (4.6 - 0.8 * b + 0.8 * self.explode) * (1.0 - cp["punch"] * accent * an.kick)
            cam = (yaw, pitch, zoom)
            fov, pal = 2.0 * math.tan(math.radians(cp["fov"]) * 0.5), THEMES[self.theme]
            self.cam_roll_out = roll
        return dict(
            gen=self.gen, prof=self.prof, style_default=SCENE_STYLE[self.scene], style_auto=self.style_auto, duo=self.duo_colors(), seed=self.seed, pal=pal, bg=(self.bg if self.gen == 0 else (0.0, 0.0, 0.0)), tier_uni=list(self.tiers), layer_scale=list(self.layer_scale), hardcut=self.pop_hardcut(), layer_var=list(self.layer_var), modes=list(self.modes), upals=self.upals, time=t, travel=self.travel, rot=self.rot_a, rdir=int(cfg.get("mv_dir", 0)), pulse=(0.0, 0.04, 0.08, 0.15)[int(cfg.get("mv_pulse", 0))] * an.kick * (1.0 if (not cfg.get("mv_one", False) or an.beat_in_bar == 0) else 0.0), fov=fov, roll=getattr(self,'cam_roll_out',0.0), cam=cam, funnel=(min(1.0, self.funnel * self.cam_p['funnel']) if self.gen == 0 else 0.0),
            build=b, complexity=complexity, collapse=_ss(0.7, 1.0, b), explode=self.explode,
            drop=an.drop_b, fade=self.fade, gain=0.12 + 0.88 * alive,
        )
