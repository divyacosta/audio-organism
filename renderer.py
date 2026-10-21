"""wgpu renderer: ray-marched 3D neon scene -> bloom chain -> composite (flash as Difference).

Runs on Vulkan or Direct3D 12 (the backend is chosen before wgpu is imported, see app.py).
Shaders live in ./shaders and are hot-reloaded.
"""
import os
import sys
import time

import numpy as np
import wgpu

from gpu_lib import ShaderLib

HDR = "rgba16float"
BLOOM_LEVELS = 4


def base_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def shader_dir():
    """A `shaders` folder next to the .exe (editable, hot-reloaded) wins over the copy bundled inside it."""
    if getattr(sys, "frozen", False):
        ext = os.path.join(os.path.dirname(sys.executable), "shaders")
        if os.path.isdir(ext) and os.path.exists(os.path.join(ext, "neon3d.wgsl")):
            return ext
    return os.path.join(base_dir(), "shaders")


PROF = {  # per scene profile: panel half size, layer offset, decay per layer (see the Facetas engine in neon3d.wgsl)
    0: ((0.52, 0.34), (0.70, 0.38), 0.84), 1: ((0.95, 0.075), (0.42, 0.22), 0.89), 2: ((0.62, 0.30), (0.55, 0.30), 0.86),
    3: ((0.50, 0.40), (0.75, 0.42), 0.82), 4: ((0.46, 0.33), (0.66, 0.36), 0.85), 5: ((0.92, 0.05), (0.50, 0.26), 0.88)}


def facet_tables(p, w, h, prof):
    """Per-frame scalars and per-layer tables of the Facetas distance function, so the GPU does not recompute them at every step."""
    import math
    aspect = w / max(h, 1)
    sx = min(8.0, max(1.0, aspect / 1.78)) ** 0.70
    sy = min(8.0, max(1.0, 1.78 / aspect)) ** 0.70
    n = min(7 + int(p["complexity"] * 4.0) + int((sx - 1.0) * 1.5 + (sy - 1.0) * 1.5), 12)
    sc = 1.0 - 0.35 * p["collapse"] + 0.6 * p["explode"]
    thick = 0.009 + 0.012 * p["bass"] + 0.010 * p["kick"]
    if prof == 1:
        thick *= 0.7
    elif prof == 2:
        thick *= 0.5
    elif prof == 3:
        thick = thick * 2.4 + 0.012 * p["kick"]
    elif prof == 4:
        thick = 0.016 + 0.020 * p["mid"] + 0.006 * p["high"]
    elif prof == 5:
        thick = 0.020 + 0.012 * p["bass"] + 0.012 * p["kick"]            # round sticks
    (psx, psy), (pox, poy), decay = PROF.get(prof, PROF[0])
    mnd = p.get("mandala")
    if mnd:                                                  # the scene's own numbers replace the character's
        psx, psy, pox, poy, decay = mnd["psx"], mnd["psy"], mnd["pox"], mnd["poy"], mnd["decay"]
        thick *= mnd["thick"]
        rnd, glass = float(mnd["round"]), float(mnd["glass"])
    else:
        rnd, glass = (1.0 if prof == 4 else (2.0 if prof == 5 else 0.0)), (0.4 if prof == 2 else 1.0)
    fn = min(1.0, max(0.0, p.get("funnel", 0.0)))
    t, seed = p["time"], p["seed"]
    tiers = p.get("tier_uni", (0, 1, 2))
    trig, szs = [], []
    rot = p.get("rot", t * 0.10 * (1.0 + 0.6 * p["build"]))
    rdir = p.get("rdir", 0)
    pulse = 1.0 + p.get("pulse", 0.0)
    for i in range(12):
        uni = tiers[0 if i < 4 else (1 if i < 8 else 2)]
        ang = seed[0] * 3.0 + uni * 1.9 + i * 0.75 + (1.0 if (i % 2 == 0 or rdir != 2) else -1.0) * (-1.0 if rdir == 1 else 1.0) * rot
        tilt = 0.55 + seed[1] * 1.4 + uni * 0.8 + 0.45 * math.sin(t * 0.27 + i * 1.3)
        trig.append((math.cos(ang), math.sin(ang), math.cos(tilt), math.sin(tilt)))
        wave = 1.0 + 0.40 * fn * math.sin(p["travel"] * 1.1 - i * 0.9)
        szs.append((decay ** i * wave * pulse, (1.0 - fn) + fn * 0.80 ** i, (p.get("roll", 0.0) if i == 0 else (p.get("dist", 9.0) if i == 1 else 0.0)), (p.get("fov", 2.0) if i == 0 else 0.0)))
    return (sx, sy, float(n), sc), (psx, psy, pox, poy), (thick, 1.0 if prof in (1, 5) else 0.0, rnd, glass), trig, szs


def pack_scene(p, w, h, steps, bounces, flags=0, quality=0, prof=0):   # flags: bit0 anime, bit1 ray traced lighting, bit2 edge AA
    """Uniform block of neon3d.wgsl (1152 bytes)."""
    a = np.zeros(288, np.float32)
    a[0:2] = (w, h)
    a[2], a[3] = p["time"], p["travel"]
    a[4], a[5], a[6], a[7] = p["fov"], p["bass"], p["mid"], p["high"]
    a[8], a[9], a[10], a[11] = p["kick"], p["snare"], p["hat"], p["build"]
    a[12], a[13], a[14], a[15] = p["drop"], p["explode"], p["collapse"], p["complexity"]
    a[16], a[17] = p["gain"], p["fade"]
    iv = a.view(np.uint32)
    iv[18], iv[19], iv[20] = p["gen"], steps, bounces
    iv[21], iv[22], iv[23] = flags, quality, prof
    a[24:28] = p["seed"]
    a[28:31] = p["cam"]
    a[31] = p.get("funnel", 0.0)
    for i, col in enumerate(p["pal"]):
        a[32 + i * 4: 35 + i * 4] = col
    tiers, modes = p.get("tier_uni", (0, 1, 2)), p.get("modes", (0, 2, 3))
    scales = p.get("layer_scale") or [1.0] * 12
    variants = p.get("layer_var") or [0] * 12
    for i in range(12):
        uni = tiers[0 if i < 4 else (1 if i < 8 else 2)]
        a[44 + i * 4: 48 + i * 4] = (uni, modes[uni], scales[i], variants[i])
    for k, pal in enumerate(p.get("upals") or ()):
        for j, col in enumerate(pal):
            a[92 + (k * 3 + j) * 4: 95 + (k * 3 + j) * 4] = col
    geo, prm0, prm1, trig, szs = facet_tables(p, w, h, prof)
    a[128:132], a[132:136], a[136:140] = geo, prm0, prm1
    a[140:188] = np.array(trig, np.float32).ravel()
    a[188:236] = np.array(szs, np.float32).ravel()
    shp = p.get("shapes")
    if shp:
        a[236:284] = np.array(shp, np.float32).ravel()                       # per layer: shape A, shape B, morph, unused
    a[284:288] = p.get("mat", (1.0, 1.0, 1.0, 0.0))                         # the shader preset's numbers
    return a.tobytes()


class Renderer:
    def __init__(self, headless=False, size=(1280, 720), title="Audio Organism", shader_dir_arg=None, power="high-performance", on_wait=None):
        self.headless = headless
        adapter = wgpu.gpu.request_adapter_sync(power_preference=power)
        self.device = adapter.request_device_sync()
        self.adapter = adapter
        info = adapter.info
        self.gpu_name = str(info.get("device"))
        self.backend = str(info.get("backend_type"))
        if headless:
            from rendercanvas.offscreen import RenderCanvas
            self.canvas = RenderCanvas(size=size, pixel_ratio=1.0, format="rgba-u8")
        else:
            from rendercanvas.glfw import RenderCanvas
            self.canvas = RenderCanvas(size=size, title=title, update_mode="ondemand", vsync=False)
        self.context = self.canvas.get_wgpu_context()
        self.fmt = self.context.get_preferred_format(adapter)
        if not headless:
            try:
                self.context.configure(device=self.device, format="bgra8unorm")   # non-sRGB: keeps the raw neon look
                self.fmt = "bgra8unorm"
            except Exception:
                self.context.configure(device=self.device, format=self.fmt)
        else:
            try:
                self.context.configure(device=self.device, format="rgba8unorm")      # same non-sRGB look as the window
                self.fmt = "rgba8unorm"
            except Exception:
                self.context.configure(device=self.device, format=self.fmt)
        self.vsync = False

        self.lib = ShaderLib(self.device, shader_dir_arg or shader_dir())
        for name in ("neon3d", "bloom", "composite", "accum", "fxaa"):
            self.lib.load(name, name + ".wgsl")
        ok, msg = self.lib.status()
        if not ok:
            raise RuntimeError("Shader inicial com erro: " + msg)

        d = self.device
        self.u_scene = d.create_buffer(size=1152, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.u_acc = d.create_buffer(size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.mblur, self.mblur_fps, self.dt = 180, 24, 1 / 60   # shutter angle (degrees), reference film rate, frame time (set by the app)
        self.u_fx = d.create_buffer(size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.u_blit = d.create_buffer(size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.u_comp = d.create_buffer(size=144, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.sampler = d.create_sampler(mag_filter="linear", min_filter="linear",
                                        address_mode_u="clamp-to-edge", address_mode_v="clamp-to-edge")
        self.pipes = {}
        self.pipe_errors = {}
        if on_wait is None:
            self._build_pipelines()
        else:                                      # the first launch after an update compiles the shaders for a while: do it in a thread so
            import threading                       # the program can keep a window alive (on_wait is called about 20 times a second)
            th = threading.Thread(target=self._build_pipelines, daemon=True)
            th.start()
            while th.is_alive():
                on_wait()
                time.sleep(0.05)
            th.join()
        self.res, self.steps, self.bounces = 100, 72, 1
        self.style = 0                 # image style: 0 = 3D, 1 = neon, 2 = holograma
        self.duo = False               # duotone post-process
        self.rt = True
        self.aa = True                 # analytic edge anti-aliasing
        self.fxaa = False              # FXAA pass over the finished picture
        self.preview = False           # keep a small copy of the finished picture (the thumbnail in the settings tabs)
        self.preview_every = 8         # frames between two thumbnails (the read-back waits for the GPU, so it is rare)
        self.preview_rgba, self.preview_size, self.preview_n = None, (320, 180), 0
        self._pv_count = 0
        self.preview_err = None        # why the last read-back failed (shown in the panel when the preview stays empty)
        self.msaa = 0                  # extra samples on edge pixels: 0 off, 1 = 2x, 2 = 4x, 3 = 8x
        self.sharp = 0.0               # sharpening amount (composite)
        self.bloom_shift = 1           # bloom base size = window >> shift
        self.dist = 9.0                # how far past the first layer the rays travel
        self._bs = 1
        self.shadow_q, self.ao_q, self.refl_q, self.bloom_levels = 2, 2, 2, 3     # graphics quality knobs (menu "Gráficos")
        self.size = (0, 0)
        self.scene_size = (0, 0)
        self.params = None
        self.exposure, self.bloom, self.flash = 1.1, 0.6, 0.0
        self.events = []
        self._win_state = None
        self.fullscreen = False
        self.canvas.add_event_handler(lambda e: self.events.append(e), "key_down", "double_click",
                                      "pointer_move", "pointer_down", "close")
        self.canvas.request_draw(self._draw)

    # ----------------------------------------------------------------- pipelines
    def _pipe(self, shader, vs, fs, fmt):
        return self.device.create_render_pipeline(
            layout="auto",
            vertex={"module": shader.module, "entry_point": vs},
            fragment={"module": shader.module, "entry_point": fs, "targets": [{"format": fmt}]},
            primitive={"topology": "triangle-list"})

    def _build_pipelines(self, only=None):
        specs = {"neon3d": [("scene", "vs", "fs", HDR)],
                 "bloom": [("down", "vs", "fs_down", HDR), ("blur", "vs", "fs_blur", HDR)],
                 "composite": [("comp", "vs", "fs", None)],
                 "accum": [("accum", "vs", "fs", HDR)],
                 "fxaa": [("fxaa", "vs", "fs", None)]}
        for name, items in specs.items():
            if only and name != only:
                continue
            sh = self.lib.shaders[name]
            for key, vs, fs, fmt in items:
                try:
                    self.pipes[key] = self._pipe(sh, vs, fs, fmt or self.fmt)
                    self.pipe_errors.pop(name, None)
                except Exception as e:
                    self.pipe_errors[name] = str(e).strip().splitlines()[0][:110] if str(e).strip() else "erro"
        self.bind = None          # bind groups depend on pipelines: rebuilt lazily

    def poll_shaders(self):
        """Hot reload. Returns names of shaders that were rebuilt successfully."""
        changed = self.lib.poll()
        for sh in changed:
            self._build_pipelines(only=sh.name)
        return [s.name for s in changed]

    def shader_status(self):
        ok, msg = self.lib.status()
        if ok and self.pipe_errors:
            n, m = next(iter(self.pipe_errors.items()))
            return False, f"{n}.wgsl: {m}"
        return ok, msg

    # ------------------------------------------------------------------ targets
    def _tex(self, w, h, copy=False):
        use = wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.TEXTURE_BINDING
        if copy:
            use |= wgpu.TextureUsage.COPY_SRC | wgpu.TextureUsage.COPY_DST
        return self.device.create_texture(size=(max(w, 2), max(h, 2), 1), format=HDR, usage=use)

    def _ubuf(self, vals):
        return self.device.create_buffer_with_data(data=np.array(vals, np.float32).tobytes(), usage=wgpu.BufferUsage.UNIFORM)

    def _scene_dims(self, w, h):
        s = max(0.25, min(2.0, self.res / 100.0))                  # above 100 % the scene is rendered larger than the window (supersampling)
        s = min(s, 8192.0 / max(w, h, 1))
        return max(int(w * s), 16), max(int(h * s), 16)

    def _build_targets(self, w, h):
        sw, sh = self._scene_dims(w, h)
        self.size, self.scene_size = (w, h), (sw, sh)
        self.scene = self._tex(sw, sh)
        self.ldr = self.device.create_texture(size=(max(w, 2), max(h, 2), 1), format=self.fmt,
                                              usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.TEXTURE_BINDING)
        self.ldr_v = self.ldr.create_view()
        self._bs = self.bloom_shift
        self.device.queue.write_buffer(self.u_fx, 0, np.array([1.0 / max(w, 2), 1.0 / max(h, 2), 1.0, 0.0], np.float32).tobytes())
        self.device.queue.write_buffer(self.u_blit, 0, np.array([1.0 / max(w, 2), 1.0 / max(h, 2), 0.0, 0.0], np.float32).tobytes())
        pw, ph = self.preview_size
        self.ptex = self.device.create_texture(size=(pw, ph, 1), format=self.fmt,
                                               usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC)
        self.ptex_v = self.ptex.create_view()
        self.pbuf = self.device.create_buffer(size=pw * 4 * ph, usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.COPY_DST)
        self.scene_v = self.scene.create_view()
        # motion blur: `disp` = scene blended with the previous frame (what bloom and the composite read); `hist` = last `disp`
        self.disp, self.hist = self._tex(sw, sh, copy=True), self._tex(sw, sh, copy=True)
        self.disp_v, self.hist_v = self.disp.create_view(), self.hist.create_view()
        self.hist_valid = False
        self.levels = []
        src_w, src_h = sw, sh
        for i in range(BLOOM_LEVELS):
            lw, lh = max(w >> (i + self.bloom_shift), 2), max(h >> (i + self.bloom_shift), 2)
            down, tmp, lv = self._tex(lw, lh), self._tex(lw, lh), self._tex(lw, lh)
            self.levels.append(dict(
                down=down, tmp=tmp, lv=lv, dv=down.create_view(), tv=tmp.create_view(), lvv=lv.create_view(),
                pd=self._ubuf([1.0 / src_w, 1.0 / src_h, 0.45 if i == 0 else 0.0, 0.0]),
                ph=self._ubuf([1.0 / lw, 0.0, 0.0, 0.0]), pv=self._ubuf([0.0, 1.0 / lh, 0.0, 0.0])))
            src_w, src_h = lw, lh
        self.bind = None

    def _entry(self, binding, res):
        return {"binding": binding, "resource": res}

    def _build_bind(self):
        d, pipes = self.device, self.pipes
        bind = {"scene": d.create_bind_group(layout=pipes["scene"].get_bind_group_layout(0),
                                             entries=[self._entry(0, {"buffer": self.u_scene, "offset": 0, "size": 1152})])}
        bind["accum"] = d.create_bind_group(layout=pipes["accum"].get_bind_group_layout(0), entries=[
            self._entry(0, self.scene_v), self._entry(1, self.hist_v), self._entry(2, self.sampler),
            self._entry(3, {"buffer": self.u_acc, "offset": 0, "size": 16})])
        src = self.disp_v
        lv = []
        for L in self.levels:
            def grp(pipe, view, buf):
                return d.create_bind_group(layout=pipe.get_bind_group_layout(0), entries=[
                    self._entry(0, view), self._entry(1, self.sampler), self._entry(2, {"buffer": buf, "offset": 0, "size": 16})])
            L["g_down"] = grp(pipes["down"], src, L["pd"])
            L["g_h"] = grp(pipes["blur"], L["dv"], L["ph"])
            L["g_v"] = grp(pipes["blur"], L["tv"], L["pv"])
            src = L["lvv"]
            lv.append(L["lvv"])
        bind["comp"] = d.create_bind_group(layout=pipes["comp"].get_bind_group_layout(0), entries=[
            self._entry(0, self.disp_v), self._entry(1, lv[0]), self._entry(2, lv[1]), self._entry(3, lv[2]),
            self._entry(4, lv[3]), self._entry(5, self.sampler), self._entry(6, {"buffer": self.u_comp, "offset": 0, "size": 144})])
        bind["fxaa"] = d.create_bind_group(layout=pipes["fxaa"].get_bind_group_layout(0), entries=[
            self._entry(0, self.ldr_v), self._entry(1, self.sampler), self._entry(2, {"buffer": self.u_fx, "offset": 0, "size": 16})])
        bind["blit"] = d.create_bind_group(layout=pipes["fxaa"].get_bind_group_layout(0), entries=[
            self._entry(0, self.ldr_v), self._entry(1, self.sampler), self._entry(2, {"buffer": self.u_blit, "offset": 0, "size": 16})])
        self.bind = bind

    # ---------------------------------------------------------------------- draw
    def _pass(self, enc, view, pipe, group):
        rp = enc.begin_render_pass(color_attachments=[{"view": view, "clear_value": (0, 0, 0, 1),
                                                       "load_op": "clear", "store_op": "store"}])
        rp.set_pipeline(pipe)
        rp.set_bind_group(0, group)
        rp.draw(3)
        rp.end()

    def _draw(self):
        tex = self.context.get_current_texture()
        w, h = tex.width, tex.height
        scene_size = self._scene_dims(w, h)
        if (w, h) != self.size or scene_size != self.scene_size or self.bind is None or self._bs != self.bloom_shift:
            if (w, h) != self.size or scene_size != self.scene_size or self._bs != self.bloom_shift:
                self._build_targets(w, h)
            self._build_bind()
        p = self.params
        p["dist"] = self.dist
        d = self.device
        d.queue.write_buffer(self.u_scene, 0, pack_scene(p, *self.scene_size, self.steps, self.bounces,
                                                                     (2 if self.rt else 0) | (4 if self.aa else 0) | (self.style << 8) | (max(0, min(3, int(self.msaa))) << 12),
                                                                     self.shadow_q | (self.ao_q << 4) | (self.refl_q << 8), p.get("prof", 0)))
        d.queue.write_buffer(self.u_comp, 0, np.array([self.bloom, self.flash, self.exposure, float(self.bloom_levels), *p.get("bg", (0.0, 0.0, 0.0)), p["fade"] * p["gain"],
                                                      0.0, p["time"], float(self.sharp), float(p.get("duo_contrast", 1.0)),
                                                      *(p.get("duo") or ((0, 0, 0), (1, 1, 1)))[0], 1.0 if self.duo else 0.0, *(p.get("duo") or ((0, 0, 0), (1, 1, 1)))[1], 0.0,
                                                      *self._lights_block(p)], np.float32).tobytes())
        enc = d.create_command_encoder()
        self._pass(enc, self.scene_v, self.pipes["scene"], self.bind["scene"])
        # motion blur by SHUTTER ANGLE, as in cinema: the shutter is open for (angle / 360) of one frame of the reference film rate, so
        # 180 deg at 24 fps = 1/48 s, 360 deg = 1/24 s. The trail is an exponential filter over that exposure time, independent of the
        # real frame rate. A hard cut resets the trail.
        exposure = max(0.0, min(720.0, self.mblur)) / 360.0 / max(self.mblur_fps, 1.0)
        tau = 0.4 * exposure
        k = float(np.exp(-max(self.dt, 1e-3) / tau)) if tau > 1e-4 else 0.0
        if not self.hist_valid or p.get("hardcut"):
            k = 0.0
        d.queue.write_buffer(self.u_acc, 0, np.array([k, 0.0, 0.0, 0.0], np.float32).tobytes())
        self._pass(enc, self.disp_v, self.pipes["accum"], self.bind["accum"])
        enc.copy_texture_to_texture({"texture": self.disp}, {"texture": self.hist}, (self.scene_size[0], self.scene_size[1], 1))
        self.hist_valid = True
        for L in self.levels[:max(0, min(BLOOM_LEVELS, self.bloom_levels))]:      # unused bloom levels cost nothing
            self._pass(enc, L["dv"], self.pipes["down"], L["g_down"])
            self._pass(enc, L["tv"], self.pipes["blur"], L["g_h"])
            self._pass(enc, L["lvv"], self.pipes["blur"], L["g_v"])
        self._pv_count += 1
        want_pv = self.preview and self._pv_count % max(1, self.preview_every) == 0
        if self.fxaa or want_pv:
            self._pass(enc, self.ldr_v, self.pipes["comp"], self.bind["comp"])
            self._pass(enc, tex.create_view(), self.pipes["fxaa"], self.bind["fxaa" if self.fxaa else "blit"])
            if want_pv:                                    # a small copy of the finished picture, for the thumbnail
                self._pass(enc, self.ptex_v, self.pipes["fxaa"], self.bind["blit"])
                enc.copy_texture_to_buffer({"texture": self.ptex}, {"buffer": self.pbuf, "bytes_per_row": self.preview_size[0] * 4},
                                           (self.preview_size[0], self.preview_size[1], 1))
        else:
            self._pass(enc, tex.create_view(), self.pipes["comp"], self.bind["comp"])
        d.queue.submit([enc.finish()])
        if want_pv:
            try:
                self.pbuf.map_sync(wgpu.MapMode.READ)
                self.preview_rgba = bytes(self.pbuf.read_mapped())
                self.pbuf.unmap()
                self.preview_n += 1
            except Exception as e:
                self.preview_rgba = None
                self.preview_err = repr(e)[:90]

    def _lights_block(self, p):
        """The 16 floats of the background lights: style / intensity / speed / blank, two colours with bass and kick, then mid, high, beat and aspect."""
        lg = p.get("lights") or (0, 1.0, 1.0)
        pal = p.get("pal") or ((1.0, 0.3, 0.8), (0.2, 0.8, 1.0))
        ca = pal[0][:3]
        cb = pal[1][:3] if len(pal) > 1 else ca
        w, h = self.size
        return [float(lg[0]), float(lg[1]), float(lg[2]), 1.0 if p.get("blank") else 0.0,
                ca[0], ca[1], ca[2], float(p.get("bass", 0.0)),
                cb[0], cb[1], cb[2], float(p.get("kick", 0.0)),
                float(p.get("mid", 0.0)), float(p.get("high", 0.0)), float(p.get("beat", p.get("time", 0.0) * 2.0)), w / max(h, 1)]

    def render(self, params):
        """Draw one frame. Returns the frame (H, W, 4 uint8) when headless."""
        self.params = params
        if not self.headless and self.minimized():
            time.sleep(0.03)                              # nothing to see: do not spend the GPU (nor spin the CPU)
            return None
        if self.headless:
            self.canvas.request_draw(self._draw)
            return np.asarray(self.canvas.draw())
        self.canvas.force_draw()
        return None

    # --------------------------------------------------------------- window glue
    def set_vsync(self, on):
        """Reconfigure the surface with the other present mode."""
        if self.headless or on == self.vsync:
            return True
        try:
            self.canvas._vsync = bool(on)
            self.context._wgpu_context._present_info["vsync"] = bool(on)     # read by wgpu when the surface is configured
            self.context.configure(device=self.device, format=self.fmt)
            self.vsync = bool(on)
            return True
        except Exception:
            self.canvas._vsync = self.vsync
            return False

    def _glfw(self):
        import glfw
        return glfw, self.canvas._window

    def set_fullscreen(self, on):
        if self.headless or on == self.fullscreen:
            return
        glfw, win = self._glfw()
        if on:
            x, y = glfw.get_window_pos(win)
            w, h = glfw.get_window_size(win)
            self._win_state = (x, y, w, h)
            mon, best = glfw.get_primary_monitor(), None
            for m in glfw.get_monitors():                       # the monitor the window is on
                mx, my = glfw.get_monitor_pos(m)
                mode = glfw.get_video_mode(m)
                if mx <= x + w // 2 < mx + mode.size.width and my <= y + h // 2 < my + mode.size.height:
                    best = m
            mon = best or mon
            mode = glfw.get_video_mode(mon)
            glfw.set_window_monitor(win, mon, 0, 0, mode.size.width, mode.size.height, mode.refresh_rate)
        else:
            x, y, w, h = self._win_state or (30, 40, 1280, 720)
            glfw.set_window_monitor(win, None, x, y, w, h, 0)
        self.fullscreen = on

    def set_title(self, text):
        if self.headless:
            return
        glfw, win = self._glfw()
        glfw.set_window_title(win, text)

    def hide_cursor(self, hide):
        if self.headless:
            return
        glfw, win = self._glfw()
        glfw.set_input_mode(win, glfw.CURSOR, glfw.CURSOR_HIDDEN if hide else glfw.CURSOR_NORMAL)

    def place_window(self, x, y):
        if not self.headless:
            glfw, win = self._glfw()
            glfw.set_window_pos(win, x, y)

    def poll_events(self):
        if not self.headless:
            import glfw
            glfw.poll_events()
        ev, self.events = self.events, []
        return ev

    def minimized(self):
        try:
            glfw, win = self._glfw()
            return bool(glfw.get_window_attrib(win, glfw.ICONIFIED))
        except Exception:
            return False

    def closed(self):
        return False if self.headless else bool(self.canvas.get_closed())

    def close(self):
        try:
            self.canvas.close()
        except Exception:
            pass
