"""Audio Organism - wgpu edition.

Music-reactive 3D neon, ray-marched on the GPU through wgpu (Vulkan or Direct3D 12). A procedural director
picks and modulates the scene from the music's build-up. Shaders in ./shaders hot-reload while it runs.

Two windows: the display window shows only the effect; the control window has the live music monitor and
the settings. Display window keys: F / double click fullscreen, Esc leave fullscreen, D test drop, V vsync, S strobe.

  python app.py                    normal start
  python app.py --backend d3d12    force Direct3D 12 (or: vulkan)
"""
import os
import sys
import time

import pygame

from menu import Menu, fresh, load_cfg, save_cfg, PRESETS
from updater import Updater, can_self_update, apply as apply_update
from version import REPO, VERSION

PRESETS_N = [p[0] for p in PRESETS]

BACKENDS = {1: "Vulkan", 2: "D3D12"}


def parse_backend(cfg):
    arg = None
    if "--backend" in sys.argv:
        i = sys.argv.index("--backend")
        arg = sys.argv[i + 1].lower() if i + 1 < len(sys.argv) else None
    if arg in ("vulkan", "d3d12"):
        return {"vulkan": "Vulkan", "d3d12": "D3D12"}[arg]
    return BACKENDS.get(cfg.get("backend", 0))


def main():
    test = os.environ.get("VIS_TEST") == "1"
    pygame.init()
    cfg = fresh() if test else load_cfg()
    forced = parse_backend(cfg)
    if forced:
        os.environ["WGPU_BACKEND_TYPE"] = forced

    from analysis import HOP, Analyzer, Capture, Synth
    from control import ControlWindow
    from neon_director import NeonDirector
    from renderer import Renderer

    notice = None
    power = "low-power" if cfg.get("gpu", 0) == 1 else "high-performance"
    try:
        rend = Renderer(headless=test, size=(1280, 720), power=power)
    except Exception as e:                                  # forced backend not available: fall back to automatic
        if not forced:
            raise
        os.environ.pop("WGPU_BACKEND_TYPE", None)
        notice = f"Backend {forced} indisponível: usando automático"
        rend = Renderer(headless=test, size=(1280, 720), power=power)
    print(f"GPU: {rend.gpu_name} | backend: {rend.backend}", flush=True)

    # ---------------------------------------------------------------- audio
    cap, syn, rate = None, None, 48000
    if test:
        syn = Synth(rate)
    else:
        try:
            cap = Capture()
            rate = cap.rate
        except Exception as e:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Nao foi possivel capturar o audio do sistema:\n{e}", "Audio Organism", 0x10)
            sys.exit(1)
    an = Analyzer(rate)

    menu = Menu(cfg)
    if notice:
        menu.say(notice)
    dw, dh = pygame.display.get_desktop_sizes()[0]
    ctl = ControlWindow(menu, pos=(max(40, min(dw - 1000, 1330)), 40), headless=test)
    rend.place_window(30, 40)
    ndir = NeonDirector()

    # ---------------------------------------------------------------- state
    fps, last, clock_t = 60.0, time.perf_counter(), 0.0
    last_dev_check = 0.0
    last_motion, last_click = 0.0, -1.0
    cursor_hidden = False
    frame = 0
    shots = {int(t * 60): n for t, n in ((4, "calm"), (10, "groove"), (15.5, "build"), (16.8, "peak"), (17.3, "drop"), (24, "high"))}
    dyn, dyn_t = 1.0, 0.0                                       # dynamic resolution: scale factor and last adjustment time
    bench = None
    upd = Updater()
    upd_seen = ""
    if cfg["auto_update"] and REPO and not test:
        upd.start_check()
    menu.info = f"versão {VERSION}"

    running = True
    while running:
        t_start = time.perf_counter()
        dt = 1 / 60 if test else min(max(t_start - last, 0.0005), 0.05)
        last = t_start
        clock_t += dt
        fps += (1.0 / max(dt, 1e-4) - fps) * 0.05
        manual_drop = False

        # ------------------------------------------------------------ events
        for e in pygame.event.get():
            ew = getattr(e, "window", None)
            wid = ew.id if ew is not None else None
            if os.environ.get("VIS_DEBUG") and e.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN, pygame.WINDOWFOCUSGAINED):
                print(f"[dbg] pygame event {pygame.event.event_name(e.type)} window={wid} ctl={getattr(ctl, 'id', None)}", flush=True)
            if e.type == pygame.QUIT or e.type == pygame.WINDOWCLOSE:
                running = False
            elif not test and wid == getattr(ctl, "id", None):
                act = ctl.handle(e)
                if act == "quit":
                    running = False
                elif act == "update_check":
                    if not REPO:
                        menu.say("Atualização ainda não configurada (repositório do GitHub)")
                    elif upd.start_check():
                        menu.say("Procurando atualização...")
                elif act == "update_apply":
                    if upd.state == "available":
                        if not can_self_update():
                            menu.say("A atualização automática só funciona no .exe. Use: git pull")
                        else:
                            upd.start_download()
                            menu.say("Baixando a atualização...")
                elif act == "bench" and bench is None:
                    if cfg["vsync"]:
                        menu.say("Desligue o VSync para medir o desempenho")
                    else:
                        bench = dict(t0=clock_t, dts=[])                       # measure 10 s with the current settings, dynamic resolution off
                        menu.say("Medindo o desempenho por 10 s...")
        for ev in rend.poll_events():
            t = ev.get("event_type")
            if t in ("pointer_move", "pointer_down"):
                last_motion = clock_t
            if t == "double_click":
                menu.set_value("fullscreen", not cfg["fullscreen"])
            elif t == "key_down":
                k = str(ev.get("key", ""))
                if k == "Escape":
                    if cfg["fullscreen"]:
                        menu.set_value("fullscreen", False)
                elif k.lower() == "f":
                    menu.set_value("fullscreen", not cfg["fullscreen"])
                elif k.lower() == "v":
                    menu.set_value("vsync", not cfg["vsync"])
                elif k.lower() == "s":
                    menu.set_value("strobe", 0 if cfg["strobe"] else 2)
                elif k.lower() == "d":
                    manual_drop = True
        if rend.closed():
            running = False

        # ------------------------------------------------------- apply settings
        if cfg["vsync"] != rend.vsync:
            if not rend.set_vsync(cfg["vsync"]):
                cfg["vsync"] = rend.vsync
                menu.say("VSync indisponível neste backend")
        if cfg["fullscreen"] != rend.fullscreen:
            rend.set_fullscreen(cfg["fullscreen"])
        # graphics options (aba Gráficos)
        rend.steps, rend.bounces = max(24, int(cfg["steps"] * (0.55 + 0.45 * dyn))), 0          # dynamic quality: fewer ray steps too when the FPS is short
        rend.shadow_q, rend.ao_q, rend.refl_q = cfg["shadows"], cfg["ao"], cfg["reflect"]
        am = cfg["aa_mode"]                                                       # 0 off, 1 edges, 2 FXAA, 3..5 MSAA 2x / 4x / 8x
        rend.aa, rend.fxaa, rend.msaa = (am == 1), (am == 2), {3: 1, 4: 2, 5: 3}.get(am, 0)
        rend.bloom_levels, rend.rt = cfg["bloomq"], bool(cfg["rt"])
        rend.sharp = (0.0, 0.35, 0.7, 1.2)[cfg["sharp"]]
        rend.bloom_shift = 1 + cfg["bloomres"]
        rend.dist = (5.0, 9.0, 14.0)[cfg["dist"]]
        dyn_floor = max(0.1, min(1.0, cfg["dynmin"] / max(cfg["res"], 1)))
        ctl.interval = 1.0 / max(5, cfg["panel_hz"])
        rend.mblur, rend.mblur_fps, rend.dt = cfg["mblur"], cfg["mblur_fps"], dt
        if cfg["dynres"] and not test and bench is None:
            if clock_t - dyn_t > 0.6:                           # trade resolution for FPS: down fast, up slowly
                dyn_t = clock_t
                target = cfg["fps_target"]
                if fps < target * 0.93:
                    dyn = max(dyn_floor, dyn - 0.07)
                elif fps > target * 1.20 and dyn < 1.0:
                    dyn = min(1.0, dyn + 0.03)
        else:
            dyn = 1.0
        if bench is not None:
            bench["dts"].append(dt)
            if clock_t - bench["t0"] >= 10.0:
                dts = sorted(bench["dts"][5:])                                         # skip the first frames (warm-up)
                avg = len(dts) / max(sum(dts), 1e-6)
                p1 = 1.0 / max(dts[max(0, int(len(dts) * 0.99) - 1)], 1e-6)            # the slowest 1% of frames
                tgt, cur = cfg["fps_target"], int(cfg["preset"])
                if cur >= len(PRESETS_N):                                              # custom settings: compare with the middle preset
                    cur = 1
                if avg >= 1.8 * tgt and p1 >= 1.2 * tgt:
                    new = min(len(PRESETS_N) - 1, cur + 1)
                elif avg < 0.6 * tgt:
                    new = max(0, cur - 2)
                elif avg < 0.95 * tgt or p1 < 0.7 * tgt:
                    new = max(0, cur - 1)
                else:
                    new = cur
                msg = f"Média {avg:.0f} fps, 1% pior {p1:.0f}  ·  "
                if new != int(cfg["preset"]):
                    menu.set_value("preset", new, announce=False)
                    msg += f"aplicado: {PRESETS_N[new]}"
                else:
                    msg += "as configurações atuais estão boas"
                menu.say(msg)
                bench = None
        rend.res = max(25, cfg["res"] * dyn)
        strobe_on = (0.0, 0.45, 1.0)[cfg["strobe"]]
        an.max_sub = 1 if cfg["strobe"] < 2 else 8
        an.bursts_enabled = bool(cfg["bursts"]) and cfg["strobe"] == 2
        rk = cfg["react"] / 100.0
        want_hide = rend.fullscreen and clock_t - last_motion > 2.0
        if want_hide != cursor_hidden:
            cursor_hidden = want_hide
            rend.hide_cursor(want_hide)

        # update status -> menu (version text, button label, short messages on changes)
        key = f"{upd.state}:{int(upd.progress * 10)}"
        if key != upd_seen:
            upd_seen = key
            if upd.state == "available":
                menu.upd_label = f"Atualizar para {upd.info['version']}"
                menu.info = f"versão {VERSION}  ·  nova: {upd.info['version']}"
                if key.endswith(":0"):
                    menu.say(f"Nova versão {upd.info['version']} disponível (aba Ajustes)")
            elif upd.state == "uptodate":
                menu.upd_label = ""
                menu.info = f"versão {VERSION}  ·  atualizado"
                menu.say("Você está na versão mais recente")
            elif upd.state == "downloading":
                menu.upd_label = ""
                menu.info = f"baixando {upd.progress * 100:.0f}%"
            elif upd.state == "error":
                menu.info = f"versão {VERSION}  ·  {upd.error}"
                menu.say(upd.error)
                upd.state = "idle"
            menu.need = True
        if upd.state == "ready" and upd.path:
            menu.say("Atualização baixada: reiniciando...")
            apply_update(upd.path)
            running = False
            upd.state = "idle"

        # hot reload of shaders
        for name in rend.poll_shaders():
            menu.say(f"Shader recarregado: {name}")

        # ------------------------------------------------------------ audio
        if test:
            an.feed(syn.chunk(int(rate * dt)))
        else:
            an.pump(cap, time.perf_counter())
            if clock_t - last_dev_check > 2.0:
                last_dev_check = clock_t
                if cap.default_changed():
                    try:
                        cap.reopen()
                        if cap.rate != an.rate:
                            an = Analyzer(cap.rate)
                    except Exception:
                        pass
        an.update(dt)
        if manual_drop:
            an.drop = an.drop_b = an.drop_event = 1.0
            an.drop_flash = 1.0
        if ndir.log and menu.dirty is False and False:
            pass

        # --------------------------------------------------- procedural scene
        params = ndir.update(dt, an, cfg)
        # image style: the user's choice, or the style that suits the current scene (3D, 2D or holograma; painted by the Facetas engine)
        eff = (params.get("style_auto", 1) if cfg["auto_style"] else params.get("style_default", 1)) if cfg["style"] == 8 else (cfg["style"] or params.get("style_default", 1))
        rend.style = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}.get(eff, 0)
        rend.duo = (eff == 7)
        if eff in (2, 5):                                 # neon and chrome only read on a dark room: the background stays black
            params["bg"] = (0.0, 0.0, 0.0)
        if eff == 4:                                      # raio X: a deep blue-black room
            params["bg"] = (0.0, 0.01, 0.025)
        if eff == 6:                                      # aquarela: the background is paper
            params["bg"] = (0.97, 0.95, 0.91)
        params["complexity"] = min(params["complexity"], max(0.30, cfg["detail"] / 100.0))     # panel density cap
        params.update(bass=an.bass * rk, mid=an.mid * rk, high=an.high * rk, kick=an.kick * rk, snare=an.snare, hat=an.hat)
        rend.bloom = cfg["bloom"] / 100.0
        rend.flash = min(1.0, max(max(an.strobe, an.burst_pulse) * strobe_on, an.flash * strobe_on, an.drop_flash * 1.1))
        skip = cfg["rrate"] > 0 and not test and frame % (cfg["rrate"] + 1) != 0       # render rate: draw 1 frame out of 2 or 3
        frame_img = None if skip else rend.render(params)

        # ------------------------------------------------ control window + save
        ok, msg = rend.shader_status()
        status = dict(gpu=rend.gpu_name, backend=rend.backend, shader_ok=ok, shader_msg=msg, reloads=rend.lib.reloads)
        lat = (cap.frames / rate * 1000.0 if cap else 10.0) + HOP / rate * 1500.0 + dt * 1000.0
        if not test:
            status["look"] = ndir.look_name() + (f"  ·  gênero: {ndir.genre}" if ndir.genre != "?" else "")
            ctl.update(time.perf_counter(), an, fps, lat, rend.vsync, status)
            if menu.dirty and time.perf_counter() - menu.dirty_t > 1.0:
                save_cfg(cfg)
                menu.dirty = False

        frame += 1
        if not test and frame % 20 == 0:                    # resolution and FPS in the window title, so the picture stays clean
            sw, sh = rend.scene_size
            rend.set_title(f"Audio Organism  ·  {sw}×{sh}  ·  {fps:.0f} fps")
            menu.set_live(f"{fps:.0f} FPS  ·  render {sw}×{sh}" + (f"  ·  {dyn * 100:.0f}% dinâmico" if cfg["dynres"] and dyn < 0.999 else "") + (f"  ·  1 a cada {cfg['rrate'] + 1} quadros" if cfg["rrate"] else ""))
        if os.environ.get("VIS_DEBUG") and frame % 120 == 0:
            print(f"[dbg] backend={rend.backend} vsync={rend.vsync} fs={rend.fullscreen} fps={fps:.0f} res={rend.res} steps={rend.steps} bounces={rend.bounces}", flush=True)
        if test and frame in shots:
            nm = shots[frame]
            ctl.update(clock_t, an, fps, lat, rend.vsync, status, force=True)
            pygame.image.save(ctl.surf, f"shot_ctl_{nm}.png")
            import numpy as np
            arr = np.ascontiguousarray(frame_img[:, :, :3])
            pygame.image.save(pygame.image.frombuffer(arr.tobytes(), (arr.shape[1], arr.shape[0]), "RGB"), f"shot_{nm}.png")
            print(f"t={frame / 60:5.1f}s state={an.state:10s} bpm={an.bpm:5.1f} E={an.energy:.2f} look={ndir.log[-1] if ndir.log else '-'}", flush=True)
        if test and frame >= 25 * 60:
            break

        # fps cap (only when not synced to the monitor)
        pace = cfg["fps_cap"] if cfg["fps_cap"] > 0 else (cfg["fps_target"] if cfg["rrate"] > 0 else 0)      # skipped frames need a pace of their own
        if not test and not rend.vsync and pace > 0:
            target = 1.0 / pace
            while time.perf_counter() - t_start < target:
                time.sleep(0.0005)

    if test:
        print("diretor:", " | ".join(ndir.log), flush=True)
    if menu.dirty and not test:
        save_cfg(cfg)
    ctl.destroy()
    rend.close()
    if cap:
        cap.close()
    pygame.quit()


if __name__ == "__main__":
    main()
