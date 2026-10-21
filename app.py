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
import look
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


def make_splash():
    """A small window that says the shaders are being prepared. It only appears if that takes more than a moment (after an update the
    graphics driver compiles them again, which can take a while the first time). Returns (tick, close)."""
    state = {"win": None, "t0": time.perf_counter()}

    def tick():
        pygame.event.pump()
        el = time.perf_counter() - state["t0"]
        if state["win"] is None:
            if el < 0.8:
                return
            from pygame._sdl2 import video
            win = video.Window("Audio Organism", (500, 150))
            state["win"] = (win, video.Renderer(win), None, pygame.Surface((500, 150)), pygame.font.SysFont("segoeui", 20, bold=True), pygame.font.SysFont("segoeui", 14))
            state["win"] = state["win"][:2] + (video.Texture(state["win"][1], (500, 150), streaming=True),) + state["win"][3:]
        win, ren, tex, surf, f1, f2 = state["win"]
        surf.fill((10, 9, 22))
        pygame.draw.rect(surf, (52, 48, 96), (0, 0, 500, 150), 2)
        surf.blit(f1.render("Preparando os gráficos" + "." * (1 + int(el * 2) % 3), True, (238, 240, 255)), (24, 22))
        surf.blit(f2.render("Depois de uma atualização isso demora um pouco na primeira vez.", True, (160, 168, 208)), (24, 58))
        surf.blit(f2.render(f"{el:.0f} s", True, (255, 90, 210)), (24, 82))
        bar = int(452 * ((el * 0.08) % 1.0))
        pygame.draw.rect(surf, (46, 44, 84), (24, 112, 452, 8), border_radius=4)
        pygame.draw.rect(surf, (255, 90, 210), (24, 112, max(8, bar), 8), border_radius=4)
        tex.update(surf)
        ren.clear()
        tex.draw()
        ren.present()

    def close():
        if state["win"] is not None:
            try:
                state["win"][0].destroy()
            except Exception:
                pass
            state["win"] = None

    return tick, close


def main():
    if os.environ.get("VIS_HANGLOG"):                      # debugging: dump every thread's stack to a file while the program is busy or stuck
        import faulthandler
        faulthandler.dump_traceback_later(15, repeat=True, file=open(os.path.join(os.environ.get("APPDATA", "."), "AudioOrganism", "hang.log"), "w"))
    test = os.environ.get("VIS_TEST") == "1"
    pygame.init()
    cfg = fresh() if (test and not os.environ.get("VIS_USECFG")) else load_cfg()          # VIS_USECFG=1: test with the saved settings
    forced = parse_backend(cfg)
    if forced:
        os.environ["WGPU_BACKEND_TYPE"] = forced

    from analysis import HOP, Analyzer, Capture, Synth
    from control import ControlWindow
    from neon_director import NeonDirector
    from renderer import Renderer

    splash = make_splash()
    notice = None
    power = "low-power" if cfg.get("gpu", 0) == 1 else "high-performance"
    try:
        rend = Renderer(headless=test, size=(1280, 720), power=power, on_wait=None if test else splash[0])
    except Exception as e:                                  # forced backend not available: fall back to automatic
        if not forced:
            raise
        os.environ.pop("WGPU_BACKEND_TYPE", None)
        notice = f"Backend {forced} indisponível: usando automático"
        rend = Renderer(headless=test, size=(1280, 720), power=power, on_wait=None if test else splash[0])
    splash[1]()
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
    thumbs = None
    if not test:
        from thumbs import Thumbs                         # the live thumbnails of the scene gallery (their own small renderer, in a thread)
        thumbs = Thumbs(power)
        ctl.thumbs = thumbs
    rend.place_window(30, 40)
    ndir = NeonDirector()

    # ---------------------------------------------------------------- state
    fps, last, clock_t = 60.0, time.perf_counter(), 0.0
    last_dev_check = 0.0
    last_motion, last_click = 0.0, -1.0
    cursor_hidden = False
    frame = 0
    shots = {int(t * 60): n for t, n in ((4, "calm"), (10, "groove"), (15.5, "build"), (16.8, "peak"), (17.3, "drop"), (24, "high"))}
    pv_n = 0                                                    # thumbnails already handed to the control window
    sil_t = 0.0                                                 # seconds of deep silence in a row
    dyn, dyn_t = 1.0, 0.0                                       # dynamic resolution: scale factor and last adjustment time
    bench = None
    upd = Updater()
    upd_seen = ""
    if cfg["auto_update"] and REPO and not test:
        upd.start_check()
    menu.info = f"versão {VERSION}"

    auto = autotest_load()                                         # VIS_AUTOTEST=<script.json>: a self-driving test of the real program (see autotest_step)
    running = True
    while running:
        if auto is not None and autotest_step(auto, ctl, menu):
            running = False
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
                    new = 0 if ndir.cur.get("strobe", cfg["strobe"]) else 2          # the key acts on the scene that is on screen
                    ndir.cur["strobe"] = new
                    if ndir.cur is menu.cfg["scenes"][menu.cfg["scene_edit"]]:
                        cfg["strobe"] = new
                    menu.touch()
                    menu.say("Flashes: " + ("completo" if new else "desligado"))
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
        rend.steps, rend.bounces = max(24, int(cfg["steps"] * (0.55 + 0.45 * dyn))), 1          # dynamic quality: fewer ray steps too when the FPS is short
        rend.shadow_q, rend.ao_q, rend.refl_q = 1, 1, 1                      # (only used by the ray-traced lighting, which is off for now)
        am = cfg["aa_mode"]                                                       # 0 off, 1 edges, 2 FXAA, 3..5 MSAA 2x / 4x / 8x
        rend.aa, rend.fxaa, rend.msaa = (am == 1), (am == 2), {3: 1, 4: 2, 5: 3}.get(am, 0)
        rend.bloom_levels, rend.rt = cfg["bloomq"], False                  # ray tracing is switched off for now
        rend.sharp = (0.0, 0.35, 0.7, 1.2)[cfg["sharp"]]
        rend.bloom_shift = 1 + cfg["bloomres"]
        rend.dist = (5.0, 9.0, 14.0)[cfg["dist"]]
        dyn_floor = max(0.1, min(1.0, cfg["dynmin"] / max(cfg["res"], 1)))
        ctl.interval = 0.0                                                    # the panel is redrawn with every output frame
        ctl.view = cfg["panel_view"]
        rend.mblur, rend.mblur_fps, rend.dt = cfg["mblur"], cfg["mblur_fps"], dt
        if cfg["dynres"] and not test and bench is None:
            if clock_t - dyn_t > 0.6:                           # trade resolution for FPS: down fast, up slowly
                dyn_t = clock_t
                target = cfg["fps_out"]
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
                tgt, cur = cfg["fps_out"], int(cfg["preset"])
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
        live = ndir.cur                                                      # the scene on screen decides how it answers the music
        l_strobe, l_react = int(live.get("strobe", cfg["strobe"])), live.get("react", cfg["react"])
        strobe_on = (0.0, 0.45, 1.0)[max(0, min(2, l_strobe))]
        an.max_sub = 1 if l_strobe < 2 else 8
        an.bursts_enabled = bool(live.get("bursts", cfg["bursts"])) and l_strobe == 2
        rk = l_react / 100.0
        if thumbs is not None:
            thumbs.feed(an, cfg, rk)
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
        look.apply(rend, params, ndir.cur, cfg["detail"])                  # shader kind, room colour, the black scene
        params.update(bass=an.bass * rk, mid=an.mid * rk, high=an.high * rk, kick=an.kick * rk, snare=an.snare, hat=an.hat,
                      beat=(an.beat_n + an.phase) if an.bpm > 0 else clock_t * 2.0)
        if not params.get("blank"):
            rend.bloom = live.get("bloom", cfg["bloom"]) / 100.0
            rend.flash = min(1.0, max(max(an.strobe, an.burst_pulse) * strobe_on, an.flash * strobe_on, an.drop_flash * 1.1))
        sil_t = sil_t + dt if an.silence > 0.95 else 0.0
        idle = sil_t > 3.0 and not test                                                  # a long silence: the picture is dark and still, draw it rarely
        skip = ((cfg["rrate"] > 0 and frame % (cfg["rrate"] + 1) != 0) or (idle and frame % 6 != 0)) and not test    # render rate: 1 frame out of 2 or 3
        rend.preview = (not test) and menu.reserved > 0
        frame_img = None if skip else rend.render(params)
        if rend.preview and rend.preview_rgba is not None and rend.preview_n != pv_n:
            pv_n = rend.preview_n
            ctl.set_preview(rend.preview_rgba, rend.preview_size, rend.fmt)

        # ------------------------------------------------ control window + save
        ok, msg = rend.shader_status()
        status = dict(gpu=rend.gpu_name, backend=rend.backend, shader_ok=ok, shader_msg=msg, reloads=rend.lib.reloads)
        status["preview"] = dict(on=rend.preview, n=rend.preview_n, got=rend.preview_rgba is not None, err=rend.preview_err, reserved=menu.reserved,
                                 thumbs=(None if thumbs is None else (thumbs.ready, thumbs.error, len(thumbs.frames))))
        lat = (cap.frames / rate * 1000.0 if cap else 10.0) + HOP / rate * 1500.0 + dt * 1000.0
        if not test:
            status["genre"] = ndir.genre
            try:
                from menu import CAM_OPTS, MV_OPTS, CAM_AUTO, MV_AUTO
                cam_names = {1: "Cinema", 2: "Clipe", 3: "Hipnótico"}
                mv_names = {"calm": "Calmo", "groove": "Hipnótico", "high": "Nervoso", "build": "Pela música"}
                cam = (cam_names.get(ndir.cam_auto, "?") + " (auto)") if cfg["camera"] == CAM_AUTO else dict((v, n) for n, v in CAM_OPTS).get(cfg["camera"], "Manual")
                mov = (mv_names.get(ndir.mv_auto, "?") + " (auto)") if cfg["movement"] == MV_AUTO else dict((v, n) for n, v in MV_OPTS).get(cfg["movement"], "Manual")
                sty = params.get("shader_name", "3D")
                why, t_ch = ndir.last_change
                status["image"] = dict(scene=ndir.scene_name(ndir.scene), scene_i=ndir.scene, pending_scene=params.get("pending_scene", -1), scene_when=params.get("scene_when", 2), style=sty, camera=cam, movement=mov, why=why or None, since=max(0.0, ndir.age - t_ch))
            except Exception:
                pass
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
            print(f"[dbg] preview={status.get('preview')}", flush=True)
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
        pace = cfg["fps_out"]                                                                  # the output FPS: the picture is never drawn faster than this
        if not test and not rend.vsync and pace > 0:
            target = 1.0 / pace
            while time.perf_counter() - t_start < target:
                time.sleep(0.0005)

    if test:
        print("diretor:", " | ".join(ndir.log), flush=True)
    if menu.dirty and not test:
        save_cfg(cfg)
    if thumbs is not None:
        thumbs.stop()
    ctl.destroy()
    rend.close()
    if cap:
        cap.close()
    pygame.quit()


def autotest_load():
    """A test hook: VIS_AUTOTEST names a JSON list of steps {"wait": s, "do": "click"|"key"|"shot"|"quit", ...} that the running program performs on its own
    control window (events go straight to the window code, the real mouse and screen are never touched; "shot" saves the panel as a PNG)."""
    path = os.environ.get("VIS_AUTOTEST")
    if not path:
        return None
    import json
    with open(path, encoding="utf-8") as f:
        return dict(steps=json.load(f), i=0, t=time.perf_counter())


def autotest_step(auto, ctl, menu):
    """Run the next step when its wait is over. Returns True when the program should quit."""
    import types
    if auto["i"] >= len(auto["steps"]):
        return True
    st = auto["steps"][auto["i"]]
    if time.perf_counter() - auto["t"] < float(st.get("wait", 0.5)):
        return False
    auto["i"] += 1
    auto["t"] = time.perf_counter()
    do = st.get("do")
    if do == "click":
        pos = (int(st["x"]), int(st["y"]))
        for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))),
                           (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
            ctl.handle(types.SimpleNamespace(type=typ, pos=pos, **extra))
    elif do == "back":
        ctl.handle(types.SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, pos=(100, 300), button=6, buttons=(0, 0, 0)))
    elif do == "key":
        k = getattr(pygame, "K_" + st["k"])
        ctl.handle(types.SimpleNamespace(type=pygame.KEYDOWN, key=k, mod=0, unicode=""))
    elif do == "tab":
        menu.press("tab%d" % int(st["n"]))
    elif do == "shot":
        ctl.force = True
        ctl.update(time.perf_counter(), None, 0, 0, False, None, force=True) if False else None
        pygame.image.save(ctl.surf, st["f"])
    elif do == "dump":
        print("[autotest]", dict(view=menu.scene_view, tab=menu.tab, scenes=len(menu.cfg["scenes"]), card_menu=ctl.card_menu, effect=menu.cfg["effect"],
                                 hits=[(str(r), k, a) for r, k, a in ctl.gal_hits if k in ("mi", "menu")][:6]), flush=True)
    elif do == "quit":
        return True
    return False


def _single_instance():
    """Only one copy at a time: a second double-click brings the open one to the front (a second heavy copy on the same GPU makes both
    crawl, which looks like "it does not open"). Returns False when this process should quit."""
    if os.name != "nt" or os.environ.get("VIS_TEST") == "1" or "--multi" in sys.argv:
        return True
    import ctypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.CreateMutexW(None, False, "Local\\AudioOrganismSingleInstance")
    if k32.GetLastError() != 183:                                    # ERROR_ALREADY_EXISTS
        return True
    hwnd = u32.FindWindowW(None, "Audio Organism - Controles")
    if hwnd:
        u32.ShowWindow(hwnd, 9)                                      # SW_RESTORE
        u32.SetForegroundWindow(hwnd)
    else:
        u32.MessageBoxW(0, "O Audio Organism já está aberto (ou ainda abrindo).\nSe nada aparece, feche MusicVisualizer.exe no Gerenciador de Tarefas e abra de novo.",
                        "Audio Organism", 0x40)
    return False


def _log_crash(text):
    try:
        folder = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AudioOrganism")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "erro.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  versão " + VERSION + "\n" + text + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    if _single_instance():
        try:
            main()
        except SystemExit:
            raise
        except BaseException:
            import traceback
            tb = traceback.format_exc()
            _log_crash(tb)                                           # the exe has no console: without this a crash is silent
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, "O Audio Organism fechou por um erro.\nO detalhe foi salvo em:\n%APPDATA%\\AudioOrganism\\erro.log\n\n" + tb.strip().splitlines()[-1][:200],
                                                 "Audio Organism", 0x10)
            except Exception:
                pass
            raise
