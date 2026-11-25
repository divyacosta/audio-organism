"""The stack of layers of a scene, as the renderer needs it every frame (no GPU in here, so it can be tested alone).

`FxStack.update(p, dt)` takes the parameters of the frame (the layers of the scene and the music) and returns a Plan:
  tone   the tone-mapping mode (the last tone layer on)
  fb     the feedback trail: dict(amt, zoom, rot, hue, blur) or None
  part   the particles: dict(count, mode, size, amt) or None
  post   the effect layers drawn as passes over the picture, bottom to top: dict(kind, op, bm, amt, p1..p6)
  bg     the background layers (gradient, lights), bottom to top, as they go into the composite shader
The effects glide from one scene to the next: a layer that goes away (another scene, or turned off) fades out over half a second with the parameters it had,
and a new one fades in, so changing scene dissolves the effects into each other and a trail fades by itself."""
import math

import numpy as np

import layers as LY

POST_KIND = {"ca": 1, "edge": 2, "fl": 3, "gr": 4}
SRC_NAMES = ("", "kick", "snare", "hat", "bass", "mid", "high", "energy", "build", "drop")
GLIDE = 0.5                                 # seconds for an effect to fade in or out


class Plan:
    def __init__(self):
        self.tone, self.fb, self.part, self.post, self.bg = 0, None, None, [], []


def signal(p, src):
    name = SRC_NAMES[max(0, min(9, int(src)))]
    if not name:
        return 0.0
    if name == "energy":
        v = (float(p.get("bass", 0.0)) + float(p.get("mid", 0.0)) + float(p.get("high", 0.0))) / 3.0
    else:
        v = float(p.get(name, 0.0))
    return max(0.0, min(1.0, v))


class FxStack:
    def __init__(self):
        self.env = {}                       # the smoothed music signal of each layer that follows it
        self.state = {}                     # (type, n) -> {"layer", "gain"}: the effect layers on screen, with their fade
        self.ready = False

    # ------------------------------------------------------------------ following the music
    def follow(self, p, layer, key, dt):
        """The amount of a layer (0..1.x): `amt` %, shaped by the music when the layer follows one (source, how much, sensitivity, threshold, curve, inverted,
        attack and release), times its opacity."""
        base = float(layer.get("amt", 100)) / 100.0
        op = float(layer.get("op", 100)) / 100.0
        src = int(layer.get("src", 0))
        if base <= 0 or op <= 0:
            self.env.pop(key, None)
            return 0.0
        if src == 0:
            return base * op
        sig = signal(p, src) * float(layer.get("gain", 100)) / 100.0
        thr = float(layer.get("thr", 0)) / 100.0
        sig = max(0.0, min(1.0, (sig - thr) / max(1e-3, 1.0 - thr)))
        curve = int(layer.get("curve", 0))
        if curve == 1:
            sig = sig ** 2.5
        elif curve == 2:
            sig = sig ** 0.5
        if layer.get("inv", False):
            sig = 1.0 - sig
        env = self.env.get(key, 0.0)
        tau = (0.3 * float(layer.get("atk", 0)) / 100.0) if sig > env else (1.5 * float(layer.get("rel", 25)) / 100.0)
        dt = max(1e-3, min(0.25, dt))
        env = sig if tau <= 1e-3 else env + (sig - env) * float(1.0 - math.exp(-dt / tau))
        self.env[key] = env
        amt = float(layer.get("famt", 50)) / 100.0
        return base * ((1.0 - amt) + 2.0 * amt * env) * op

    # ------------------------------------------------------------------------ the plan
    def update(self, p, dt, bloom=0.6, aspect=1.78, size=(1280, 720)):
        plan = Plan()
        dt = max(1e-3, min(0.25, dt))
        fxl = [l for l in (p.get("layers") or []) if LY.TYPES.get(l.get("t"), {}).get("group") in ("fx", "part")]
        target, seen = [], {}
        for l in fxl:
            t = l["t"]
            n = seen.get(t, 0)
            seen[t] = n + 1
            target.append(((t, n), l))
        keys = {k for k, _ in target}
        k_fade = 1.0 - math.exp(-dt / GLIDE)
        for k, l in target:
            st = self.state.get(k)
            if st is None:
                st = self.state[k] = {"layer": l, "gain": 1.0 if (not self.ready and l.get("on", True)) else 0.0}
            st["layer"] = l
            goal = 1.0 if l.get("on", True) else 0.0
            st["gain"] += (goal - st["gain"]) * k_fade
            if abs(goal - st["gain"]) < 0.01:
                st["gain"] = goal
        for k in list(self.state):
            if k not in keys:
                st = self.state[k]
                st["gain"] += (0.0 - st["gain"]) * k_fade
                if st["gain"] < 0.01:
                    del self.state[k]
                    self.env.pop(k, None)
        self.ready = True
        order = [k for k, _ in target] + [k for k in self.state if k not in keys]           # the layers of the scene first, the ones fading out on top
        tone_on = None
        time_ = float(p.get("time", 0.0))
        for k in order:
            st = self.state[k]
            g, l = st["gain"], st["layer"]
            if g < 0.01:
                continue
            t = l["t"]
            if t == "tone":
                if g > 0.5:
                    tone_on = int(l.get("mode", 1))
            elif t == "fb":
                if plan.fb is None:
                    a = self.follow(p, l, k, dt) * g
                    plan.fb = dict(amt=min(0.97, a * 0.97 + 0.02 * float(p.get("kick", 0.0)) * (1 if a > 0 else 0)), zoom=float(l.get("zoom", 0)), rot=float(l.get("rot", 0)),
                                   hue=float(l.get("hue", 0)), blur=float(l.get("blur", 0)) / 100.0, fbt=int(l.get("fbt", 0)))
            elif t == "part":
                if plan.part is None:
                    plan.part = dict(count=int(l.get("count", 2)), mode=int(l.get("pmode", 0)), size=float(l.get("psize", 50)), amt=self.follow(p, l, k, dt) * g)
            elif t in POST_KIND and len(plan.post) < LY.MAX_FX:
                a = self.follow(p, dict(l, op=100), k, dt)                      # the amount, shaped by the music
                bm = int(l.get("bm", 0))
                kind = POST_KIND[t]
                d = dict(kind=kind, op=g * float(l.get("op", 100)) / 100.0, bm=bm, amt=a)       # the opacity of the layer and its fade decide how it is put over the picture
                if t == "ca":
                    d.update(p1=float(l.get("dir", 0)), p2=float(l.get("start", 0)) / 100.0, p3=float(l.get("blur", 0)) / 100.0, p4=0.0, p5=0.0, p6=0.0)
                elif t == "edge":
                    d.update(p1=float(l.get("r", 0)) / 100.0, p2=float(l.get("shape", 0)), p3=0.0, p4=0.0, p5=0.0, p6=0.0)
                elif t == "fl":
                    d.update(p1=float(l.get("len", 100)) / 100.0, p2=float(l.get("col", 0)), p3=float(l.get("n", 1)), p4=float(l.get("blur", 0)) / 100.0, p5=0.0, p6=bloom)
                else:
                    d.update(p1=float(l.get("size", 1)), p2=float(l.get("where", 0)), p3=float(l.get("color", 0)), p4=float(l.get("fps", 0)), p5=float(l.get("blur", 0)) / 100.0, p6=0.0)
                d["time"] = time_
                plan.post.append(d)
        plan.tone = tone_on if tone_on is not None else 0
        # the background layers come already placed by the director (their colours cycle with the music)
        for i, item in enumerate((p.get("bgl") or [])[:LY.MAX_BG]):
            l = item["layer"]
            if not l.get("on", True):
                continue
            amt = self.follow(p, dict(l, op=100), ("bg", i), dt)
            plan.bg.append(dict(kind=1 if l["t"] == "grad" else 2, bm=int(l.get("bm", 0)), op=float(l.get("op", 100)) / 100.0, amt=amt, cols=item.get("cols"),
                                angle=float(item.get("angle", 0.0)), react=float(l.get("greact", 0)) / 100.0, gtype=int(l.get("gtype", 1)), style=int(l.get("style", 1)),
                                speed=float(l.get("speed", 100)) / 100.0, lcol=int(l.get("lcol", 0))))
        return plan


def pack_bg(plan, pal):
    """The 20 vec4 of the background layers for the composite uniform (80 floats)."""
    out = np.zeros(80, np.float32)
    for i, b in enumerate(plan.bg[:LY.MAX_BG]):
        o = i * 20
        out[o:o + 4] = (b["kind"], b["bm"], b["op"], 0.0)
        if b["kind"] == 1:
            cols = b.get("cols") or ((0.0, 0.0, 0.0),) * 3
            out[o + 4:o + 8] = (b["gtype"], b["amt"], 1.0, b["react"])
            out[o + 8:o + 11] = cols[0]
            out[o + 12:o + 15], out[o + 15] = cols[1], b["angle"]
            out[o + 16:o + 19] = cols[2]
        else:
            ca, cb = pal
            fixed = {1: ((0.92, 0.92, 0.92), (0.75, 0.82, 1.0)), 2: ((0.92, 0.03, 0.22), (1.0, 0.35, 0.45)), 3: ((0.0, 0.31, 0.93), (0.3, 0.55, 1.0))}.get(b["lcol"])
            if fixed:
                ca, cb = fixed
            out[o + 4:o + 8] = (b["style"], b["amt"], b["speed"], 0.0)
            out[o + 8:o + 11] = ca
            out[o + 12:o + 15] = cb
    return out
