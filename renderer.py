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


def pack_scene(p, w, h, steps, bounces, flags=0, quality=0):   # flags: bit0 anime, bit1 ray traced lighting, bit2 edge AA
    """Uniform block of neon3d.wgsl (512 bytes)."""
    a = np.zeros(128, np.float32)
    a[0:2] = (w, h)
    a[2], a[3] = p["time"], p["travel"]
    a[4], a[5], a[6], a[7] = p["fov"], p["bass"], p["mid"], p["high"]
    a[8], a[9], a[10], a[11] = p["kick"], p["snare"], p["hat"], p["build"]
    a[12], a[13], a[14], a[15] = p["drop"], p["explode"], p["collapse"], p["complexity"]
    a[16], a[17] = p["gain"], p["fade"]
    iv = a.view(np.uint32)
    iv[18], iv[19], iv[20] = p["gen"], steps, bounces
    iv[21], iv[22] = flags, quality
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
    return a.tobytes()


class Renderer:
    def __init__(self, headless=False, size=(1280, 720), title="Audio Organism", shader_dir_arg=None):
        self.headless = headless
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
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
        for name in ("neon3d", "bloom", "composite", "accum"):
            self.lib.load(name, name + ".wgsl")
        ok, msg = self.lib.status()
        if not ok:
            raise RuntimeError("Shader inicial com erro: " + msg)

        d = self.device
        self.u_scene = d.create_buffer(size=512, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.u_acc = d.create_buffer(size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.mblur, self.mblur_fps, self.dt = 180, 24, 1 / 60   # shutter angle (degrees), reference film rate, frame time (set by the app)
        self.u_comp = d.create_buffer(size=32, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.sampler = d.create_sampler(mag_filter="linear", min_filter="linear",
                                        address_mode_u="clamp-to-edge", address_mode_v="clamp-to-edge")
        self.pipes = {}
        self.pipe_errors = {}
        self._build_pipelines()
        self.res, self.steps, self.bounces = 100, 72, 1
        self.anime = True
        self.rt = True
        self.aa = True
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
                 "accum": [("accum", "vs", "fs", HDR)]}
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

    def _build_targets(self, w, h):
        s = max(0.25, min(1.0, self.res / 100.0))
        sw, sh = max(int(w * s), 16), max(int(h * s), 16)
        self.size, self.scene_size = (w, h), (sw, sh)
        self.scene = self._tex(sw, sh)
        self.scene_v = self.scene.create_view()
        # motion blur: `disp` = scene blended with the previous frame (what bloom and the composite read); `hist` = last `disp`
        self.disp, self.hist = self._tex(sw, sh, copy=True), self._tex(sw, sh, copy=True)
        self.disp_v, self.hist_v = self.disp.create_view(), self.hist.create_view()
        self.hist_valid = False
        self.levels = []
        src_w, src_h = sw, sh
        for i in range(BLOOM_LEVELS):
            lw, lh = max(w >> (i + 1), 2), max(h >> (i + 1), 2)
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
                                             entries=[self._entry(0, {"buffer": self.u_scene, "offset": 0, "size": 512})])}
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
            self._entry(4, lv[3]), self._entry(5, self.sampler), self._entry(6, {"buffer": self.u_comp, "offset": 0, "size": 32})])
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
        scene_size = (max(int(w * max(0.25, min(1.0, self.res / 100.0))), 16),
                      max(int(h * max(0.25, min(1.0, self.res / 100.0))), 16))
        if (w, h) != self.size or scene_size != self.scene_size or self.bind is None:
            if (w, h) != self.size or scene_size != self.scene_size:
                self._build_targets(w, h)
            self._build_bind()
        p = self.params
        d = self.device
        d.queue.write_buffer(self.u_scene, 0, pack_scene(p, *self.scene_size, self.steps, self.bounces,
                                                                     (1 if self.anime else 0) | (2 if self.rt else 0) | (4 if self.aa else 0),
                                                                     self.shadow_q | (self.ao_q << 4) | (self.refl_q << 8)))
        d.queue.write_buffer(self.u_comp, 0, np.array([self.bloom, self.flash, self.exposure, float(self.bloom_levels), *p.get("bg", (0.0, 0.0, 0.0)), p["fade"] * p["gain"]], np.float32).tobytes())
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
        self._pass(enc, tex.create_view(), self.pipes["comp"], self.bind["comp"])
        d.queue.submit([enc.finish()])

    def render(self, params):
        """Draw one frame. Returns the frame (H, W, 4 uint8) when headless."""
        self.params = params
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

    def closed(self):
        return False if self.headless else bool(self.canvas.get_closed())

    def close(self):
        try:
            self.canvas.close()
        except Exception:
            pass
