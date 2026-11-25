"""wgpu renderer: ray-marched 3D neon scene -> bloom chain -> composite (flash as Difference).

Runs on Vulkan or Direct3D 12 (the backend is chosen before wgpu is imported, see app.py).
Shaders live in ./shaders and are hot-reloaded.
"""
import os
import sys
import time

import numpy as np
import prof

import layers as LY
from fxstack import FxStack, pack_bg
import wgpu

from gpu_lib import ShaderLib

HDR = "rgba16float"
PART_MAX = 262144

# the words over the picture (osd.py): one textured quad with alpha, drawn after everything else on the window only (never on the thumbnails)
OSD_WGSL = """
struct U { rect: vec4<f32>, a: vec4<f32> };
@group(0) @binding(0) var<uniform> u: U;
@group(0) @binding(1) var tex: texture_2d<f32>;
@group(0) @binding(2) var smp: sampler;
struct VO { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32> };
@vertex fn vs(@builtin(vertex_index) i: u32) -> VO {
    var c = array<vec2<f32>, 6>(vec2<f32>(0.0, 0.0), vec2<f32>(1.0, 0.0), vec2<f32>(0.0, 1.0), vec2<f32>(0.0, 1.0), vec2<f32>(1.0, 0.0), vec2<f32>(1.0, 1.0));
    let p = c[i];
    var o: VO;
    o.pos = vec4<f32>(mix(u.rect.x, u.rect.z, p.x), mix(u.rect.y, u.rect.w, p.y), 0.0, 1.0);
    o.uv = p;
    return o;
}
@fragment fn fs(i: VO) -> @location(0) vec4<f32> {
    let t = textureSample(tex, smp, i.uv);
    return vec4<f32>(t.rgb, t.a * u.a.x);
}
"""


def halton(i, base):
    f, r = 1.0, 0.0
    while i > 0:
        f /= base
        r += f * (i % base)
        i //= base
    return r
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
        rnd, glass = float(mnd["round"]), (float(mnd["glass"]) if p.get("glass_on", True) else 1.0)
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


def pack_gen(p, aspect, logo_aspect, kind):
    """Uniform block of generators.wgsl (480 bytes): time, aspect, kind and gain; the sound; the three settings of the visual; two colours; 32 bands and 64 samples."""
    pal = p.get("pal") or ((1.0, 0.3, 0.8), (0.2, 0.8, 1.0))
    c0, c1 = pal[0][:3], (pal[1][:3] if len(pal) > 1 else pal[0][:3])
    gp = p.get("gen_p") or (50, 50, 50)
    a = [float(p.get("time", 0.0)), float(aspect), float(kind), float(p.get("fade", 1.0)) * float(p.get("gain", 1.0))]
    b = [float(p.get("bass", 0.0)), float(p.get("mid", 0.0)), float(p.get("high", 0.0)), float(p.get("kick", 0.0))]
    c = [float(p.get("beat", 0.0)), float(p.get("energy", 0.0)), float(p.get("tension", 0.0)), float(p.get("drop", 0.0))]
    d = [gp[0] / 100.0, gp[1] / 100.0, gp[2] / 100.0, float(logo_aspect)]
    bands = np.zeros(32, np.float32)
    bw = p.get("bands32")
    if bw is not None:
        bands[:len(bw)] = bw[:32]
    wave = np.zeros(64, np.float32)
    ww = p.get("wave64")
    if ww is not None:
        wave[:len(ww)] = ww[:64]
    return np.concatenate((np.array(a + b + c + d + [*c0, 1.0] + [*c1, 1.0], np.float32), bands, wave)).astype(np.float32).tobytes()


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
        for name in ("neon3d", "bloom", "composite", "accum", "fxaa", "taa", "feedback", "particles", "post", "generators"):
            self.lib.load(name, name + ".wgsl")
        ok, msg = self.lib.status()
        if not ok:
            raise RuntimeError("Shader inicial com erro: " + msg)

        d = self.device
        self.u_scene = d.create_buffer(size=1152, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.u_acc = d.create_buffer(size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.mblur, self.mblur_fps, self.dt = 180, 24, 1 / 60   # shutter angle (degrees), reference film rate, frame time (set by the app)
        self.u_fx = d.create_buffer(size=96, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.u_blit = d.create_buffer(size=96, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.u_comp = d.create_buffer(size=480, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.u_post = [d.create_buffer(size=64, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST) for _ in range(LY.MAX_FX)]       # one per effect pass
        self.stack = FxStack()                  # the layers of the scene as the passes need them (fxstack.py)
        self.u_taa = d.create_buffer(size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.u_fb = d.create_buffer(size=32, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.u_part = d.create_buffer(size=80, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.u_gen = d.create_buffer(size=512, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)       # the visual generators (generators.wgsl)
        self.logo_key, self.logo_aspect, self.logo_tex = None, 1.0, None
        self._set_logo_pixels(b"\xff" * 16, 2, 2)
        self.ov_on, self.ov, self.ov_key, self.ov_aspect = False, (0, 10.0, 0.9, 0), None, 1.0       # the Sobreposição: on, (where, size %, opacity, what it follows), its picture
        self._set_overlay_pixels(b"\x00" * 16, 2, 2)
        self.osd_a, self.osd_key, self.osd_size, self.osd_tex = 0.0, None, (0, 0), None          # the words over the picture: opacity (0 draws nothing), what they say, their size
        self._osd_pipe = self._osd_bind = None
        self.u_osd = d.create_buffer(size=32, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.parts =d.create_buffer(size=PART_MAX * 32, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST)       # the particles (see particles.wgsl)
        self.parts_init = False
        self.taa = False               # temporal anti-aliasing (jittered scene + history)
        self._jit_i = 0
        self.sampler = d.create_sampler(mag_filter="linear", min_filter="linear",
                                        address_mode_u="clamp-to-edge", address_mode_v="clamp-to-edge")
        self.pipes = {}
        self.pipe_errors = {}
        self._build_osd()
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
        self.monitor_pick = 0           # 0 = where the window is, 1.. = that monitor (Ajustes)
        self.flash_mode = 0            # how the flash is laid over the picture: 0 inverts it (Difference), 1 a white glow (added)
        self.preview = False           # keep a small copy of the finished picture (the thumbnail in the settings tabs)
        self.preview_every = 8         # frames between two thumbnails (the read-back waits for the GPU, so it is rare)
        self.preview_rgba, self.preview_size, self.preview_n = None, (320, 180), 0
        self._pv_count = 0
        self.preview_err = None        # why the last read-back failed (shown in the panel when the preview stays empty)
        self.msaa = 0                  # extra samples on edge pixels: 0 off, 1 = 2x, 2 = 4x, 3 = 8x
        self.sharp = 0.0               # sharpening amount (composite)
        self.fx_trail = self.fx_parts = True       # Sistema > Imagem > Efeitos pesados: the trail and particle layers may be left out
        self.fin = (1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 4.0)   # the last pass: brightness, contrast, saturation, gamma, warmth, vignette, dither, mirror, zoom, aspect, style (0 normal, 1 flat, 2 lines, 3 pixels), pixel size (the neutral values draw nothing)
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
                 "fxaa": [("fxaa", "vs", "fs", None)],
                 "taa": [("taa", "vs", "fs", HDR)],
                 "feedback": [("fb", "vs", "fs", HDR)],
                 "post": [("post", "vs", "fs", None)],
                 "generators": [("gen", "vs", "fs", HDR)]}
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
        if not only or only == "particles":
            try:
                sh = self.lib.shaders["particles"]
                add = {"src_factor": "one", "dst_factor": "one", "operation": "add"}
                self.pipes["p_up"] = self.device.create_compute_pipeline(layout="auto", compute={"module": sh.module, "entry_point": "update"})
                self.pipes["p_draw"] = self.device.create_render_pipeline(
                    layout="auto", vertex={"module": sh.module, "entry_point": "vs"},
                    fragment={"module": sh.module, "entry_point": "fs", "targets": [{"format": HDR, "blend": {"color": add, "alpha": add}}]},
                    primitive={"topology": "triangle-list"})
                self.pipe_errors.pop("particles", None)
            except Exception as e:
                self.pipe_errors["particles"] = str(e).strip().splitlines()[0][:110] if str(e).strip() else "erro"
        self.bind = None          # bind groups depend on pipelines: rebuilt lazily

    def _build_osd(self):
        """The pipeline of the words over the picture. A courtesy, never a risk: when it cannot be built (or VIS_NO_OSD is set) there are no words and the
        picture goes on as before."""
        if os.environ.get("VIS_NO_OSD"):
            return
        try:
            mod = self.device.create_shader_module(code=OSD_WGSL, label="osd")
            over = {"src_factor": "src-alpha", "dst_factor": "one-minus-src-alpha", "operation": "add"}
            keep = {"src_factor": "one", "dst_factor": "one-minus-src-alpha", "operation": "add"}
            self._osd_pipe = self.device.create_render_pipeline(
                layout="auto", vertex={"module": mod, "entry_point": "vs"},
                fragment={"module": mod, "entry_point": "fs", "targets": [{"format": self.fmt, "blend": {"color": over, "alpha": keep}}]},
                primitive={"topology": "triangle-list"})
        except Exception:
            self._osd_pipe = None

    def set_osd(self, key, rgba, w, h):
        """The words of the picture window as a picture (osd.py). Cheap when it is the one already there; does nothing when the overlay could not be built."""
        if self._osd_pipe is None or key == self.osd_key:
            return
        try:
            d = self.device
            tex = d.create_texture(size=(w, h, 1), format="rgba8unorm", usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST)
            d.queue.write_texture({"texture": tex}, rgba, {"bytes_per_row": w * 4, "rows_per_image": h}, (w, h, 1))
            self._osd_bind = d.create_bind_group(layout=self._osd_pipe.get_bind_group_layout(0), entries=[
                self._entry(0, {"buffer": self.u_osd, "offset": 0, "size": 32}), self._entry(1, tex.create_view()), self._entry(2, self.sampler)])
            self.osd_tex, self.osd_size, self.osd_key = tex, (w, h), key
        except Exception:
            self._osd_pipe = None

    def _osd_pass(self, enc, view, w, h):
        """The words, centred near the bottom of the window, over what is already there."""
        ow, oh = self.osd_size
        x0, y1 = (w - ow) * 0.5, h * 0.94
        y0 = y1 - oh
        self.device.queue.write_buffer(self.u_osd, 0, np.array([x0 / w * 2 - 1, 1 - y0 / h * 2, (x0 + ow) / w * 2 - 1, 1 - y1 / h * 2, self.osd_a, 0.0, 0.0, 0.0],
                                                               np.float32).tobytes())
        rp = enc.begin_render_pass(color_attachments=[{"view": view, "load_op": "load", "store_op": "store"}])
        rp.set_pipeline(self._osd_pipe)
        rp.set_bind_group(0, self._osd_bind)
        rp.draw(6)
        rp.end()

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
        self.ldr_b = self.device.create_texture(size=(max(w, 2), max(h, 2), 1), format=self.fmt,
                                                usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.TEXTURE_BINDING)       # the other one of the pair the effect passes alternate between
        self.ldr_b_v = self.ldr_b.create_view()
        self._bs = self.bloom_shift
        self.device.queue.write_buffer(self.u_fx, 0, np.array([1.0 / max(w, 2), 1.0 / max(h, 2), 1.0, 0.0], np.float32).tobytes())
        self.device.queue.write_buffer(self.u_blit, 0, np.array([1.0 / max(w, 2), 1.0 / max(h, 2), 0.0, 0.0], np.float32).tobytes())
        pw, ph = self.preview_size
        self.ptex = self.device.create_texture(size=(pw, ph, 1), format=self.fmt,
                                               usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC)
        self.ptex_v = self.ptex.create_view()
        self.pbufs = [self.device.create_buffer(size=pw * 4 * ph, usage=wgpu.BufferUsage.MAP_READ | wgpu.BufferUsage.COPY_DST) for _ in range(3)]       # a ring: the copy of
        self._pv_queue = []                                              # a frame is read two frames later, when the GPU has long finished it (no wait)
        self.scene_v = self.scene.create_view()
        # motion blur: `disp` = scene blended with the previous frame (what bloom and the composite read); `hist` = last `disp`
        self.disp, self.hist = self._tex(sw, sh, copy=True), self._tex(sw, sh, copy=True)
        self.disp_v, self.hist_v = self.disp.create_view(), self.hist.create_view()
        self.hist_valid = False
        self.taa_out, self.taa_hist = self._tex(sw, sh, copy=True), self._tex(sw, sh, copy=True)       # TAA result and its history
        self.fbo, self.fb_hist = self._tex(sw, sh, copy=True), self._tex(sw, sh, copy=True)             # feedback result and its history
        self.taa_out_v, self.taa_hist_v = self.taa_out.create_view(), self.taa_hist.create_view()
        self.fbo_v, self.fb_hist_v = self.fbo.create_view(), self.fb_hist.create_view()
        self.taa_valid = False
        self.fb_valid = False
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
        if "gen" in pipes:
            bind["gen"] = d.create_bind_group(layout=pipes["gen"].get_bind_group_layout(0), entries=[
                self._entry(0, {"buffer": self.u_gen, "offset": 0, "size": 512}), self._entry(1, self.logo_tex.create_view()), self._entry(2, self.sampler)])
        bind["accum"] = d.create_bind_group(layout=pipes["accum"].get_bind_group_layout(0), entries=[
            self._entry(0, self.scene_v), self._entry(1, self.hist_v), self._entry(2, self.sampler),
            self._entry(3, {"buffer": self.u_acc, "offset": 0, "size": 16})])
        bind["accum_taa"] = d.create_bind_group(layout=pipes["accum"].get_bind_group_layout(0), entries=[
            self._entry(0, self.taa_out_v), self._entry(1, self.hist_v), self._entry(2, self.sampler),
            self._entry(3, {"buffer": self.u_acc, "offset": 0, "size": 16})])
        bind["taa"] = d.create_bind_group(layout=pipes["taa"].get_bind_group_layout(0), entries=[
            self._entry(0, self.scene_v), self._entry(1, self.taa_hist_v), self._entry(2, self.sampler),
            self._entry(3, {"buffer": self.u_taa, "offset": 0, "size": 16})])
        bind["fb"] = d.create_bind_group(layout=pipes["fb"].get_bind_group_layout(0), entries=[
            self._entry(0, self.disp_v), self._entry(1, self.fb_hist_v), self._entry(2, self.sampler),
            self._entry(3, {"buffer": self.u_fb, "offset": 0, "size": 32})])
        if "p_up" in pipes:
            bind["p_up"] = d.create_bind_group(layout=pipes["p_up"].get_bind_group_layout(0), entries=[
                self._entry(0, {"buffer": self.parts, "offset": 0, "size": PART_MAX * 32}),
                self._entry(2, {"buffer": self.u_part, "offset": 0, "size": 80})])
            bind["p_draw"] = d.create_bind_group(layout=pipes["p_draw"].get_bind_group_layout(0), entries=[
                self._entry(1, {"buffer": self.parts, "offset": 0, "size": PART_MAX * 32}),
                self._entry(2, {"buffer": self.u_part, "offset": 0, "size": 80})])
        src = self.fbo_v
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
            self._entry(0, self.fbo_v), self._entry(1, lv[0]), self._entry(2, lv[1]), self._entry(3, lv[2]),
            self._entry(4, lv[3]), self._entry(5, self.sampler), self._entry(6, {"buffer": self.u_comp, "offset": 0, "size": 480})])
        bind["fxaa"] = d.create_bind_group(layout=pipes["fxaa"].get_bind_group_layout(0), entries=[
            self._entry(0, self.ldr_v), self._entry(1, self.sampler), self._entry(2, {"buffer": self.u_fx, "offset": 0, "size": 96}), self._entry(3, self.ov_tex.create_view())])
        bind["blit"] = d.create_bind_group(layout=pipes["fxaa"].get_bind_group_layout(0), entries=[
            self._entry(0, self.ldr_v), self._entry(1, self.sampler), self._entry(2, {"buffer": self.u_blit, "offset": 0, "size": 96}), self._entry(3, self.ov_tex.create_view())])
        bind["fxaa_b"] = d.create_bind_group(layout=pipes["fxaa"].get_bind_group_layout(0), entries=[
            self._entry(0, self.ldr_b_v), self._entry(1, self.sampler), self._entry(2, {"buffer": self.u_fx, "offset": 0, "size": 96}), self._entry(3, self.ov_tex.create_view())])
        bind["blit_b"] = d.create_bind_group(layout=pipes["fxaa"].get_bind_group_layout(0), entries=[
            self._entry(0, self.ldr_b_v), self._entry(1, self.sampler), self._entry(2, {"buffer": self.u_blit, "offset": 0, "size": 96}), self._entry(3, self.ov_tex.create_view())])
        views = (self.ldr_v, self.ldr_b_v)
        bind["post"] = {}
        for si in range(2):
            for i in range(LY.MAX_FX):
                bind["post"][(si, i)] = d.create_bind_group(layout=pipes["post"].get_bind_group_layout(0), entries=[
                    self._entry(0, views[si]), self._entry(1, self.sampler), self._entry(2, {"buffer": self.u_post[i], "offset": 0, "size": 64}),
                    self._entry(3, lv[1]), self._entry(4, lv[2]), self._entry(5, lv[3])])
        self.bind = bind

    # ---------------------------------------------------------------------- draw
    def _pass(self, enc, view, pipe, group):
        rp = enc.begin_render_pass(color_attachments=[{"view": view, "clear_value": (0, 0, 0, 1),
                                                       "load_op": "clear", "store_op": "store"}])
        rp.set_pipeline(pipe)
        rp.set_bind_group(0, group)
        rp.draw(3)
        rp.end()

    def _read_preview(self, force=False):
        """Read the thumbnails whose copy is two frames old (the GPU is done with them: the read does not wait)."""
        while self._pv_queue and (force or self._pv_count - self._pv_queue[0][0] >= 2):
            _, idx = self._pv_queue.pop(0)
            try:
                b = self.pbufs[idx]
                b.map_sync(wgpu.MapMode.READ)
                self.preview_rgba = bytes(b.read_mapped())
                b.unmap()
                self.preview_n += 1
                self.preview_err = None
            except Exception as e:
                self.preview_rgba = None
                self.preview_err = repr(e)[:90]

    def _draw(self):
        t_in = time.perf_counter()
        prof.mark_start()
        tex = self.context.get_current_texture()
        out_v = tex.create_view()                                          # the window's picture: the last passes write here and the words go over it
        w, h = tex.width, tex.height
        scene_size = self._scene_dims(w, h)
        if (w, h) != self.size or scene_size != self.scene_size or self.bind is None or self._bs != self.bloom_shift:
            if (w, h) != self.size or scene_size != self.scene_size or self._bs != self.bloom_shift:
                self._build_targets(w, h)
            self._build_bind()
        prof.mark("GPU/obter a imagem da janela (aqui o programa espera a placa liberar o quadro)")
        p = self.params
        p["dist"] = self.dist
        d = self.device
        plan = self.stack.update(p, self.dt, self.bloom, w / max(h, 1), (w, h))
        prof.mark("GPU/pilha de efeitos (plano do quadro)")
        if not self.fx_trail:
            plan.fb = None
        if not self.fx_parts:
            plan.part = None
        if plan.fb is not None and plan.fb.get("fbt") == 1:                 # the trail only on the particles: the picture stays sharp, the points draw streaks
            if plan.part is not None:
                plan.part = dict(plan.part, trail=plan.fb["amt"])
            plan.fb = None
        jit = 0
        if self.taa:                                                       # a different sub-pixel offset every frame (Halton 2, 3), 8 bits each
            self._jit_i = (self._jit_i + 1) % 8
            jit = (int(round((halton(self._jit_i + 1, 2)) * 255)) | (int(round(halton(self._jit_i + 1, 3) * 255)) << 8)) << 16
            if jit == 0:
                jit = 1 << 16
        d.queue.write_buffer(self.u_scene, 0, pack_scene(p, *self.scene_size, self.steps, self.bounces,
                                                                     (2 if self.rt else 0) | (4 if self.aa else 0) | (self.style << 8) | (max(0, min(3, int(self.msaa))) << 12) | jit,
                                                                     self.shadow_q | (self.ao_q << 4) | (self.refl_q << 8), p.get("prof", 0)))
        pal = p.get("pal") or ((1.0, 0.3, 0.8), (0.2, 0.8, 1.0))
        pal2 = (pal[0][:3], pal[1][:3] if len(pal) > 1 else pal[0][:3])
        d.queue.write_buffer(self.u_comp, 0, np.concatenate((np.array([self.bloom, self.flash, self.exposure, float(self.bloom_levels), *p.get("bg", (0.0, 0.0, 0.0)), p["fade"] * p["gain"],
                                                      float(self.flash_mode), p["time"], float(self.sharp), float(p.get("duo_contrast", 1.0)),
                                                      *(p.get("duo") or ((0, 0, 0), (1, 1, 1)))[0], 1.0 if self.duo else 0.0, *(p.get("duo") or ((0, 0, 0), (1, 1, 1)))[1], 0.0,
                                                      *self._lights_block(p), float(plan.tone), 0.0, 0.0, 0.0], np.float32), pack_bg(plan, pal2))).astype(np.float32).tobytes())
        prof.mark("GPU/enviar parâmetros (buffers)")
        enc = d.create_command_encoder()
        gen = int(p.get("visual", 0))                                        # NOT p["gen"]: that one is the director's own (the mandala uses it)
        if gen >= 2 and "gen" in self.bind:                                  # a visual other than the Mandala
            d.queue.write_buffer(self.u_gen, 0, pack_gen(p, self.scene_size[0] / max(self.scene_size[1], 1), self.logo_aspect, gen))
            self._pass(enc, self.scene_v, self.pipes["gen"], self.bind["gen"])
        else:
            self._pass(enc, self.scene_v, self.pipes["scene"], self.bind["scene"])
        prof.mark("GPU/passe da cena (raymarching ou gerador)")
        # motion blur by SHUTTER ANGLE, as in cinema: the shutter is open for (angle / 360) of one frame of the reference film rate, so
        # 180 deg at 24 fps = 1/48 s, 360 deg = 1/24 s. The trail is an exponential filter over that exposure time, independent of the
        # real frame rate. A hard cut resets the trail.
        exposure = max(0.0, min(720.0, self.mblur)) / 360.0 / max(self.mblur_fps, 1.0)
        tau = 0.4 * exposure
        k = float(np.exp(-max(self.dt, 1e-3) / tau)) if tau > 1e-4 else 0.0
        if not self.hist_valid or p.get("hardcut"):
            k = 0.0
        d.queue.write_buffer(self.u_acc, 0, np.array([k, 0.0, 0.0, 0.0], np.float32).tobytes())
        cut = bool(p.get("hardcut"))
        if self.taa:
            d.queue.write_buffer(self.u_taa, 0, np.array([0.0 if (not self.taa_valid or cut) else 0.82, 0, 0, 0], np.float32).tobytes())
            self._pass(enc, self.taa_out_v, self.pipes["taa"], self.bind["taa"])
            enc.copy_texture_to_texture({"texture": self.taa_out}, {"texture": self.taa_hist}, (self.scene_size[0], self.scene_size[1], 1))
            self.taa_valid = True
        else:
            self.taa_valid = False
        prof.mark("GPU/suavização temporal (TAA)")
        self._pass(enc, self.disp_v, self.pipes["accum"], self.bind["accum_taa" if self.taa else "accum"])
        enc.copy_texture_to_texture({"texture": self.disp}, {"texture": self.hist}, (self.scene_size[0], self.scene_size[1], 1))
        self.hist_valid = True
        prof.mark("GPU/borrão de movimento (acúmulo)")
        self._particles(enc, p, plan.part)
        prof.mark("GPU/partículas")
        fb = plan.fb
        step = max(0.25, min(4.0, self.dt * 60.0))                          # the per-frame zoom / turn is per 1/60 s, whatever the frame rate
        aspect = self.size[0] / max(self.size[1], 1)
        if fb is not None:
            d.queue.write_buffer(self.u_fb, 0, np.array([0.0 if not self.fb_valid else fb["amt"], 1.0 + fb["zoom"] * 0.0015 * step, fb["rot"] * 0.0012 * step, aspect,
                                                          0.0, 0.0, fb["hue"] * 0.004 * step, fb["blur"]], np.float32).tobytes())
        else:
            d.queue.write_buffer(self.u_fb, 0, np.array([0.0, 1.0, 0.0, aspect, 0.0, 0.0, 0.0, 0.0], np.float32).tobytes())
        self._pass(enc, self.fbo_v, self.pipes["fb"], self.bind["fb"])
        enc.copy_texture_to_texture({"texture": self.fbo}, {"texture": self.fb_hist}, (self.scene_size[0], self.scene_size[1], 1))
        self.fb_valid = fb is not None and fb["amt"] > 0.003
        prof.mark("GPU/rastro (feedback)")
        for L in self.levels[:max(0, min(BLOOM_LEVELS, self.bloom_levels))]:      # unused bloom levels cost nothing
            self._pass(enc, L["dv"], self.pipes["down"], L["g_down"])
            self._pass(enc, L["tv"], self.pipes["blur"], L["g_h"])
            self._pass(enc, L["lvv"], self.pipes["blur"], L["g_v"])
        prof.mark("GPU/brilho (bloom)")
        self._pv_count += 1
        self._read_preview()
        prof.mark("GPU/leitura da prévia (volta da placa)")
        want_pv = self.preview and self._pv_count % max(1, self.preview_every) == 0
        post = plan.post
        fin = tuple(float(x) for x in self.fin)
        fin_on = fin[:11] != (1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0) or self.ov_on
        fb_ = np.array([*fin[:4], *fin[4:8], fin[8], fin[9], fin[10], fin[11], *self._overlay_block(p, w, h)], np.float32).tobytes()
        d.queue.write_buffer(self.u_fx, 16, fb_)
        d.queue.write_buffer(self.u_blit, 16, fb_)
        if self.fxaa or want_pv or post or fin_on:
            self._pass(enc, self.ldr_v, self.pipes["comp"], self.bind["comp"])
            cur = 0                                                   # the picture is in ldr (0) or ldr_b (1): the effect passes hand it to each other
            for i, ps in enumerate(post):
                d.queue.write_buffer(self.u_post[i], 0, np.array([ps["kind"], ps["op"], ps["bm"], ps["amt"], ps["p1"], ps["p2"], ps["p3"], ps["p4"],
                                                                   ps["p5"], ps["p6"], ps["p6"] if ps["kind"] == 3 else 0.0, ps["time"], aspect, self.size[0], self.size[1], 0.0], np.float32).tobytes())
                self._pass(enc, self.ldr_b_v if cur == 0 else self.ldr_v, self.pipes["post"], self.bind["post"][(cur, i)])
                cur ^= 1
            sfx = "_b" if cur else ""
            self._pass(enc, out_v, self.pipes["fxaa"], self.bind[("fxaa" if self.fxaa else "blit") + sfx])
            if want_pv:                                    # a small copy of the finished picture, for the thumbnail
                self._pass(enc, self.ptex_v, self.pipes["fxaa"], self.bind["blit" + sfx])
                pv_idx = self._pv_count % 3
                enc.copy_texture_to_buffer({"texture": self.ptex}, {"buffer": self.pbufs[pv_idx], "bytes_per_row": self.preview_size[0] * 4},
                                           (self.preview_size[0], self.preview_size[1], 1))
        else:
            self._pass(enc, out_v, self.pipes["comp"], self.bind["comp"])
        prof.mark("GPU/composição, efeitos de tela, FXAA e cópia da prévia")
        if self.osd_a > 0.003 and self._osd_pipe is not None and self._osd_bind is not None:
            try:
                self._osd_pass(enc, out_v, w, h)
            except Exception:
                self._osd_pipe = None                                      # the words are a courtesy: they never take the picture down
        prof.mark("GPU/texto na tela (OSD)")
        d.queue.submit([enc.finish()])
        prof.mark("GPU/fechar e enviar os comandos (submit)")
        self._drawn = time.perf_counter() - t_in
        if want_pv:
            self._pv_queue.append((self._pv_count, pv_idx))              # read it later, see _read_preview

    def _particles(self, enc, p, part):
        """The particle field: a compute pass that moves them and an additive instanced draw over the picture (before the feedback, so they leave trails too)."""
        if part is None or part["amt"] < 0.01 or "p_up" not in self.bind:
            return
        n = (0, 16384, 65536, PART_MAX)[max(0, min(3, part["count"]))]
        if n == 0:
            return
        pal = p.get("pal") or ((1.0, 0.3, 0.8), (0.2, 0.8, 1.0))
        c0, c1 = pal[0][:3], (pal[1][:3] if len(pal) > 1 else pal[0][:3])
        aspect = self.size[0] / max(self.size[1], 1)
        if not self.parts_init:
            self.device.queue.write_buffer(self.parts, 0, np.zeros(PART_MAX * 8, np.float32).tobytes())
            self.parts_init = True
        vals = np.array([min(self.dt, 0.05), float(p.get("time", 0.0)), float(p.get("bass", 0.0)), float(p.get("kick", 0.0)),
                         float(p.get("mid", 0.0)), float(p.get("high", 0.0)), float(n), float(part["mode"]),
                         part["size"] / 50.0, aspect, (0.55 if n >= 65536 else 1.0) * part["amt"], float(part.get("trail", 0.0)),
                         c0[0], c0[1], c0[2], 1.0, c1[0], c1[1], c1[2], 1.0], np.float32)
        self.device.queue.write_buffer(self.u_part, 0, vals.tobytes())
        cp = enc.begin_compute_pass()
        cp.set_pipeline(self.pipes["p_up"])
        cp.set_bind_group(0, self.bind["p_up"])
        cp.dispatch_workgroups((n + 255) // 256)
        cp.end()
        rp = enc.begin_render_pass(color_attachments=[{"view": self.disp_v, "load_op": "load", "store_op": "store"}])
        rp.set_pipeline(self.pipes["p_draw"])
        rp.set_bind_group(0, self.bind["p_draw"])
        rp.draw(6, n)
        rp.end()

    def _set_logo_pixels(self, rgba, w, h):
        tex = self.device.create_texture(size=(w, h, 1), format="rgba8unorm", usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST)
        self.device.queue.write_texture({"texture": tex}, rgba, {"bytes_per_row": w * 4, "rows_per_image": h}, (w, h, 1))
        self.logo_tex = tex
        self.logo_aspect = w / max(h, 1)

    def _set_overlay_pixels(self, rgba, w, h):
        tex = self.device.create_texture(size=(w, h, 1), format="rgba8unorm", usage=wgpu.TextureUsage.TEXTURE_BINDING | wgpu.TextureUsage.COPY_DST)
        self.device.queue.write_texture({"texture": tex}, rgba, {"bytes_per_row": w * 4, "rows_per_image": h}, (w, h, 1))
        self.ov_tex = tex
        self.ov_aspect = w / max(h, 1)

    def set_overlay(self, key, rgba, w, h):
        """The picture of the Sobreposição (a text or the logo, see logo.py). Cheap when it is the one already there."""
        if key == self.ov_key:
            return
        self.ov_key = key
        self._set_overlay_pixels(rgba, w, h)
        self.bind = None

    def _overlay_block(self, p, w, h):
        """The 8 floats of the Sobreposição in the last pass: its box in the picture (x, y, width, height, 0..1 from the top left) and its opacity."""
        if not self.ov_on:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        pos, size, op, react = self.ov
        kick, energy = float(p.get("kick", 0.0)), float(p.get("energy", (float(p.get("bass", 0.0)) + float(p.get("mid", 0.0))) * 0.5))
        scale = 1.0 + (0.12 * kick if react == 1 else (0.10 * energy if react == 2 else 0.0))
        bh = max(0.02, min(0.6, size / 100.0)) * scale
        bw = bh * self.ov_aspect * h / max(w, 1)
        if bw > 0.9:
            bh, bw = bh * 0.9 / bw, 0.9
        m = 0.04
        if pos == 1:
            x, y = 0.5 - bw / 2, 0.5 - bh / 2
        elif pos == 2:
            x, y = 0.5 - bw / 2, 1.0 - m - bh
        else:
            x, y = m * h / max(w, 1), 1.0 - m - bh
        alpha = op * ((0.55 + 0.45 * min(1.0, kick)) if react == 1 else ((0.45 + 0.55 * min(1.0, energy)) if react == 2 else 1.0))
        return (x, y, bw, bh, alpha, 0.0, 0.0, 0.0)

    def set_logo(self, key, rgba, w, h):
        """The picture of the Logo / texto visual (see logo.py). Cheap when it is the one already there."""
        if key == self.logo_key:
            return
        self.logo_key = key
        self._set_logo_pixels(rgba, w, h)
        self.bind = None                                                      # the bind groups hold the old texture: they are rebuilt

    def _lights_block(self, p):
        """The 16 floats of the background lights: style / intensity / speed / blank, two colours with bass and kick, then mid, high, beat and aspect."""
        lg = p.get("lights") or (0, 1.0, 1.0)
        pal = p.get("pal") or ((1.0, 0.3, 0.8), (0.2, 0.8, 1.0))
        ca = pal[0][:3]
        cb = pal[1][:3] if len(pal) > 1 else ca
        fixed = {1: ((0.92, 0.92, 0.92), (0.75, 0.82, 1.0)), 2: ((0.92, 0.03, 0.22), (1.0, 0.35, 0.45)), 3: ((0.0, 0.31, 0.93), (0.3, 0.55, 1.0))}.get(int(lg[3]) if len(lg) > 3 else 0)
        if fixed:                                                      # a colour of its own instead of the palette
            ca, cb = fixed
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
        t_fd = time.perf_counter()
        self.canvas.force_draw()
        prof.add("GPU/entregar o quadro (swap e espera pela placa)", max(0.0, time.perf_counter() - t_fd - getattr(self, "_drawn", 0.0)))
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
            if self.monitor_pick > 0 and self.monitor_pick <= len(glfw.get_monitors()):
                best = glfw.get_monitors()[self.monitor_pick - 1]                     # the monitor picked in Ajustes
            for m in ([] if best else glfw.get_monitors()):                       # the monitor the window is on
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

    def monitor_count(self):
        try:
            glfw, _ = self._glfw()
            return len(glfw.get_monitors())
        except Exception:
            return 1

    def move_to_monitor(self, n):
        """Put the picture on monitor n (1..): the window is moved there (a full screen window goes full screen on it). 0 leaves it where it is."""
        if self.headless or n <= 0:
            return
        glfw, win = self._glfw()
        mons = glfw.get_monitors()
        if n > len(mons):
            return
        mon = mons[n - 1]
        mx, my = glfw.get_monitor_pos(mon)
        mode = glfw.get_video_mode(mon)
        if self.fullscreen:
            glfw.set_window_monitor(win, mon, 0, 0, mode.size.width, mode.size.height, mode.refresh_rate)
        else:
            w, h = glfw.get_window_size(win)
            glfw.set_window_pos(win, mx + max(0, (mode.size.width - w) // 2), my + max(0, (mode.size.height - h) // 2))

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
