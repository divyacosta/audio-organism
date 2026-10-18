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
SYM_NAMES = ["espelho 4x", "espelho lateral", "radial 6", "radial 8", "radial 5", "diagonal", "espelho vertical"]
# one-sided kaleidoscopes (left/right only = 1, top/bottom only = 6) are drawn more often than the rest
SYM_W = [3, 5, 2, 2, 2, 2, 5]


class NeonDirector:
    def __init__(self):
        self.gen = 0                   # opening scene: Facetas
        self.theme = 0                 # red
        self._hc = False               # a hard cut happened this frame (the motion-blur trail is cleared)
        self.tr = None                 # running change of universe: the old elements shrink away, the new ones grow in
        self.layer_scale = [1.0] * 12
        self.layer_var = [0] * 12        # colour variant per layer (0..2); a few layers change colour on the beat in GROOVE
        self.var_step, self.var_off = -1, random.randrange(16)
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
        self.note(f"{why}: {self.look_name() if style == 'now' else GENS[gen]}")

    def pop_hardcut(self):
        hc, self._hc = self._hc, False
        return hc

    def roll_colors(self):
        """Hard cut of the colours: the background takes one of black / red / blue / white and every universe re-draws its face, side and
        edge colours from the other colours, so the elements never disappear into the background."""
        self._hc = True
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
        for _ in range(3):                                           # every universe gets a different kaleidoscope cut, one-sided ones favoured
            m = random.choices(range(len(SYM_NAMES)), weights=w)[0]
            modes.append(m)
            w[m] = 0
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
        gen, _ = self.pending
        self._hc = True
        self.gen = gen
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
        if an.beat_n != self.last_beat and an.beat_n % 8 == 0:
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

    # ----------------------------------------------------------------- update
    def update(self, dt, an, cfg):
        self.age += dt
        E = an.energy
        ev = self.detect(dt, an)
        forced = int(cfg.get("effect", 0)) - 1            # -1 auto, 0 Facetas, 1 Estrela

        def scene_for(swap):
            if forced >= 0:
                return forced
            return 1 - self.gen if swap else self.gen

        if forced >= 0 and self.gen != forced and self.pending is None and self.phase == "idle":
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

        # hard cuts on the beat: a size tier jumps to another universe, or all colours (elements AND background) are re-drawn.
        # Every 2 beats in loud passages, every 4 normally, every 8 when calm; never closer than 1.2 s
        self.cut_cd = max(0.0, self.cut_cd - dt)
        if an.beat_n != self.cut_beat:
            self.cut_beat = an.beat_n
            calm = max(0.0, min(1.0, (0.35 - E) / 0.2))
            period = 2 if E > 0.6 else (4 if calm < 0.3 else 8)
            if (self.gen == 0 and self.pending is None and self.phase == "idle" and self.cut_cd <= 0 and an.beat_n % period == 0
                    and self.age > 4.0 and random.random() < 0.8):
                self.cut_cd = 1.2
                if random.random() < 0.55:
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
        p_change = 0.06 + 0.54 * e_n * (0.3 + 0.7 * beat_q)                  # lower energy and weaker beat: much rarer changes
        st_res = {"CALM": 2, "BREAKDOWN": 2, "GROOVE": 4, "HIGH ENERGY": 8, "DROP": 8, "SILENCE": 0}.get(an.state, 4)
        if an.tension > 0.5 and an.state not in ("SILENCE", "DROP"):
            st_res = 16
        if st_res and self.gen == 0 and self.pending is None and self.phase == "idle":
            per_beat = 1 if st_res <= 4 else (2 if st_res == 8 else 4)          # steps per beat
            sub = min(per_beat - 1, int(an.phase * per_beat)) if per_beat > 1 else 0
            step = (an.beat_n % 4) * per_beat + sub                              # position in the bar, 0 .. 4 * per_beat - 1
            if step != self.var_step:
                self.var_step = step
                if st_res > 2 or (an.beat_n % 4) in (0, 2):                     # calm: only beats 1 and 3
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
        self.build += (an.tension - self.build) * (1.0 - math.exp(-dt / 0.35))
        self.explode *= math.exp(-dt / 0.9)
        if an.drop_event:
            self.explode = 1.0
        b = self.build
        alive = an.alive
        complexity = max(0.45, min(1.0, 0.45 + 0.55 * b + 0.30 * E))               # always enough layers to fill the screen
        self.flow_t += dt * (0.25 + 1.3 * an.e_fast + 1.0 * an.drop_b) * (0.3 + 0.7 * alive)
        self.travel += dt * (0.30 + 1.2 * E + 4.0 * b + 6.0 * self.explode) * (0.3 + 0.7 * alive)
        t = self.flow_t
        # funnel: it opens during build-ups and drops (the picture is sucked toward the centre), and breathes lightly with the energy
        # a slow breathing keeps the camera drifting in and out at all times, so the movement is always there to see
        ft = min(1.0, 0.30 * (0.5 + 0.5 * math.sin(t * 0.45)) + 0.95 * b + 0.8 * self.explode + 0.25 * max(0.0, E - 0.4)) if cfg.get("funnel", True) else 0.0
        self.funnel += (ft - self.funnel) * (1.0 - math.exp(-dt / (0.5 if ft > self.funnel else 1.4)))
        if self.gen == 0:                                   # fixed orthographic front view
            cam = (0.0, 0.0, 4.6 - 0.8 * b + 0.8 * self.explode)                   # fixed front view, orthographic: z = zoom
            fov, pal = 1.3, THEMES[self.theme]
        else:
            cam = (0.6 * math.sin(t * 0.13), 0.18 + 0.10 * math.sin(t * 0.09), 3.6 - 1.0 * b + 0.8 * self.explode)
            fov, pal = 1.3 - 0.35 * b + 0.5 * self.explode, PALETTES[self.pal]
        return dict(
            gen=self.gen, seed=self.seed, pal=pal, bg=(self.bg if self.gen == 0 else (0.0, 0.0, 0.0)), tier_uni=list(self.tiers), layer_scale=list(self.layer_scale), hardcut=self.pop_hardcut(), layer_var=list(self.layer_var), modes=list(self.modes), upals=self.upals, time=t, travel=self.travel, fov=fov, cam=cam, funnel=(self.funnel if self.gen == 0 else 0.0),
            build=b, complexity=complexity, collapse=_ss(0.7, 1.0, b), explode=self.explode,
            drop=an.drop_b, fade=self.fade, gain=0.12 + 0.88 * alive,
        )
