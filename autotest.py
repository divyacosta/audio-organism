"""A test driver for the real program: VIS_AUTOTEST names a JSON list of steps that the running program performs on its own control window
(see app.py). Kept out of app.py: only imported to run a script."""
import os
import time

import pygame


def _grab_screen(path, max_w=1400):
    """The primary screen as a PNG, shrunk to max_w wide. GDI through ctypes: the program does not ship Pillow. A test hook, nothing else uses it."""
    import ctypes
    from ctypes import wintypes
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
    hdc = user32.GetDC(0)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    gdi32.BitBlt(mdc, 0, 0, w, h, hdc, 0, 0, 0x00CC0020 | 0x40000000)           # SRCCOPY | CAPTUREBLT (layered windows too)
    bi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = (ctypes.c_ubyte * (w * h * 4))()
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(0, hdc)
    img = pygame.image.frombuffer(bytes(buf), (w, h), "BGRA").copy()
    pygame.surfarray.pixels_alpha(img)[:] = 255
    if w > max_w:
        img = pygame.transform.smoothscale(img, (max_w, int(h * max_w / w)))
    pygame.image.save(img, path)


def _seen(y, h, ctop, cbot):
    """How much of a control (top y, height h) is inside the viewport [ctop, cbot]: 2 = all of it, 1 = its centre (it can be clicked, an edge is cut), 0 = it cannot be clicked."""
    if ctop <= y and y + h <= cbot:
        return 2
    return 1 if ctop <= y + h // 2 <= cbot else 0


def _locate(ctl, mw, st):
    """Where a control is on the window, and how much of it is on the screen as the panel is scrolled NOW (a person cannot click what they cannot see).
    st["src"]: "live" (a button of the Palco, st["bid"]), "gal" (a hit of the gallery / the new-scene steps, st["kind"] and st["arg"]) or "menu" (a row or a tab, st["cid"]).
    Returns (found, seen 0..2 as in _seen, (x, y) on the window)."""
    px, py = ctl.panel_pos
    top = py + mw.HEAD + mw.reserved
    src = st["src"]
    if src == "live":
        best = (False, 0, None)
        for rect in [r for r, b in ctl.live.live_hits if b == st["bid"]]:                  # a control may be there twice (a button and a tile): the better placed one will do
            y = rect.y + mw.HEAD + mw.reserved - mw.scroll + py
            here = (True, _seen(y, rect.h, top, top + mw.content_h()), (rect.centerx + px, y + rect.h // 2))
            if not best[0] or here[1] > best[1]:
                best = here
        return best
    if src == "gal":
        rect = next((r for r, k, a in ctl.gal_hits if k == st["kind"] and a == st.get("arg", 0)), None)
        if rect is None:
            return False, 0, None
        bar = 64 if mw.in_wizard() and st["kind"] not in ("wz-next", "wz-back", "wz-cancel") else 0       # the bottom bar of the new-scene steps hides what is under it (its own buttons are on it)
        return True, _seen(rect.top, rect.h, top, top + mw.content_h() - bar), rect.center
    ent = next(((r, c) for r, c, k, a in mw.hits if c == st["cid"]), None)
    if ent is None:
        return False, 0, None
    rect = ent[0]
    if rect.bottom <= mw.HEAD:                                                       # the tab bar: it never scrolls
        return True, 2, (rect.centerx + px, rect.centery + py)
    right = mw.panes() and mw.in_right_pane(rect.x)
    y = py + mw.reserved + rect.y - (mw.scroll2 if right else mw.scroll)
    if mw.panes():
        ctop = top + mw.pane_dims()[0]
        cbot = ctop + mw.pane_view_h()
    else:
        ctop, cbot = top, top + mw.content_h()
    return True, _seen(y, rect.h, ctop, cbot), (rect.centerx + px, y + rect.h // 2)


def _tlog(auto, st, **kw):
    """One JSON line of the lay-user test (tests/lay.py reads them): what was done or seen, for which task, when."""
    import json
    kw.update(task=st.get("task"), label=st.get("label"), t=round(time.perf_counter() - auto["t0"], 2))
    with open(st["f"], "a", encoding="utf-8") as f_:
        f_.write(json.dumps(kw, ensure_ascii=False) + "\n")


def autotest_load():
    """A test hook: VIS_AUTOTEST names a JSON list of steps {"wait": s, "do": "click"|"key"|"shot"|"quit", ...} that the running program performs on its own
    control window (events go straight to the window code, the real mouse and screen are never touched; "shot" saves the panel as a PNG)."""
    path = os.environ.get("VIS_AUTOTEST")
    if not path:
        return None
    import json
    with open(path, encoding="utf-8") as f:
        return dict(steps=json.load(f), i=0, t=time.perf_counter(), t0=time.perf_counter())


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
            act = ctl.handle(types.SimpleNamespace(type=typ, pos=pos, **extra))
            if isinstance(act, str) and act.startswith("key:"):                  # a shortcut button of the Ao vivo tab
                auto["rend"].events.append({"event_type": "key_down", "key": act[4:]})
    elif do == "back":
        ctl.handle(types.SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, pos=(100, 300), button=6, buttons=(0, 0, 0)))
    elif do == "key":
        k = getattr(pygame, "K_" + st["k"])
        ctl.handle(types.SimpleNamespace(type=pygame.KEYDOWN, key=k, mod=0, unicode=st.get("char", "")))
    elif do == "wheel":
        ctl.handle(types.SimpleNamespace(type=pygame.MOUSEWHEEL, y=int(st.get("y", -5)), pos=(300, 400)))
    elif do == "tab":
        menu.press("tab%d" % int(st["n"]))
    elif do == "shot":
        ctl.force = True
        ctl.update(time.perf_counter(), None, 0, 0, False, None, force=True) if False else None
        pygame.image.save(ctl.surf, st["f"])
    elif do == "set":
        menu.set_value(st["id"], st["value"])
    elif do == "adjust":
        menu.adjust(st["id"], 0)
    elif do == "sym":
        sc_ = menu.cfg["scenes"][menu.cfg["scene_edit"]]
        with open(st["f"], "a", encoding="utf-8") as f_:
            f_.write(f"{st.get('tag', '')}: none={bool(menu.cfg.get('m_symnone'))} cuts={[k for k in range(8) if menu.cfg['m_sym%d' % k]]} scene={[k for k in range(8) if sc_['m_sym%d' % k]]} sceneNone={bool(sc_.get('m_symnone'))}\n")
    elif do == "rkey":                                           # a key pressed on the picture window (its events come from the canvas, not from pygame)
        auto["rend"].events.append(dict({"event_type": "key_down", "key": st["key"]}, **({"remote": True} if st.get("remote") else {})))       # "remote": a controller's key
    elif do == "livebtn":                                        # click the Ao vivo button of a shortcut, wherever it is on the scrolled panel
        want = st["bid"] if "bid" in st else "key:" + st["key"]                  # a shortcut button ("key": "v") or any button of the Palco ("bid": "macro:pal:2")
        rect = next((r for r, b in ctl.live.live_hits if b == want), None)
        mw = ctl.menu
        if rect is not None:
            mw.scroll = max(0, min(mw.max_scroll(), rect.centery - 200))        # the button is brought into view first
            pos = (rect.centerx + ctl.panel_pos[0], rect.centery + mw.HEAD + mw.reserved - mw.scroll + ctl.panel_pos[1])
            for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))),
                               (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
                act = ctl.handle(types.SimpleNamespace(type=typ, pos=pos, **extra))
                if isinstance(act, str) and act.startswith("key:"):
                    auto["rend"].events.append({"event_type": "key_down", "key": act[4:]})
    elif do == "winsize":                                        # the real window of the controls gets a new size (the program notices it by itself)
        ctl.win.size = (int(st["w"]), int(st["h"]))
    elif do == "maximize":
        ctl.win.maximize()
    elif do == "restore":
        ctl.win.restore()
    elif do == "winlog":
        with open(st["f"], "a", encoding="utf-8") as f_:
            f_.write(f"{st.get('tag', '')}: window={tuple(ctl.win.size)} panel={menu.W} wide={menu.wide} surf={ctl.surf.get_size()}\n")
    elif do == "palco":                                          # where the Palco ends up: are the scenes on screen without scrolling?
        mw = ctl.menu
        hits = [r for r, b in ctl.live.live_hits if str(b).startswith("scene:")]
        top = mw.HEAD + mw.reserved - mw.scroll + ctl.panel_pos[1]
        first = [r for r in hits if r.y == hits[0].y] if hits else []
        with open(st["f"], "a", encoding="utf-8") as f_:
            f_.write(f"{st.get('tag', '')}: window={tuple(ctl.win.size)} panel={mw.W} wide={mw.wide} tour={ctl.live.tour_open} marks={mw.cfg.get('tour_marks')} scenes={len(hits)} "
                     f"first_row_bottom={max((r.bottom for r in first), default=-1) + top} last_bottom={max((r.bottom for r in hits), default=-1) + top} "
                     f"end={ctl.live.live_end + top} fix={[b for _, b in ctl.live.live_hits if str(b).startswith('fix:')]}\n")
    elif do == "tclick":                                         # a lay user's click: only on what is on the screen now (no scrolling first); logged, and made with real events
        found, vis, pos = _locate(ctl, menu, st)
        if found and vis:                                        # vis: 2 all of it on the screen, 1 only its centre (it can be clicked, an edge is cut), 0 not on the screen
            for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))),
                               (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
                act = ctl.handle(types.SimpleNamespace(type=typ, pos=tuple(pos), **extra))
                if isinstance(act, str) and act.startswith("key:"):
                    auto["rend"].events.append({"event_type": "key_down", "key": act[4:]})
        _tlog(auto, st, ev="click", found=found, visible=int(vis), did=bool(found and vis), optional=bool(st.get("optional")))
    elif do == "tkey":                                           # a key typed in the control window
        ctl.handle(types.SimpleNamespace(type=pygame.KEYDOWN, key=getattr(pygame, "K_" + st["k"]), mod=0, unicode=st.get("char", "")))
        _tlog(auto, st, ev="key", k=st["k"])
    elif do == "trkey":                                          # a key pressed on the picture window
        auto["rend"].events.append({"event_type": "key_down", "key": st["key"]})
        _tlog(auto, st, ev="key", k=st["key"], window="imagem")
    elif do == "tlog":                                           # what the program shows now
        cfg = menu.cfg
        scn = cfg["scenes"]
        info = (ctl._last_status or {}).get("image") or {}
        r_ = auto["rend"]
        last = scn[-1]
        _tlog(auto, st, ev="state", tag=st.get("tag"), tab=menu.tab, view=menu.scene_view, wizard=(menu.wizard or {}).get("step"), effect=cfg["effect"], live=info.get("scene"),
              energy=cfg.get("macro_energy"), speed=cfg.get("macro_speed"), pal=cfg.get("macro_pal"), n=len(scn), last=last.get("scene_name"), last_pal=last.get("scene_palette"),
              last_auto=bool(last.get("scene_auto", True)), last_layers=[l_.get("t") for l_ in (last.get("layers") or [])], fullscreen=bool(r_.fullscreen), osd=round(float(getattr(r_, "osd_a", 0.0)), 2), sys_item=cfg.get("sys_item"),
              toast=(menu.toast[0] if menu.toast else None), auto_off=[s_.get("scene_name") for s_ in scn if not s_.get("scene_auto", True)], marks=cfg.get("tour_marks"),
              bpm=round(float(auto["an"].bpm), 1) if auto.get("an") is not None else None, manual=round(float(auto["an"].manual_bpm), 1) if auto.get("an") is not None else None)
    elif do == "desktop":                                        # the primary screen as the person sees it (both windows, the words on the picture), shrunk
        _grab_screen(st["f"])
    elif do == "rdouble":
        auto["rend"].events.append({"event_type": "double_click"})
    elif do == "state":
        r_ = auto["rend"]
        live = auto["ndir"].cur
        with open(st["f"], "a", encoding="utf-8") as f_:
            f_.write(f"{st.get('tag', '')}: fullscreen={r_.fullscreen} vsync={r_.vsync} strobe(live)={live.get('strobe')} effect={menu.cfg['effect']} "
                     f"drop_flash={auto['an'].drop_flash:.2f} log_last={(auto['ndir'].log or [''])[-1][:40]}\n")
    elif do == "call":                                           # a method of the menu without arguments (export_scenes, import_scenes ...)
        getattr(menu, st["name"])(*st.get("args", []))
    elif do == "log":
        with open(st["f"], "a", encoding="utf-8") as f_:
            f_.write(f"{st.get('tag', '')}: effect={menu.cfg['effect']} scenes={[s_['scene_name'] for s_ in menu.cfg['scenes']]} auto={[bool(s_.get('scene_auto', True)) for s_ in menu.cfg['scenes']]}\n")
    elif do == "dump":
        print("[autotest]", dict(view=menu.scene_view, tab=menu.tab, scenes=len(menu.cfg["scenes"]), card_menu=ctl.card_menu, effect=menu.cfg["effect"],
                                 hits=[(str(r), k, a) for r, k, a in ctl.gal_hits if k in ("mi", "menu")][:6]), flush=True)
    elif do == "quit":
        return True
    return False
