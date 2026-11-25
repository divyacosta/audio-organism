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
import prof

import pygame

from menu import Menu, fresh, load_cfg, save_cfg, PRESETS
import look
import scenes as SC
import widgets
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
            state["win"] = (win, video.Renderer(win), None, pygame.Surface((500, 150)), widgets.font("head", True), widgets.font("label"))
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
    from osd import Osd, HINT
    from neon_director import NeonDirector
    from demo import Silence
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
    rend.preview_size = (512, 288)                          # the picture of the Palco is big: rows of 2048 bytes (a multiple of 256, as the GPU wants)
    print(f"GPU: {rend.gpu_name} | backend: {rend.backend}", flush=True)

    # ---------------------------------------------------------------- audio
    cap, syn, rate, audio_err = None, None, 48000, None
    if test:
        syn = Synth(rate)
    elif os.environ.get("VIS_SYNTH"):                                            # VIS_SYNTH=1: the test music instead of the capture (the performance report: the same load every time)
        syn = Synth(rate)
    elif os.environ.get("VIS_SILENT"):                                          # VIS_SILENT=1: the audio input is replaced by silence (tests and pictures of the first screen)
        syn = Silence()
    else:
        try:
            cap = Capture(cfg.get("abuf", 1024), cfg.get("adev", ""))
            rate = cap.rate
        except Exception as e:                                                  # no modal box: the program opens with the test signal and says so
            syn, audio_err = Synth(rate), f"Sem captura de áudio ({str(e)[:50]}): usando sinal de teste"
    an = Analyzer(rate)

    menu = Menu(cfg)
    recorder = None
    import agenda as _agenda
    agenda_tk = _agenda.Ticker()
    import foreground as _fg
    fg_watch, fg_next = _fg.Watch(), 0.0                                      # Regras por programa: the program in front, asked twice a second
    if os.environ.get("VIS_REPORT"):                                          # the performance report (report.py): Ultra, VSync and dynamic resolution off, then measure and quit
        import report
        import settings as _settings
        _settings.PATH = os.path.join(os.path.dirname(os.environ["VIS_REPORT"]), "settings.json")      # whatever the run saves goes next to the report, never over the person's settings
        recorder = report.Recorder(os.environ["VIS_REPORT"], profile=bool(os.environ.get("VIS_REPORT_PROF")))
        prof.ON = True
        pick = int(os.environ.get("VIS_REPORT_PRESET", len(PRESETS_N) - 1))              # 0 Baixo, 1 Médio, 2 Alto, 3 Ultra (the report's default)
        cfg["preset"], cfg["vsync"], cfg["dynres"] = pick, False, False
        if os.environ.get("VIS_REPORT_FPS"):                                   # the FPS cap of the run (to see what the picture does with no cap in the way)
            cfg["fps_out"] = int(os.environ["VIS_REPORT_FPS"])
        menu.set_value("preset", pick, announce=False)
    if cap is not None:                                                       # the pickers of Ajustes list what the system has
        menu.audio_devices = cap.devices()
        menu.monitors = rend.monitor_count()
        menu.rebuild_scenes()
    if notice:
        menu.say(notice)
    if audio_err:
        menu.problem("audio", audio_err)
    dw, dh = pygame.display.get_desktop_sizes()[0]
    cw0, _ = ControlWindow.default_size(dw, dh)
    ctl = ControlWindow(menu, pos=(max(20, min(dw - cw0 - 20, 1330)), 30), headless=test)
    thumbs = None
    if not test:
        from thumbs import Thumbs                         # the live thumbnails of the scene gallery (their own small renderer, in a thread)
        thumbs = Thumbs(power)
        ctl.thumbs = thumbs
    rend.place_window(30, 40)
    ndir = NeonDirector()
    osd, fs_prev = Osd(), False                       # the words on the picture window in full screen (osd.py)

    # ---------------------------------------------------------------- state
    fps, last, clock_t = 60.0, time.perf_counter(), 0.0
    last_dev_check = 0.0
    last_motion, last_click = 0.0, -1.0
    cursor_hidden = False
    frame = 0
    shots = {int(t * 60): n for t, n in ((4, "calm"), (10, "groove"), (15.5, "build"), (16.8, "peak"), (17.3, "drop"), (24, "high"))}
    pv_n = 0                                                    # thumbnails already handed to the control window
    dyn, dyn_t = 1.0, 0.0                                       # dynamic resolution: scale factor and last adjustment time
    bench = None
    upd = Updater()
    upd_seen = ""
    if cfg["auto_update"] and REPO and not test:
        upd.start_check()
    menu.info = f"versão {VERSION}"

    auto = None
    if os.environ.get("VIS_AUTOTEST"):                              # VIS_AUTOTEST=<script.json>: a self-driving test of the real program (see autotest.py)
        from autotest import autotest_load, autotest_step
        auto = autotest_load()
        auto["rend"], auto["ndir"] = rend, ndir
    running = True
    import remote as remote_mod
    remote = remote_mod.Remote()
    import stream as stream_mod
    phone = stream_mod.Stream()                                # "Ver no celular": the picture and a few buttons in a phone's browser
    tm = {}                                                   # smoothed milliseconds of each stage of a frame (shown in the Status)

    def lap(k, t0):
        tm[k] = tm.get(k, 0.0) * 0.92 + (time.perf_counter() - t0) * 1000.0 * 0.08

    while running:
        if auto is not None:
            auto["an"] = an
        if auto is not None and autotest_step(auto, ctl, menu):
            running = False
        t_start = time.perf_counter()
        dt = 1 / 60 if test else min(max(t_start - last, 0.0005), 0.05)
        last = t_start
        clock_t += dt
        fps += (1.0 / max(dt, 1e-4) - fps) * 0.05
        manual_drop = False
        prof.mark_start()

        # ------------------------------------------------------------ events
        for e in pygame.event.get():
            ew = getattr(e, "window", None)
            wid = ew.id if ew is not None else None
            if os.environ.get("VIS_DEBUG") and e.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN, pygame.WINDOWFOCUSGAINED):
                print(f"[dbg] pygame event {pygame.event.event_name(e.type)} window={wid} ctl={getattr(ctl, 'id', None)}", flush=True)
            if auto is not None and e.type in (pygame.KEYDOWN, pygame.KEYUP, pygame.TEXTINPUT, pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL):
                continue                                                       # a self-driving test (VIS_AUTOTEST) takes no real keys or clicks: its own go straight to the window code, so a person at the machine cannot change the run
            if e.type == pygame.QUIT or e.type == pygame.WINDOWCLOSE:
                running = False
            elif not test and wid == getattr(ctl, "id", None):
                act = ctl.handle(e)
                if isinstance(act, str) and act.startswith("key:"):                    # a shortcut button of the Ao vivo tab: the same as pressing the key on the picture
                    rend.events.append({"event_type": "key_down", "key": act[4:]})
                elif act == "quit":
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
                    stage_mode(False)
                elif k.lower() == "p":                                                 # stage mode: full screen and the control window out of the way
                    on = not stage[0]
                    stage_mode(on)
                    menu.set_value("fullscreen", on)
                elif k.lower() == "f":
                    menu.set_value("fullscreen", not cfg["fullscreen"])
                elif k.lower() == "v":
                    menu.set_value("vsync", not cfg["vsync"])
                elif k.lower() == "s":
                    new = 0 if ndir.cur.get("strobe", cfg["strobe"]) else 2          # the key acts on the scene that is on screen
                    ndir.base["strobe"] = new
                    if ndir.base is menu.cfg["scenes"][menu.cfg["scene_edit"]]:
                        cfg["strobe"] = new
                    menu.touch()
                    menu.say("Flashes: " + ("completo" if new else "desligado"))
                elif k.lower() == "d":
                    manual_drop = True
                elif len(k) == 1 and menu.shortcut(k, ndir.scene, osd=not ev.get("remote")):    # 1..9 play a scene, A turns the automatic change on or off
                    pass
        if rend.closed():
            running = False

        # ------------------------------------------------------- apply settings
        if cfg["vsync"] != rend.vsync:
            if not rend.set_vsync(cfg["vsync"]):
                cfg["vsync"] = rend.vsync
                menu.say("VSync indisponível neste backend")
        if cfg.get("monitor", 0) != rend.monitor_pick:                   # the monitor of the picture was changed in Ajustes
            rend.monitor_pick = cfg.get("monitor", 0)
            rend.move_to_monitor(rend.monitor_pick)
        if cfg["fullscreen"] != rend.fullscreen:
            rend.set_fullscreen(cfg["fullscreen"])
        # the words on the picture (full screen only): the keys when it has just gone full screen, then the name of each scene the person brings to the screen
        osd_on = bool(cfg.get("osd", True))                                       # Sistema > Tela e áudio > "Dicas na tela cheia"
        if rend.fullscreen and not fs_prev and osd_on:
            osd.show(ndir.scene_name(ndir.scene), HINT, dur=4.5)
        elif rend.fullscreen and osd_on and not stage[0] and menu.osd_name is not None:          # (never in stage mode: that one faces an audience)
            osd.show(menu.osd_name[0], "", dur=2.4)
        menu.osd_name = None
        fs_prev = rend.fullscreen
        rend.osd_a = osd.alpha() if (rend.fullscreen and osd_on) else 0.0
        if rend.osd_a > 0.003:
            rend.set_osd(*osd.image(rend.size[1] or 720))
        # graphics options (Sistema > Imagem e qualidade)
        rend.steps, rend.bounces = max(24, int(cfg["steps"] * (0.55 + 0.45 * dyn))), 1          # dynamic quality: fewer ray steps too when the FPS is short
        rend.shadow_q, rend.ao_q, rend.refl_q = 1, 1, 1                      # (only used by the ray-traced lighting, which is off for now)
        am = cfg["aa_mode"]                                                       # 0 off, 1 edges, 2 FXAA, 3..5 MSAA 2x / 4x / 8x
        rend.aa, rend.fxaa, rend.msaa = (am in (1, 6)), (am == 2), {3: 1, 4: 2, 5: 3}.get(am, 0)
        rend.taa = am == 6
        rend.bloom_levels, rend.rt = (cfg["bloomq"] if cfg["fx_bloom"] else 0), False                  # ray tracing is switched off for now
        rend.sharp = (0.0, 0.35, 0.7, 1.2)[cfg["sharp"]]
        rend.bloom_shift = 1 + cfg["bloomres"]
        ac = {k: (ndir.cur.get(k, cfg[k]) if ndir.cur.get("ly_finish", True) else SC.LAYER_DEFAULTS[k]) for k in SC.ACAB_KEYS}     # the Acabamento of the scene on the air (off: neutral)
        rend.fin = (ac["fin_bright"] / 100.0, ac["fin_contrast"] / 100.0, ac["fin_sat"] / 100.0, ac["fin_gamma"] / 100.0, (ac["fin_temp"] - 2) / 2.0,
                    ac["scr_vig"] / 100.0, 1.0 if ac["fin_dither"] else 0.0, float(cfg["scr_mirror"]), cfg["scr_zoom"] / 100.0,
                    (0.0, 16 / 9, 21 / 9, 4 / 3, 1.0, 9 / 16)[cfg["scr_aspect"]], float(ac["img_style"]), float(ac["img_pix"]))
        rend.dist = (5.0, 9.0, 14.0)[cfg["dist"]]
        dyn_floor = max(0.1, min(1.0, cfg["dynmin"] / max(cfg["res"], 1)))
        ctl.interval = 1.0 / cfg["panel_fps"] if cfg.get("panel_fps", 0) > 0 else 0.0           # 0: the panel is redrawn with every output frame
        ctl.view = cfg["panel_view"]
        rend.mblur, rend.mblur_fps, rend.dt = 0, cfg["mblur_fps"], dt                 # the motion blur is out of the program for now (its settings are gone)
        rend.fx_trail, rend.fx_parts = cfg["fx_trail"], cfg["fx_parts"]
        if cfg["dynres"] and not test and bench is None:
            if clock_t - dyn_t > 0.6:                           # trade resolution for FPS: down fast, up slowly
                dyn_t = clock_t
                target = min(cfg["fps_out"], 240)                                    # "Sem limite" trades resolution for the 240 the screens go to
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
                tgt, cur = min(cfg["fps_out"], 240), int(cfg["preset"])
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
        an.riser_link = bool(cfg.get("link_riser", False))
        if cfg.get("link_vocal", False) and an.ear.vocal > 0.4:                      # a voice: the flashes calm down
            strobe_on *= 0.35
        an.max_sub = 1 if l_strobe < 2 else 8
        an.fl_len = (0.5, 1.0, 2.0)[max(0, min(2, int(live.get("fl_len", 1))))]
        an.fl_start = (0.25, 0.35, 0.5)[max(0, min(2, int(live.get("fl_start", 1))))]
        an.fl_roll = bool(live.get("fl_roll", True))
        drop_gain = (0.0, 0.6, 1.1)[max(0, min(2, int(live.get("fl_drop", 2))))]
        rend.flash_mode = int(live.get("fl_mode", 0))
        an.bursts_enabled = bool(live.get("bursts", cfg["bursts"])) and l_strobe == 2
        if cfg.get("link_vocal", False) and an.ear.vocal > 0.4:
            an.bursts_enabled = False
        rk = l_react / 100.0 * cfg.get("macro_energy", 100) / 100.0               # the Intensidade of the Palco on top of the scene's own
        if thumbs is not None:
            prof.mark_start()
            thumbs.feed(an, cfg, rk)
            prof.mark("UI/miniaturas das cenas (thumbs.feed)")
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
                menu.notes = " ".join(str(upd.info.get("notes") or "").split())[:160]
                if key.endswith(":0"):
                    menu.say(f"Nova versão {upd.info['version']} disponível (Sistema > Aplicativo)")
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

        err_r = remote.configure(cfg.get("remote_osc", False), cfg.get("remote_midi", False))
        if err_r:
            menu.say(err_r)
        err_s = phone.configure(cfg.get("phone_view", False))
        if err_s:
            menu.say(err_s)
            cfg["phone_view"] = False
        for k_ in remote.poll() + phone.poll():                                              # a controller or another program: the same as pressing the key
            rend.events.append({"event_type": "key_down", "key": k_, "remote": True})         # (marked: a controller may be driving a projection, no words on the picture)

        # hot reload of shaders
        for name in rend.poll_shaders():
            menu.say(f"Shader recarregado: {name}")

        # ------------------------------------------------------------ audio
        prof.mark("Resto/eventos, atalhos, comandos remotos e painel web")
        t_st = time.perf_counter()
        if syn is not None:
            an.feed(syn.chunk(int(rate * dt)))
        else:
            an.pump(cap, time.perf_counter())
            if cap.dev_name != cfg.get("adev", ""):                           # another audio device was picked in Ajustes
                try:
                    cap.dev_name = cfg.get("adev", "")
                    cap.reopen()
                    if cap.rate != an.rate:
                        an = Analyzer(cap.rate)
                    menu.say("Áudio: " + (cap.dev_name or "padrão do Windows"))
                except Exception:
                    pass
            if cap.frames != cfg["abuf"]:                                   # the buffer time was changed in Ajustes
                try:
                    cap.frames = int(cfg["abuf"])
                    cap.reopen()
                    menu.say(f"Buffer de áudio: {cap.frames / cap.rate * 1000:.0f} ms")
                except Exception:
                    pass
            if clock_t - last_dev_check > 2.0:
                last_dev_check = clock_t
                if cap.default_changed():
                    try:
                        if not cap.dev_name and cfg.get("adev"):                          # the picked device was unplugged
                            cfg["adev"] = ""
                            menu.touch()
                            menu.say("A entrada de áudio sumiu: voltei ao padrão do Windows")
                        cap.reopen()
                        if cap.rate != an.rate:
                            an = Analyzer(cap.rate)
                    except Exception:
                        pass
        prof.mark("áudio/entrada (captura ou sinal de teste) e troca de dispositivo")
        menu.apply_taps(an)                                                       # tap tempo asked for since the last frame (TAP, the T key, a controller)
        if time.perf_counter() >= fg_next:
            fg_next = time.perf_counter() + 0.5
            fg_watch.update(cfg, menu.play_scene)
        for rule in agenda_tk.check(cfg.get("agenda") or []):                       # the agenda: a rule of this minute brings its scene to the picture
            if fg_watch.paused:                                                     # a program's rule pauses the agenda while it is in front
                break
            scn_ = cfg.get("scenes") or []
            if 0 <= int(rule.get("scene", -1)) < len(scn_):
                menu.play_scene(int(rule["scene"]))
                menu.say(f"Agenda: {scn_[int(rule['scene'])].get('scene_name', '?')}")
        an.update(dt)
        prof.mark("áudio/análise (FFT, bandas, batida, estados da música)")
        vis = an                                             # what the picture follows: the real analyzer, always
        lap("áudio", t_st)
        if manual_drop:
            for a_ in (an, vis):
                a_.drop = a_.drop_b = a_.drop_event = 1.0
                a_.drop_flash = 1.0
        if ndir.log and menu.dirty is False and False:
            pass

        # --------------------------------------------------- procedural scene
        t_st = time.perf_counter()
        prof.mark("Resto/gestos de drop e checagens")
        params = ndir.update(dt, vis, cfg)
        params["glass_on"] = cfg["fx_glass"]
        lap("cena", t_st)
        prof.mark("cena/diretor (escolha de cena, câmera, movimento, parâmetros)")
        look.apply(rend, params, ndir.cur, cfg["detail"])                  # shader kind, room colour, the black scene
        prof.mark("cena/look: tipo de shader, cores e sala")
        gb, gm, gh = live.get("react_bass", 100) / 100.0, live.get("react_mid", 100) / 100.0, live.get("react_high", 100) / 100.0      # one gain per band
        rend.exposure = 1.1 * live.get("expo", 100) / 100.0
        params.update(bass=vis.bass * rk * gb, mid=vis.mid * rk * gm, high=vis.high * rk * gh, kick=vis.kick * rk, snare=vis.snare, hat=vis.hat,
                      beat=(vis.beat_n + vis.phase) if vis.bpm > 0 else clock_t * 2.0)
        if params.get("visual"):
            look.audio(params, vis)
        if not params.get("blank"):
            rend.bloom = live.get("bloom", cfg["bloom"]) / 100.0 * min(1.6, 0.6 + 0.4 * cfg.get("macro_energy", 100) / 100.0)
            rend.flash = min(1.0, max(max(vis.strobe, vis.burst_pulse) * strobe_on, vis.flash * strobe_on, vis.drop_flash * drop_gain)) * (1.0, 0.5, 0.12)[cfg["safe_flash"]]
        prof.mark("cena/ligar o som aos parâmetros e ao flash")
        skip = (cfg["rrate"] > 0 and frame % (cfg["rrate"] + 1) != 0) and not test       # render rate: 1 frame out of 2 or 3 (silence is no reason to draw less: the picture keeps going)
        rend.preview = (not test) and (menu.reserved > 0 or menu.tab == 0 or phone.wanted)        # the strip of the editor, the picture of the Palco, or a phone watching
        rend.preview_every = 3 if (menu.tab == 0 or phone.wanted) else 8                         # live: about 20 pictures a second
        t_st = time.perf_counter()
        prof.mark("Resto/preparar o quadro")
        frame_img = None if skip else rend.render(params)
        lap("GPU", t_st)
        prof.mark_start()
        if rend.preview and rend.preview_rgba is not None and rend.preview_n != pv_n:
            pv_n = rend.preview_n
            ctl.set_preview(rend.preview_rgba, rend.preview_size, rend.fmt)
            if phone.wanted:
                phone.push(rend.preview_rgba, rend.preview_size, rend.fmt)

        # ------------------------------------------------ control window + save
        ok, msg = rend.shader_status()
        menu.problem("shader", None if ok else "Erro no shader (usando o anterior): " + msg[:60])
        menu.problem("thumbs", None if thumbs is None or not thumbs.error else "Miniaturas ao vivo falharam")
        status = dict(gpu=rend.gpu_name, backend=rend.backend, shader_ok=ok, shader_msg=msg, reloads=rend.lib.reloads)
        status["keys"] = dict(fullscreen=rend.fullscreen, vsync=rend.vsync, strobe=l_strobe > 0, auto=cfg["effect"] == 0, stage=stage[0])
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
                status["image"] = dict(scene=ndir.scene_name(ndir.scene), scene_i=ndir.scene, pending_scene=params.get("pending_scene", -1), pending_eta=params.get("pending_eta"), scene_when=params.get("scene_when", 2), style=sty, camera=cam, movement=mov, why=why or None, since=max(0.0, ndir.age - t_ch))
            except Exception:
                pass
            status["look"] = ndir.look_name() + (f"  ·  gênero: {ndir.genre}" if ndir.genre != "?" else "")
            status["timing"] = dict(tm)
            t_st = time.perf_counter()
            prof.mark("Resto/prévia, estado e salvar configurações")
            ctl.update(time.perf_counter(), an, fps, lat, rend.vsync, status)
            lap("UI", t_st)
            if menu.dirty and time.perf_counter() - menu.dirty_t > 1.0:
                save_cfg(cfg)
                menu.dirty = False

        frame += 1
        if recorder is not None and recorder.step(clock_t, dt, tm):
            recorder.write(rend, cfg, PRESETS_N[int(cfg["preset"]) % len(PRESETS_N)])
            running = False
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
        pace = 0 if cfg["fps_out"] >= 246 else cfg["fps_out"]          # "Sem limite": no cap at all                                                                  # the output FPS: the picture is never drawn faster than this
        if not test and (not rend.vsync or skip) and pace > 0:                                 # a skipped frame (a long silence draws 1 in 6) never reaches the swap that vsync waits on: it needs the cap too, or the loop spins at 1500 fps
            target = 1.0 / pace
            prof.mark("Resto/fim do quadro")
            while time.perf_counter() - t_start < target:
                time.sleep(0.0005)
            prof.mark("Resto/limitador de FPS (espera para chegar à meta)")

    if test:
        print("diretor:", " | ".join(ndir.log), flush=True)
    if menu.dirty and not test:
        save_cfg(cfg)
    remote.close()
    phone.close()
    if thumbs is not None:
        thumbs.stop()
    ctl.destroy()
    rend.close()
    if cap:
        cap.close()
    pygame.quit()


stage = [False]


def stage_mode(on):
    """Stage mode (key P): the control window is minimised so only the picture is left; P or Esc brings it back."""
    if os.name != "nt" or on == stage[0]:
        return
    stage[0] = on
    import ctypes
    hwnd = ctypes.windll.user32.FindWindowW(None, "Audio Organism - Controles")
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 6 if on else 9)                 # SW_MINIMIZE / SW_RESTORE


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
