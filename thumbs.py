"""Live thumbnails of the scene gallery: every scene is drawn in real time, always at a very low resolution.

One extra renderer (headless, 128x72) and one director per scene run in a background thread, one scene at a time, so the main picture is
never held up. The thread only works while the gallery is on screen (`want` is refreshed by the control window).
"""
import threading
import time

import look
import scenes as SC
from neon_director import NeonDirector

SIZE = (128, 72)


class Thumbs:
    def __init__(self, power="high-performance"):
        self.power = power
        self.want = []                     # the scene dicts on screen (set by the control window every frame)
        self.t_want = 0.0
        self.frames = {}                   # id(scene) -> (counter, rgba bytes)
        self.fmt = "rgba8unorm"
        self.size = SIZE
        self.ready = False
        self.error = None
        self._src = None                   # (analysis, settings, reactivity) of the main loop
        self._dirs = {}                    # id(scene) -> [director, time of its last frame, scene]
        self._stop = False
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()

    def feed(self, an, cfg, rk):
        self._src = (an, cfg, rk)

    def show(self, scene_list):
        """The scenes the gallery draws now."""
        self.want = list(scene_list)
        self.t_want = time.perf_counter()

    def stop(self):
        self._stop = True

    # ------------------------------------------------------------ thread
    def _run(self):
        while not self.want and not self._stop:                          # nothing to draw until the gallery is first opened
            time.sleep(0.1)
        try:
            from renderer import Renderer
            rend = Renderer(headless=True, size=SIZE, power=self.power)
            rend.preview_size = SIZE
            rend.preview, rend.preview_every = True, 1
            rend.res, rend.steps, rend.bounces, rend.rt = 100, 40, 1, False
            rend.aa, rend.fxaa, rend.msaa, rend.mblur, rend.sharp = False, False, 0, 0, 0.0
            rend.bloom_levels, rend.bloom_shift, rend.dist = 2, 2, 7.0
            self.fmt = rend.fmt
            self.ready = True
        except Exception as e:
            self.error = repr(e)
            return
        i = 0
        while not self._stop:
            sc_list = self.want
            if not sc_list or self._src is None or time.perf_counter() - self.t_want > 0.6:
                time.sleep(0.05)
                continue
            t0 = time.perf_counter()
            try:
                sc = sc_list[i % len(sc_list)]
                i += 1
                self._frame(rend, sc)
            except Exception as e:                                        # the settings change under our feet: just try again
                self.error = repr(e)
                time.sleep(0.05)
            self._forget(sc_list)
            time.sleep(max(0.0, 1.0 / 40.0 - (time.perf_counter() - t0)))      # at most ~40 thumbnails a second in total

    def _forget(self, keep):
        ids = {id(s) for s in keep}
        for k in [k for k in self._dirs if k not in ids]:
            del self._dirs[k]
            self.frames.pop(k, None)

    def _frame(self, rend, sc):
        an, cfg, rk = self._src
        now = time.perf_counter()
        key = id(sc)
        if sc.get("scene_visual", 1) == 0 and not sc.get("bg_light", 0):  # Nenhum without lights: black, nothing to draw
            if key not in self.frames:
                self.frames[key] = (1, bytes(SIZE[0] * SIZE[1] * 4))
            return
        ent = self._dirs.get(key)
        if ent is None:
            d = NeonDirector()
            d.scenes = [sc]
            d.scene = 0
            d.pending = (0, "cut")
            d._apply()
            ent = self._dirs[key] = [d, now]
        d, last = ent
        dt = max(1e-3, min(0.25, now - last))
        ent[1] = now
        c = dict(cfg)
        SC.apply_scene(c, sc)
        c["scenes"], c["effect"] = [sc], 1
        params = d.update(dt, an, c)
        look.apply(rend, params, d.cur, 100)
        rk = sc.get("react", 100) / 100.0
        params.update(bass=an.bass * rk, mid=an.mid * rk, high=an.high * rk, kick=an.kick * rk, snare=an.snare, hat=an.hat,
                      beat=(an.beat_n + an.phase) if an.bpm > 0 else now * 2.0)
        rend.bloom, rend.flash, rend.dt = 0.8 * sc.get("bloom", 60) / 100.0, 0.0, dt
        rend.render(params)
        if rend.preview_rgba is not None:
            self.frames[key] = (rend.preview_n, rend.preview_rgba)
