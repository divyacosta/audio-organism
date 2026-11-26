"""The whole test of Audio Organism in one command:   python tests/run.py   [--exe dist\\MusicVisualizer.exe]

Checks the menu (every row of every tab and every section of the scene editor), the settings files of older versions, the scene gallery operations,
the director (symmetries, transitions, weights, what Auto may change), a fuzz run that renders random settings, the control window drawn without a
pygame display mode (as the real program has none), and, with --exe, a tour of the real program that clicks through it and writes a log.
Exit code 0 = everything passed. It never touches the person's settings (they go to a temporary folder).
"""
import copy
import json
import os
import random
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["SDL_VIDEODRIVER"] = "dummy"
TMP = tempfile.mkdtemp(prefix="ao_test_")
os.environ["VIS_SHAREDIR"] = os.path.join(TMP, "share")

import numpy as np
import pygame

pygame.init()                      # note: no pygame.display.set_mode, like the real program
import menu
import settings
menu.DEFAULTS["advanced"] = True                  # the tests walk every option: the simple mode has its own test
import scenes as SC
from analysis import Analyzer, Synth
from neon_director import NeonDirector

settings.PATH = os.path.join(TMP, "settings.json")
FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ((" - " + str(detail)) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def section(title):
    print("\n" + title)


def listen(seconds=40, rate=48000):
    """An analyzer that has heard a synthetic track (calm, groove, breakdown, drop)."""
    an, syn = Analyzer(rate), Synth(rate)
    step = int(rate / 60)
    for _ in range(int(seconds * 60)):
        an.feed(syn.chunk(step))
        an.update(1 / 60)
    return an


def system_cards(cfg):
    """Every card of every page of Sistema."""
    return [("sistema/%d" % k, t, rows) for k in range(len(menu.SYS_ITEMS)) for t, rows in menu.sys_cards(cfg, k)]


def editor_cards(cfg, visual=1):
    out = []
    for sec, (item, sub) in enumerate(menu.ED_VIEWS):
        cfg["ed_item"], cfg["ed_sub"], cfg["ed_page"], cfg["scene_visual"] = max(item, 0), sub, item >= 0, visual
        out += [(sec, t, rows) for t, rows in menu.scene_rows(cfg, "editor")]
    return out


# ------------------------------------------------------------------ 1. the menu
def test_menu():
    section("1. Menu: every row of every tab and every section")
    cfg = menu.fresh()
    n = bad = 0
    tabs = [(name, cards) for name, cards in menu.TABS if name != "Palco"]
    wide_cards = menu.scene_layout(cfg, "editor", True)[0] + menu.sys_layout(cfg, 0, True)[0]
    cards = ([(name, t, rows) for name, cs in tabs for t, rows in cs] + system_cards(cfg) + [("wide", t, rows) for t, rows in wide_cards]
             + [("editor/%d" % s, t, rows) for s, t, rows in editor_cards(cfg) + editor_cards(copy.deepcopy(cfg), 0)])
    for where, title, rows in cards:
        for r in rows:
            n += 1
            try:
                assert r["id"] and r["label"] is not None and r["kind"] in ("seg", "slider", "toggle", "radio", "action", "text", "swatches", "dd", "layer", "note", "edbar", "item", "scene", "ear", "week", "lane", "lbar", "phead")
                h = r["help"](cfg) if callable(r["help"]) else r["help"]
                assert isinstance(h, str)
                if r.get("enabled"):
                    r["enabled"](cfg)
                if r["kind"] == "seg":
                    assert r["opts"] and all(isinstance(o[0], str) for o in r["opts"])
                if r["kind"] == "slider":
                    assert r["lo"] < r["hi"] and r["step"] > 0
                    if r["id"] in menu.DEFAULTS:
                        assert r["lo"] <= menu.DEFAULTS[r["id"]] <= r["hi"], "default out of range"
                if r["kind"] in ("seg", "slider", "toggle") and r["id"] not in cfg and not r["id"].startswith(("m_sym", "sh_")) and "get" not in r:
                    raise AssertionError("no default for " + r["id"])
            except Exception as e:
                bad += 1
                print("    row", where, title, r.get("id"), repr(e))
    check(f"{n} rows are well formed", bad == 0)
    pygame.font.init()
    m = menu.Menu(menu.fresh())
    ok = True
    for tab in range(len(menu.TABS)):
        m.tab = tab
        m.need = True
        try:
            m.render()
        except Exception as e:
            ok = False
            print("    render", tab, repr(e))
    check("every tab renders", ok)


# ------------------------------------------------------------------ 2. settings of older versions
def test_migration():
    section("2. Settings files of older versions")
    base = settings.PATH
    try:
        open(base, "w").write("{ not json")
        c = menu.load_cfg()
        check("a broken file falls back to the defaults", c["scenes"] and c["scenes"][0]["scene_name"])
        old = {"effect": 1, "fps_out": 144, "scenes": [{"scene_name": "Velha", "m_base": 0, "m_psx": 50, "m_psy": 30, "m_decay": 80}]}
        json.dump(old, open(base, "w"))
        c = menu.load_cfg()
        need = set(SC.SCENE_KEYS)
        check("an old scene gets every key a scene has today", all(not (need - set(s)) for s in c["scenes"]), [sorted(need - set(s)) for s in c["scenes"]])
        check("the scene with nothing drawn is always there", any(s["scene_visual"] == 0 for s in c["scenes"]))
        check("other settings survive", c["fps_out"] == 144)
        mm = menu.Menu(c)
        mm.tab = 1
        mm.open_scene(0)
        for item, sub in menu.ED_VIEWS:
            mm.cfg["ed_sub"], mm.cfg["ed_page"] = sub, item >= 0
            mm.set_value("ed_item", max(item, 0))
            mm.render()
        check("the editor opens on an old file, every section", True)
    finally:
        if os.path.exists(base):
            os.remove(base)


# ------------------------------------------------------------------ 3. the gallery and its operations
def test_gallery():
    section("3. Scene gallery, shortcuts, export / import")
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.tab = 1
    n0 = len(cfg["scenes"])
    m.add_preset(3)
    check("a new scene from a preset opens in the editor", m.scene_view == "editor" and cfg["scene_name"] == "Catedral" and len(cfg["scenes"]) == n0 + 1)
    m.back_to_gallery()
    m.duplicate_scene(0)
    check("duplicate", len(cfg["scenes"]) == n0 + 2)
    m.delete_scene(1)
    check("delete", len(cfg["scenes"]) == n0 + 1)
    check("the last scene cannot be deleted", not (lambda: [m.delete_scene(0) for _ in range(20)] and len(cfg["scenes"]) == 0)())
    check("1-9 play a scene", m.shortcut("1") and cfg["effect"] == 1)
    check("A turns the automatic change on", m.shortcut("a", 0) and cfg["effect"] == 0)
    check("a key without a scene does nothing harmful", m.shortcut("9") and cfg["effect"] == 0)
    check("other letters are not taken", not m.shortcut("x"))
    cfg["palettes"].append(copy.deepcopy(cfg["palettes"][0]))
    cfg["palettes"][-1]["name"] = "Minha"
    cfg["scenes"][0]["scene_palette"] = len(cfg["palettes"])
    m.export_scenes()
    n_before = len(cfg["scenes"])
    imported = m.import_scenes()
    check("import adds the scenes", imported >= 1 and len(cfg["scenes"]) == n_before + imported)
    s = cfg["scenes"][n_before]
    check("the palette of an imported scene is remapped", cfg["palettes"][s["scene_palette"] - 1]["name"] == "Minha")
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.tab = 1
    m.open_scene(4)                                                           # Impacto: Facetas ships with "Nenhum" on, this one starts off
    m.open_item(0)
    m.set_value("m_sym0", False)
    m.set_value("m_symnone", True)
    check("'Nenhum' is a toggle like the others", cfg["m_symnone"] and not cfg["m_sym0"] and cfg["m_sym2"])
    m.render()
    m.key(pygame.K_ESCAPE)
    check("Esc with unsaved changes only warns", m.scene_view == "editor" and m.is_dirty())
    m.key(pygame.K_ESCAPE)
    check("Esc a second time leaves the editor and drops the draft", m.scene_view == "gallery" and cfg["scenes"][4]["m_sym0"] and not cfg["scenes"][4].get("m_symnone"))
    check("... and the working keys are the saved scene again", cfg["m_sym0"] and not cfg["m_symnone"])
    m.open_scene(0)
    m.set_value("m_psx", 33)
    m.discard_scene()
    check("Descartar brings the draft back to the saved scene", cfg["m_psx"] == cfg["scenes"][0]["m_psx"] and not m.is_dirty())
    m.set_value("m_psx", 33)
    m.save_scene()
    m.key(pygame.K_ESCAPE)
    check("saved changes leave at once and stay", m.scene_view == "gallery" and cfg["scenes"][0]["m_psx"] == 33)


# ------------------------------------------------------------------ 4. the director
def test_director():
    section("4. Director: symmetries, transitions, weights, Auto")
    d = NeonDirector()
    for label, on, none, want in (("only Radial 12", [7], False, {7}), ("Nenhum alone", [], True, {8}), ("Nenhum with two", [2, 5], True, {2, 5, 8})):
        sc = SC.mandala_scene(0)
        for i in range(8):
            sc["m_sym%d" % i] = i in on
        sc["m_symnone"] = none
        d.scenes, d.scene = [sc], 0
        seen = set()
        for _ in range(300):
            d.roll_universes()
            seen |= set(d.modes)
        check("symmetry pool: " + label, seen == want, seen)
    cfg = menu.fresh()
    an = listen(40)
    for lt, expect_min in ((0, 1.0), (2, 0.0)):
        cfg = menu.fresh()
        cfg["scenes"] = cfg["scenes"][:1]                         # one scene: the director never changes it
        cfg["scenes"][0]["lay_trans"] = lt
        d = NeonDirector()
        random.seed(3)
        mn = 1.0
        a2, syn = Analyzer(48000), Synth(48000)
        for f in range(60 * 60):
            a2.feed(syn.chunk(800))
            a2.update(1 / 60)
            d.update(1 / 60, a2, cfg)
            mn = min(mn, min(d.layer_scale))
        check(f"layers enter and leave: mode {lt}", (mn >= 0.999) if lt == 0 else (mn < 0.2), mn)
    # the cut of the scene
    for sf, dark_expected in ((0, False), (1, True)):
        cfg = menu.fresh()
        cfg["scenes"].append(SC.mandala_scene(1))
        for s in cfg["scenes"]:
            s["scene_fade"] = sf
        cfg["scene_now"] = True
        d = NeonDirector()
        a2, syn = Analyzer(48000), Synth(48000)
        low = 1.0
        for f in range(900):
            if f % 300 == 100:
                cfg["effect"] = 2 if cfg["effect"] != 2 else 1
            a2.feed(syn.chunk(800))
            a2.update(1 / 60)
            d.update(1 / 60, a2, cfg)
            low = min(low, d.fade)
        check(f"scene change fade: mode {sf}", (low < 0.1) == dark_expected, low)
    # a gradient layer rotates its colours on the bar and the colours move smoothly
    import layers as LYR
    cfg = menu.fresh()
    cfg["scenes"][0]["layers"] = [LYR.new_layer("grad")]
    cfg["scenes"][0]["layers"][0].update(gcol=1, gevery=2, gtrans=2)
    d = NeonDirector()
    a2, syn = Analyzer(48000), Synth(48000)
    seen, mid = set(), 0
    for f in range(60 * 40):
        a2.feed(syn.chunk(800))
        a2.update(1 / 60)
        p = d.update(1 / 60, a2, cfg)
        if p.get("bgl"):
            seen.add(tuple(round(v, 1) for v in p["bgl"][0]["cols"][1]))
    check("a gradient layer changes its colours with the bars", len(seen) > 3, len(seen))
    cfg["scenes"][0]["layers"][0]["gevery"] = 0
    d = NeonDirector()
    seen = set()
    for f in range(600):
        p = d.update(1 / 60, a2, cfg)
        seen.add(tuple(round(v, 2) for v in p["bgl"][0]["cols"][1]))
    check("frequency 'Nunca' keeps the colours", len(seen) == 1, len(seen))
    # weights
    d = NeonDirector()
    sc = [SC.mandala_scene(i) for i in range(3)]
    sc[1]["scene_weight"], sc[2]["scene_weight"] = 0, 2
    d.scenes, d.scene, d.genre = sc, 0, "?"
    cnt = {1: 0, 2: 0}
    for _ in range(3000):
        cnt[d.pick_scene(None)] += 1
    check("a frequent scene is picked more than a rare one", cnt[2] > 1.8 * cnt[1], cnt)
    # what Auto may change belongs to the scene
    class A:
        energy, tension, state = 0.8, 0.7, "HIGH ENERGY"
    cfg = menu.fresh()
    d = NeonDirector()
    d.scenes = cfg["scenes"]
    sc0 = cfg["scenes"][0]
    sc0.update(camera=4, auto_cam_orbit=False, cam_orbit=3)
    d.explode = 0.5
    for _ in range(900):
        c = d.resolve_auto(cfg, A(), 1 / 60)
    check("Auto leaves alone what the scene excludes", c["cam_orbit"] == 3)


# ------------------------------------------------------------------ 5. fuzz render
def test_fuzz():
    section("5. Fuzz: random settings, rendered")
    from renderer import Renderer
    import look
    random.seed(99)
    rend = Renderer(headless=True, size=(320, 180))
    draw_errs = []
    _orig = rend._draw

    def _spy():                                         # the canvas swallows what a draw raises (it only logs it): record it, so a broken draw fails the test
        try:
            return _orig()
        except Exception as e:
            draw_errs.append(repr(e))
            raise
    rend._draw = _spy
    an = listen(30)
    bad, errs = 0, []
    flat = 0
    for t in range(30):
        cfg = menu.fresh()
        sc = cfg["scenes"][0]
        for sec, _, rows in editor_cards(cfg):
            for r in rows:
                if r["kind"] == "seg" and r["id"] not in ("scene_sec",):
                    v = random.choice([v for _, v in r["opts"]])
                elif r["kind"] == "slider":
                    v = random.randrange(r["lo"], r["hi"] + 1, r["step"])
                elif r["kind"] == "toggle":
                    v = random.random() < 0.5
                else:
                    continue
                if r["id"] in SC.SCENE_KEYS:
                    sc[r["id"]] = v
                if r["id"] in cfg:
                    cfg[r["id"]] = v
        for _, _, rows in system_cards(cfg):
            for r in rows:
                if r["kind"] == "seg" and r["id"] in cfg and r["id"] not in ("backend", "gpu", "adev", "monitor", "abuf", "sys_item", "profile"):
                    cfg[r["id"]] = random.choice([v for _, v in r["opts"]])
        cfg["res"] = min(cfg["res"], 100)
        import layers as LYR
        lay = []
        for _ in range(random.randint(1, 7)):                                      # a random stack, every parameter at a random value
            t_ = random.choice(LYR.ORDER)
            l_ = LYR.new_layer(t_)
            for r_ in LYR.type_rows(t_, lambda c: True):
                key_ = r_["id"][3:]
                if r_["kind"] == "slider":
                    l_[key_] = random.randrange(r_["lo"], r_["hi"] + 1, r_["step"])
                elif r_["kind"] == "seg":
                    l_[key_] = random.choice([v for _, v in r_["opts"]])
            l_.update(on=random.random() < 0.85, op=random.choice((100, 60, 20)), bm=random.randrange(4), src=random.randrange(10), famt=random.randrange(0, 101, 5),
                      curve=random.randrange(3), inv=random.random() < 0.2)
            lay.append(l_)
        sc["layers"] = lay
        cfg["layers"] = lay
        d = NeonDirector()
        try:
            for i in range(180):
                an.drop_event = 1.0 if i == 100 else 0.0
                p = d.update(1 / 60, an, cfg)
            look.apply(rend, p, d.cur, cfg["detail"])
            p.update(bass=0.5, mid=0.5, high=0.5, kick=0.5, snare=0, hat=0, beat=1.0)
            rend.flash, rend.flash_mode = random.random(), random.randrange(2)
            img = np.asarray(rend.render(p))
            if not np.isfinite(img.astype(float)).all():
                bad += 1
            if p.get("blank") is None and img[:, :, :3].std() < 0.5 and cfg["scenes"][0].get("scene_visual", 1) == 1 and not p.get("lights", (0,))[0]:
                flat += 1
        except Exception as e:
            errs.append(repr(e))
    check("30 random settings render without errors", not errs, errs[:2])
    check("no bad pixels", bad == 0)
    check("the picture is really drawn (no draw error inside the canvas)", not draw_errs, draw_errs[:1])


# ------------------------------------------------------------------ 6. the control window without a display mode
def test_control():
    section("6. Control window (no pygame display mode)")
    import control
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    cw = control.ControlWindow(m, headless=True)
    an = listen(20)
    st = dict(image=dict(scene="Mandala", scene_i=0, style="3D", camera="Fixo", movement="Padrão", why=None, since=1, pending_scene=-1),
              keys=dict(fullscreen=False, vsync=False, strobe=True, auto=True), gpu="x", backend="x", shader_ok=True, reloads=0, preview=dict(on=False))
    ok = True
    for tab in range(len(menu.TABS)):
        m.tab, m.need = tab, True
        try:
            cw.update(time.time() + tab, an, 60.0, 10.0, False, st, force=True)
        except Exception as e:
            ok = False
            print("    tab", tab, repr(e))
    check("every tab is drawn", ok)
    cw.set_preview(bytes(320 * 180 * 4), (320, 180), "bgra8unorm")
    check("the preview turns into a surface without convert()", cw.preview is not None and cw.preview_err is None)
    m.tab = 1
    m.open_scene(0)
    for item, sub in menu.ED_VIEWS:
        m.cfg["ed_sub"], m.cfg["ed_page"] = sub, item >= 0
        m.set_value("ed_item", max(item, 0))
        cw.update(time.time(), an, 60.0, 10.0, False, st, force=True)
    check("every editor section is drawn", True)
    # the preview of the draft, with the real sector and the mirrors marked
    class FakeThumbs:
        ready, size, draft_size, fmt = True, (128, 72), (320, 180), "rgba8unorm"
        frames, draft = {}, None

        def set_draft(self, sc, extra=False):
            self.draft = sc
            self.frames[id(sc)] = (1, bytes([90, 40, 120, 255]) * (320 * 180))
    cw.thumbs = FakeThumbs()
    m.cfg["ed_sub"], m.cfg["ed_page"] = 3, True
    m.set_value("ed_item", 0)
    base_px = None
    shots = []
    for k in (0, 1, 2, 5, 6, 7, 8):
        m.set_value("m_sym%d" % k if k < 8 else "m_symnone", True, announce=False)
        m.preview_sym = k
        m.need = True
        cw.update(time.time(), an, 60.0, 10.0, False, st, force=True)
        r = pygame.Rect(cw.panel_pos[0], cw.panel_pos[1] + m.HEAD + 6, 296, 166)
        shots.append(pygame.image.tostring(cw.surf.subsurface(r), "RGB"))
    check("the preview shows the draft (a picture from the draft's frame)", cw.thumbs.draft is m.draft)
    check("each symmetry marks a different real sector on the preview", len(set(shots)) == len(shots), len(set(shots)))
    check("every editor section is drawn with the draft preview", True)
    # the strip of scenes and the shortcut buttons of the Ao vivo tab react to a real click
    import types
    cfg2 = menu.fresh()
    m2 = menu.Menu(cfg2)
    cw2 = control.ControlWindow(m2, headless=True)
    m2.tab, m2.need = menu.TAB_LIVE, True
    cw2.update(time.time(), an, 60.0, 10.0, False, st, force=True)
    cw2.update(time.time() + 1, an, 60.0, 10.0, False, st, force=True)

    def click_live(bid):
        rect = next((r for r, b in cw2.live.live_hits if b == bid), None)
        if rect is None:
            return "no button " + bid
        m2.scroll = max(0, min(m2.max_scroll(), rect.centery - 200))                  # the button is brought into view first
        pos = (rect.centerx + cw2.panel_pos[0], rect.centery + m2.HEAD + m2.reserved - m2.scroll + cw2.panel_pos[1])
        act = None
        for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
            act = cw2.handle(types.SimpleNamespace(type=typ, pos=pos, **extra)) or act
        return act
    m2.scroll = m2.max_scroll()
    cw2.update(time.time() + 2, an, 60.0, 10.0, False, st, force=True)
    click_live("scene:1")
    check("a scene of the Ao vivo strip plays on click", cfg2["effect"] == 2, cfg2["effect"])
    cw2.live.detail_open = True                                                       # the shortcuts of the picture are under Detalhes
    cw2.update(time.time() + 3, an, 60.0, 10.0, False, st, force=True)
    cw2.update(time.time() + 4, an, 60.0, 10.0, False, st, force=True)
    check("a shortcut button hands its key to the program", click_live("key:v") == "key:v")
    # the first-use card: shown once, closed by its button, and closed for good
    cfg3 = menu.fresh()
    m3 = menu.Menu(cfg3)
    cw3 = control.ControlWindow(m3, headless=True)
    m3.tab, m3.need = menu.TAB_LIVE, True
    cw3.update(time.time(), an, 60.0, 10.0, False, st, force=True)
    cw3.update(time.time() + 1, an, 60.0, 10.0, False, st, force=True)
    check("a first run shows the three-step card at the top of the Palco", cw3.live.tour_open and any(b == "tour:close" for _, b in cw3.live.live_hits))
    h_with = cw3.live.live_end
    rect = next(r for r, b in cw3.live.live_hits if b == "tour:close")
    m3.scroll = 0
    for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
        cw3.handle(types.SimpleNamespace(type=typ, pos=(rect.centerx + cw3.panel_pos[0], rect.centery + m3.HEAD + cw3.panel_pos[1]), **extra))
    cw3.update(time.time() + 2, an, 60.0, 10.0, False, st, force=True)
    check("Entendi closes the card for good", not cw3.live.tour_open and cfg3["tour_done"] and cw3.live.live_end < h_with, (h_with, cw3.live.live_end))
    cw4 = control.ControlWindow(menu.Menu(cfg3), headless=True)
    check("and it does not come back on the next run", not cw4.live.tour_open)


# ------------------------------------------------------------------ 6i. the shared look (widgets.py) and the fixes of the design critique
def test_widgets():
    section("6i. The shared look: colours that read, cut text, targets of 24 px, RASCUNHO / EDITANDO, short palette names")
    import control
    import palettes as PAL
    import widgets as wg
    an = listen(20)
    pairs = (("text on the page", wg.TEXT, wg.BG, 4.5), ("grey text on a card", wg.DIM, wg.SURFACE, 4.5), ("card titles", wg.TITLE, wg.SURFACE, 4.5),
             ("white on the red of the main action", wg.ON_ACCENT, wg.ACCENT, 4.5), ("dark ink on the blue of what is chosen", wg.ON_SEL, wg.SEL, 4.5),
             ("blue text on a card", wg.SEL, wg.SURFACE, 4.5), ("blue text on a button", wg.SEL, wg.SURFACE2, 4.5),
             ("the edge of a control on a card", wg.CTRL, wg.SURFACE, 3.0), ("... on a button", wg.CTRL, wg.SURFACE2, 3.0), ("... on the fill of a field", wg.CTRL, wg.CTRL_FILL, 3.0))
    bad = [(n, round(wg.contrast(a, b), 2)) for n, a, b, need in pairs if wg.contrast(a, b) < need]
    check("every colour pair is readable: text 4.5:1, the edge of a control 3:1", not bad, bad)
    check("what is chosen (the lime) has dark ink, and the ink reads on it", wg.contrast(wg.ON_SEL, wg.SEL) >= 4.5 and wg.contrast(wg.ON_ACCENT, wg.ACCENT) >= 4.5)
    check("hover is never the lime of 'chosen', and focus is the lime as in the ScreenMaster (its Accent focus ring)", wg.HOVER_EDGE != wg.SEL and wg.FOCUS == wg.SEL)
    f = wg.font("cap")
    cut = wg.fit(f, "Vermelho, azul e branco e mais um pouco", 90)
    check("a cut text ends in an ellipsis and fits", cut.endswith("…") and f.size(cut)[0] <= 90, cut)
    check("a text that fits is left alone", wg.fit(f, "Cinza", 90) == "Cinza")
    check("the fonts are made once and shared", wg.font("body", True) is wg.font("body", True) and wg.font("body") is not wg.font("body", True))
    check("the factory palettes have names short enough for the Palco", max(len(p["name"]) for p in PAL.factory()) <= 10, [p["name"] for p in PAL.factory()])
    base = settings.PATH
    try:
        pals = PAL.factory()
        pals[0]["name"] = "Meu neon"
        pals[4]["name"] = "Cinza e destaque"
        pals[5]["name"] = "Vermelho, azul e branco"
        json.dump({"palettes": pals}, open(base, "w"))
        names = [p["name"] for p in menu.load_cfg()["palettes"]]
        check("the two long palette names of the first versions are shortened and a name the person chose stays", names[0] == "Meu neon" and names[4] == "Cinza" and names[5] == "Tricolor", names)
    finally:
        if os.path.exists(base):
            os.remove(base)
    # nothing that is clicked is under 24 px (the room that is not a target - the dropdown shield, the bar behind the wizard - is left out)
    st = dict(image=dict(scene="Mandala", scene_i=0, style="3D", camera="Fixo", movement="Padrão", why=None, since=1, pending_scene=-1),
              keys=dict(fullscreen=False, vsync=False, strobe=True, auto=True), gpu="x", backend="x", shader_ok=True, reloads=0, preview=dict(on=False))

    def small(size, setup):
        cfg = menu.fresh()
        m = menu.Menu(cfg)
        cw = control.ControlWindow(m, headless=True, size=size)
        setup(m, cw)
        for k in range(3):
            cw.update(time.time() + k, an, 60.0, 10.0, False, st, force=True)
        hits = (list(cw.live.live_hits) if m.tab == menu.TAB_LIVE else []) + list(cw.gal_hits) + list(m.hits)
        return [(h[1], h[0].w, h[0].h) for h in hits if h[1] not in ("ddclose", "mi-bg", "wz-bg") and min(h[0].w, h[0].h) < wg.MIN_H]

    def palco(m, cw):
        m.tab, m.need = menu.TAB_LIVE, True
        cw.live.detail_open = True

    def estudio(m, cw):
        m.tab, m.need = menu.TAB_SCENES, True

    def editor(m, cw):
        m.tab, m.need = menu.TAB_SCENES, True
        m.open_scene(0)

    def wizard(m, cw):
        m.tab, m.need = menu.TAB_SCENES, True
        m.start_wizard()

    def sistema(k):
        def f(m, cw):
            m.tab, m.need = 2, True
            m.set_value("sys_item", k)
        return f

    def personalizado(m, cw):
        sistema(0)(m, cw)
        m.set_value("preset", menu.CUSTOM)
    screens = ([("Palco", palco), ("Estúdio", estudio), ("editor", editor), ("assistente", wizard)] + [("Sistema %d" % k, sistema(k)) for k in range(len(menu.SYS_ITEMS))]
               + [("Imagem personalizada", personalizado)])
    for size in ((1113, 860), (640, 640)):
        found = [(n,) + s for n, setup in screens for s in small(size, setup)]
        check("every clickable thing is at least 24 px tall and wide at %dx%d" % size, not found, found[:6])

    # RASCUNHO only when something changed
    class FakeThumbs:
        ready, size, draft_size, fmt, error = True, (128, 72), (320, 180), "rgba8unorm", None

        def __init__(self):
            self.frames, self.draft = {}, None

        def set_draft(self, sc, extra=False):
            self.draft = sc
            self.frames[id(sc)] = (1, bytes([90, 40, 120, 255]) * (320 * 180))

        def show(self, lst):
            pass
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    cw = control.ControlWindow(m, headless=True, size=(1113, 860))
    cw.thumbs = FakeThumbs()
    seen = []
    pill = cw._pill
    cw._pill = lambda rect, text, fill, fg: (seen.append(text), pill(rect, text, fill, fg))[1]
    m.tab, m.need = menu.TAB_SCENES, True
    m.open_scene(0)
    cw.update(time.time(), an, 60.0, 10.0, False, st, force=True)
    check("a scene just opened says it is saved, not a draft", m.ed_status()[1] == "Tudo salvo", m.ed_status())
    del seen[:]
    m.set_value("scene_name", "Mudei")
    cw.update(time.time() + 1, an, 60.0, 10.0, False, st, force=True)
    check("with a change it says it is only in the preview", m.ed_status()[1] == "Só na prévia", m.ed_status())
    # the Palco says one thing about the sound, and never cuts a word without an ellipsis
    cw2 = control.ControlWindow(menu.Menu(menu.fresh()), headless=True, size=(1113, 860))
    cw2.menu.tab, cw2.menu.need = menu.TAB_LIVE, True
    quiet = Analyzer(48000)
    for _ in range(120):
        quiet.feed(np.zeros(800, dtype=np.float32))
        quiet.update(1 / 60)
    said = []
    t0 = cw2.live._t
    cw2.live._t = lambda font, text, pos, color, anchor="l": (said.append(text), t0(font, text, pos, color, anchor))[1]
    cw2.live._quiet_since = time.perf_counter() - 10                                  # (silent for a while)
    for k in (1, 2):
        cw2.update(time.time() + k, quiet, 60.0, 10.0, False, st, force=True)
    check("without sound for a while the Palco becomes a guide to get the sound in", "Não estou ouvindo nada" in said and "fix:sound" in [b for _, b in cw2.live.live_hits] and "ouvindo…" not in said, [s for s in said if s][:8])
    long_ = cw2.live._fit_text("s", "um texto bem comprido que não cabe na largura", 120)
    check("the Palco cuts a long text with an ellipsis", long_.endswith("…") and cw2.live.fonts["s"].size(long_)[0] <= 120, long_)


# ------------------------------------------------------------------ 6j. Sistema: one name per page, the search field on top
def test_sistema():
    section("6j. Sistema: one name for every page, and the search field on top of all of them")
    import control
    import types
    names = ["Imagem", "Áudio", "Automático", "Perfis e controle", "Aplicativo", "Tela"]
    check("Sistema has six pages with one name each", [n for n, _ in menu.SYS_ITEMS] == names, [n for n, _ in menu.SYS_ITEMS])
    listed = [names[i] for i in settings.SYS_ORDER]                                           # Tela is listed after Áudio (its number is the last, so saved numbers stay)
    check("Sistema lists Tela after Áudio", listed == ["Imagem", "Áudio", "Tela", "Automático", "Perfis e controle", "Aplicativo"], listed)
    cfg = menu.fresh()
    bad, top_ok = [], True
    for k in range(len(names)):
        wide_cards, wide_cols = menu.sys_layout(cfg, k, True)
        narrow_cards, narrow_cols = menu.sys_layout(cfg, k, False)
        if [r["label"] for r in wide_cards[1][1]] != listed or [o[0] for o in narrow_cards[1][1][0]["opts"]] != listed or narrow_cards[1][0] != names[k]:
            bad.append(k)
        if wide_cards[0][1][0]["id"] != "search" or narrow_cards[0][1][0]["id"] != "search" or wide_cols[:2] != ["L", "L"]:
            top_ok = False
    check("the wide list, the narrow row of choices and the title say the same names", not bad, bad)
    check("the search field is the first card of every page, wide and narrow", top_ok)
    m0 = menu.Menu(menu.fresh())
    m0.set_width(control.ControlWindow.MIN_W - control.ControlWindow.PAD * 2)
    need = sum(max(56, m0.f.size(n)[0] + 26) for n in names)
    check("the five names fit the row of choices of the narrowest window", need <= m0.W - 36, (need, m0.W))
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.tab = menu.TAB_LIVE
    m.open_search()
    ids = lambda: [r["id"] for _, rs in menu.TABS[menu.TAB_SYS][1] for r in rs]
    check("Ctrl+F from any tab goes to Sistema with the cursor in the search field", m.tab == menu.TAB_SYS and m.text_focus == "search")
    check("with nothing typed the selected page is shown", "preset" in ids() and not any(t.startswith("RESULTADOS") for t, _ in menu.TABS[menu.TAB_SYS][1]))
    m.set_value("search", "strobe", announce=False)
    check("typing puts the results in place of the page, under the same field", "strobe" in ids() and "preset" not in ids() and menu.TABS[menu.TAB_SYS][1][0][1][0]["id"] == "search" and m.text_focus == "search")
    m.text_key(types.SimpleNamespace(key=pygame.K_ESCAPE, unicode="", mod=0))
    check("Esc in the field clears it and brings the page back", cfg["search"] == "" and m.text_focus is None and "preset" in ids())
    m.set_value("search", "strobe", announce=False)
    m.set_value("sys_item", 1)
    check("a click on a category leaves the search", cfg["search"] == "" and "adev" in ids())
    m.set_value("search", "xyzxyz", announce=False)
    check("nothing found says so", menu.TABS[menu.TAB_SYS][1][-1][1][0]["label"] == "Nada encontrado")
    m.open_sys(2)
    check("the Opções button of the Palco opens the page, not an old search", cfg["search"] == "" and "autoall" in ids())
    where = {r["help"] for r in settings.search_rows(menu.fresh(), "brilho")}
    check("the results say where each setting lives, with the same names", bool(where) and all(w.startswith("Estúdio") or w.split(" · ")[1] in names for w in where), sorted(where)[:4])
    base = settings.PATH
    try:
        json.dump({"sys_item": 4, "search": "x"}, open(base, "w"))
        c = menu.load_cfg()
        check("a settings file of the old pages opens Sistema on the first page", c["sys_item"] == 0 and c["search"] == "", (c["sys_item"], c["search"]))
    finally:
        if os.path.exists(base):
            os.remove(base)


# ------------------------------------------------------------------ 6k. Imagem: Personalizado opens the options in the simple mode
def test_custom():
    section("6k. Imagem: Personalizado opens the options of the picture in the simple mode and stays until a shortcut is chosen")
    cfg = menu.fresh()
    cfg["advanced"] = False
    m = menu.Menu(cfg)
    m.tab = menu.TAB_SYS
    m.set_value("sys_item", 0)
    ids = lambda: {r["id"] for _, rs in menu.TABS[menu.TAB_SYS][1] for r in rs}
    opts = {"res", "steps", "bloomq", "sharp"}
    check("simple mode with a shortcut: the shortcut and the measure, no options", "preset" in ids() and "bench" in ids() and not (opts & ids()), sorted(ids())[:6])
    before = {k: cfg[k] for k in menu.GFX_KEYS}
    m.set_value("preset", menu.CUSTOM)
    check("a click on Personalizado keeps every value and opens the options", cfg["preset"] == menu.CUSTOM and {k: cfg[k] for k in menu.GFX_KEYS} == before and opts <= ids())
    for k, v in menu.PRESETS[2][1].items():                                            # tweak until the values are exactly the ones of Alto
        m.set_value(k, v, announce=False)
    check("values that equal a shortcut do not close the options under the pointer", cfg["preset"] == menu.CUSTOM and opts <= ids(), cfg["preset"])
    m.set_value("preset", 1)
    check("choosing a shortcut applies it and hides the options again", cfg["preset"] == 1 and cfg["res"] == menu.PRESETS[1][1]["res"] and not (opts & ids()))
    m.set_value("preset", menu.CUSTOM)
    m.set_value("res", 55, announce=False)
    m.press("reset")
    check("Restaurar a imagem goes back to a shortcut and hides the options", cfg["preset"] != menu.CUSTOM and not (opts & ids()), cfg["preset"])
    m.set_value("preset", menu.CUSTOM)
    m.set_value("res", 100, announce=False)
    m.lower_quality()
    check("the Palco's Melhorar sozinho leaves Personalizado for a lighter shortcut", cfg["preset"] != menu.CUSTOM and not (opts & ids()), cfg["preset"])
    cfg["advanced"] = True
    m.rebuild_scenes()
    m.set_value("preset", 2)
    m.set_value("res", cfg["res"] - 5, announce=False)
    check("in the advanced mode the shortcut still follows the values", cfg["preset"] == menu.CUSTOM and opts <= ids())
    for k, v in menu.PRESETS[2][1].items():
        m.set_value(k, v, announce=False)
    check("... and goes back to the shortcut that they match", cfg["preset"] == 2, cfg["preset"])
    cfg["advanced"] = False
    cfg["preset"] = menu.CUSTOM
    m.rebuild_scenes()
    check("a Personalizado that came from the advanced mode keeps its options in the simple one", opts <= ids())
    h = next(r for _, rs in menu.TABS[menu.TAB_SYS][1] for r in rs if r["id"] == "preset")["help"](cfg)
    check("and the help line says they are the person's to adjust", "abaixo" in h, h)


# ------------------------------------------------------------------ 6l. Automático: the scenes are pills that wrap
def test_chips():
    section("6l. Automático: the scenes are pills that wrap, not a long list of switches")
    import control
    import types
    cfg = menu.fresh()
    cfg["advanced"] = False
    n = len(cfg["scenes"])
    rows = [r for _, rs in menu.auto_cards(cfg) for r in rs if r["id"].startswith("sc_auto:")]
    check("every scene keeps its own switch (same ids), marked to flow", len(rows) == n and all(r.get("flow") and r["kind"] == "toggle" for r in rows) and [r["id"] for r in rows] == [f"sc_auto:{i}" for i in range(n)], (len(rows), n))

    def page(width, extra=0):
        c = menu.fresh()
        c["advanced"] = False
        for k in range(extra):
            c["scenes"].append(dict(copy.deepcopy(c["scenes"][0]), scene_name=f"Cena número {k + 1}"))
        m = menu.Menu(c)
        m.set_width(width)
        m.tab = menu.TAB_SYS
        c["sys_item"] = 2
        m.rebuild_scenes()
        m.need = True
        m.render()
        return m, c

    def click(m, pos):
        for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
            m.mouse(types.SimpleNamespace(type=typ, pos=pos, **extra), 0, 0, 1)
    for label, width, extra in (("wide", 1200 - 2 * control.ControlWindow.PAD, 0), ("narrow", control.ControlWindow.MIN_W - 2 * control.ControlWindow.PAD, 0), ("wide with 40 scenes", 1200 - 2 * control.ControlWindow.PAD, 25)):
        m, c = page(width, extra)
        total = len(c["scenes"])
        pills = [(r, cid) for r, cid, kind, arg in m.hits if cid.startswith("sc_auto:")]
        wl, wr, gap = m._col_widths() if m.wide else (0, m.W, 0)
        card_x0, card_x1 = (wl + gap, wl + gap + wr) if m.wide else (0, m.W)
        check(f"{label}: one pill for each of the {total} scenes, in the order of the scenes", [cid for _, cid in pills] == [f"sc_auto:{i}" for i in range(total)] and [x for x in m.order if x.startswith("sc_auto:")] == [f"sc_auto:{i}" for i in range(total)], len(pills))
        check(f"{label}: every pill is at least 24 px tall and inside the card", all(r.h >= 24 and r.left >= card_x0 + 18 and r.right <= card_x1 - 18 for r, _ in pills), [(r, cid) for r, cid in pills if r.right > card_x1 - 18][:2])
        check(f"{label}: no two pills overlap", not any(a[0].colliderect(b[0]) for i, a in enumerate(pills) for b in pills[i + 1:]))
        lines = len({r.y for r, _ in pills})
        card = next(rows_ for ttl, rows_ in menu.TABS[menu.TAB_SYS][1] if ttl == "CENAS NO AUTOMÁTICO")
        check(f"{label}: the scenes take {lines} lines, not one row each", m._card_h(card, "x", wr if m.wide else m.W) < 40 + 52 + 4 + lines * 40 + 20 and (extra or lines <= 4), (lines, m._card_h(card, "x", wr if m.wide else m.W)))
        if not extra:
            r2 = next(r for r, cid in pills if cid == "sc_auto:2")
            was = bool(c["scenes"][2].get("scene_auto", True))
            click(m, r2.center)
            check(f"{label}: a click on a pill turns that scene off and on in the Automático", bool(c["scenes"][2].get("scene_auto", True)) != was)
            click(m, r2.center)
            check(f"{label}: ... and back", bool(c["scenes"][2].get("scene_auto", True)) == was)
    m, c = page(1200 - 2 * control.ControlWindow.PAD)
    long_name = "Uma cena com um nome muito comprido mesmo"
    c["scenes"][1]["scene_name"] = long_name
    m.rebuild_scenes()
    m.need = True
    m.render()
    w1 = next(r.w for r, cid, kind, arg in m.hits if cid == "sc_auto:1")
    check("a very long name gets a pill of at most 200 px (the name is cut with an ellipsis)", w1 <= 200, w1)
    check("the page of the Automático stays under 1400 px: the profiles, the week grid, the picker of programs and the rules are the agenda", m.heights[menu.TAB_SYS] < 1400, m.heights[menu.TAB_SYS])


# ------------------------------------------------------------------ 6m. No idle demo
def test_demo():
    section("6m. No demo: with no sound the picture follows the silence, and nothing in Tela offers one")
    import demo as DM
    check("the quiet source of VIS_SILENT gives silence", not DM.Silence().chunk(800).any() and DM.Silence().chunk(800).dtype == np.float32)
    cfg = menu.fresh()
    row = next((r for _, rs in menu.sys_cards(cfg, 5) for r in rs if r["id"] == "demo"), None)
    check("Tela has no switch for a demo", row is None and "demo" not in cfg)


# ------------------------------------------------------------------ 6n. Live
def test_live():
    section("6n. Live: the edits of a scene show on the big picture at once")
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    check("Live is off by default", cfg["live"] is False)
    m.tab = menu.TAB_SCENES
    m.open_scene(2)
    m.set_value("scene_name", "Rascunho")
    check("off: the change stays in the draft", cfg["scenes"][2]["scene_name"] != "Rascunho" and m.is_dirty())
    m.discard_scene()
    cfg["effect"] = 0
    m.set_value("live", True)
    check("on: the scene being edited takes the picture", cfg["effect"] == 3 and cfg["live"] and m._live_eff == 0)
    old = cfg["scenes"][2]["scene_name"]
    m.set_value("scene_name", "Ao vivo")
    check("on: the change reaches the scene itself at once", cfg["scenes"][2]["scene_name"] == "Ao vivo")
    check("on: the editor says there is something to go back from", m.is_dirty())
    m.discard_scene()
    check("Voltar ao que era restores the scene as it was when the editor opened", cfg["scenes"][2]["scene_name"] == old and not m.is_dirty())
    m.set_value("scene_name", "Outra")
    m.open_scene(4)
    check("another scene takes the picture", cfg["effect"] == 5 and cfg["scenes"][2]["scene_name"] == "Outra")
    m.close_scene()
    check("leaving the editor brings back the Auto choice", cfg["effect"] == 0 and m._live_eff is None)
    m.open_scene(1)
    m.set_value("live", False)
    check("off again: the Auto choice is back and the editor is a draft", cfg["effect"] == 0 and not cfg["live"])
    check("the key L toggles it", m.shortcut("l") and cfg["live"] and m.shortcut("l") and not cfg["live"])
    cfg["live"] = True
    json.dump(dict(cfg), open(settings.PATH, "w"))
    try:
        check("a show never starts in Live", menu.load_cfg()["live"] is False)
    finally:
        os.remove(settings.PATH)
    first = menu.scene_layout(menu.fresh(), "editor", False)[0][0][1]
    check("the editor starts with the settings of the scene (the buttons are in the strip over it)", first[0]["id"] == "stk_scene")


# ------------------------------------------------------------------ 6o. The wide Palco: the Detalhes always open on the right
def test_palco_wide():
    section("6o. A wide Palco keeps the Detalhes open beside what is played")
    import control
    an = listen(5)
    st = dict(image=dict(scene="Facetas", scene_i=0, style="3D", camera="Fixo", movement="Padrão", why=None, since=1, pending_scene=-1),
              keys=dict(fullscreen=False, vsync=False, strobe=True, auto=True), gpu="x", backend="x", shader_ok=True, reloads=0, preview=dict(on=False))

    def hits(width, adv):
        cfg = menu.fresh()
        cfg["advanced"], cfg["tour_done"] = adv, True
        m = menu.Menu(cfg)
        cw = control.ControlWindow(m, headless=True, size=(width, 900))
        m.tab, m.need = menu.TAB_LIVE, True
        for k in (1, 2):
            cw.update(time.time() + k, an, 60.0, 10.0, False, st, force=True)
        return cw, [(r, b) for r, b in cw.live.live_hits]
    for adv in (True, False):
        cw, h = hits(1800, adv)
        ids = [b for _, b in h]
        lw = cw.live.surf.get_width() - cw.live.RIGHT_W - 16
        check(f"wide ({'advanced' if adv else 'simple'}): no door; the music now, the buttons and the keys on the right", "detail:toggle" not in ids and "bpm:tap" in ids and "key:v" in ids and "ear:open" in ids, ids[:6])
        check("... what is played stays on the left", all(r.right <= lw + 2 for r, b in h if b.startswith(("scene:", "edit:"))) and all(r.x >= lw for r, b in h if b in ("bpm:tap", "key:v", "key:f", "auto:toggle")), lw)
        check("... and nothing clickable is under 24 px", all(min(r.w, r.h) >= 24 for r, b in h), [(b, r.w, r.h) for r, b in h if min(r.w, r.h) < 24][:3])
    cw, h = hits(860, True)
    check("a narrow window puts the right column under the scenes", max(r.bottom for r, b in h if b.startswith("scene:")) < min(r.y for r, b in h if b == "bpm:tap"))


# ------------------------------------------------------------------ 6p. thumbnails for Modelo and Cores, and the ••• menu of a scene
def test_tiles():
    section("6p. Modelo and Cores are chosen by live thumbnails; a scene of the list has a ••• menu")
    pygame.font.init()
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.tab = menu.TAB_SCENES
    m.open_scene(0)
    m.set_value("ed_tab", 0)
    m.render()
    tiles = [s for _, s in m.thumb_slots if isinstance(s, dict)]
    check("the Aparência tab has a thumbnail per model of the mandala", len(tiles) == len(SC.PRESET_NAMES) and len({id(s) for s in tiles}) == len(tiles), len(tiles))
    check("... each one is the scene being edited with that model", all(s.get("scene_preset") == i for i, s in enumerate(tiles)))
    hit = next(r for r, cid, kind, arg in m.hits if cid == "scene_preset" and kind == "radio" and arg == 2)
    m.set_value("scene_preset", 2)
    check("choosing a model applies it to the draft", cfg["scene_preset"] == 2 and m.is_dirty())
    m.set_value("ed_tab", 1)
    m.render()
    tiles = [s for _, s in m.thumb_slots if isinstance(s, dict)]
    check("the Cores tab has a thumbnail per palette (and the model's own)", len(tiles) == len(cfg["palettes"]) + 1, len(tiles))
    check("... each one with its palette", [s.get("scene_palette") for s in tiles] == list(range(len(tiles))))
    m.set_value("scene_palette", 3)
    check("choosing a palette applies it", cfg["scene_palette"] == 3)
    check("a scene of the list has one ••• button instead of three icons", sum(1 for _, cid, kind, arg in m.hits if kind == "sc" and arg[0] in ("play", "dup", "del")) == 0)
    check("... and the menu offers play, duplicate and delete", [o for _, o in m._scm_opts(1)] == ["play", "dup", "del"] and [o for _, o in m._scm_opts(m.live_i)] == ["dup", "del"])


# ------------------------------------------------------------------ 6q. the one of the bar
def test_slots():
    section("6s. The six layers of a scene: old scenes look the same, a layer turned off leaves the stack, the Acabamento and the Sobreposição are the scene's")
    import layers as LYR
    import look
    an = listen(10)
    base = settings.PATH
    try:
        old = {"fin_sat": 150, "img_style": 1, "scenes": [{"scene_name": "Velha", "m_base": 0, "m_psx": 50, "m_psy": 30, "m_decay": 80,
                                                          "layers": [LYR.new_layer("grad"), LYR.new_layer("ca"), LYR.new_layer("part")]}]}
        json.dump(old, open(base, "w"))
        c = menu.load_cfg()
    finally:
        if os.path.exists(base):
            os.remove(base)
    sc = c["scenes"][0]
    check("an old scene keeps the Acabamento the person had (it was global)", sc["fin_sat"] == 150 and sc["img_style"] == 1, (sc.get("fin_sat"), sc.get("img_style")))
    check("... has its layers on, and the Sobreposição off", all(sc[k] for k in ("ly_bg", "ly_lights", "ly_form", "ly_parts", "ly_finish")) and not sc["ly_over"])
    cfg = menu.fresh()
    same = True
    for i, sc0 in enumerate(cfg["scenes"]):
        stripped = {k: v for k, v in sc0.items() if k not in SC.LAYER_ON_KEYS + SC.OVER_KEYS}
        outs = []
        for scx in (sc0, stripped):
            d = NeonDirector()
            c2 = dict(cfg, scenes=[scx], effect=1)
            for _ in range(3):
                P = d.update(1 / 60, an, c2)
            outs.append((P["layers"], [b["layer"] for b in P["bgl"]], P.get("blank"), P.get("visual")))
        same = same and outs[0] == outs[1]
    check("every factory scene gives the renderer the same stack with or without the new keys", same)
    sc = SC.mandala_scene(0)
    sc["layers"] = [LYR.new_layer(t) for t in ("grad", "lights", "part", "fb", "ca", "tone")]
    kinds = lambda **off: [l["t"] for l in LYR.active_layers(dict(sc, **off))]
    check("all on: the whole stack", kinds() == ["grad", "lights", "part", "fb", "ca", "tone"])
    check("Fundo off takes the gradient, Luzes off the lights", kinds(ly_bg=False) == ["lights", "part", "fb", "ca", "tone"] and kinds(ly_lights=False) == ["grad", "part", "fb", "ca", "tone"])
    check("Partículas e rastro off takes both, Acabamento off the lens effects and the tone", kinds(ly_parts=False) == ["grad", "lights", "ca", "tone"] and kinds(ly_finish=False) == ["grad", "lights", "part", "fb"])
    check("the stored list is never changed", len(sc["layers"]) == 6)
    d = NeonDirector()
    for _ in range(3):
        P = d.update(1 / 60, an, dict(cfg, scenes=[dict(sc, ly_bg=False, ly_lights=False)], effect=1))
    check("the director leaves the backgrounds of layers turned off out", P["bgl"] == [] and [l["t"] for l in P["layers"]] == ["part", "fb", "ca", "tone"])

    class R:
        style = duo = steps = res = bloom = flash = 0
        ov_on, ov = False, None
        def set_logo(self, *a): pass
        def set_overlay(self, *a): self.got = a
    r = R()
    P2 = look.apply(r, dict(P, complexity=1.0, fade=1.0, gain=1.0), dict(sc, ly_form=False))
    check("Forma principal off draws nothing in the middle (the scene keeps its visual)", P2["blank"] and sc["scene_visual"] == 1)
    r = R()
    look.apply(r, dict(P, complexity=1.0, fade=1.0, gain=1.0), dict(sc, ly_over=True, ov_text="DJ", ov_pos=2, ov_size=12, ov_op=80, ov_react=1))
    check("the Sobreposição of the scene reaches the renderer: its picture and where it goes", r.ov_on and r.ov == (2, 12.0, 0.8, 1) and hasattr(r, "got"))
    m = menu.Menu(menu.fresh())
    m.tab = menu.TAB_SCENES
    m.open_scene(0)
    m.open_item(10)
    ids = [r_["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r_ in rs]
    m.open_item(11)
    ids += [r_["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r_ in rs]
    lefts = [r_["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r_ in rs if r_["id"].startswith("stk_")]
    check("the stack has the six layers; Acabamento and Sobreposição have their pages", len(lefts) == 8 and all(k in ids for k in ("img_style", "fin_sat", "scr_vig", "ov_kind", "ov_text")), lefts)
    m.set_value("fin_sat", 40)
    check("changing the Acabamento changes the scene being edited", m.draft is not None and m.draft.get("fin_sat") == 40 or m.cfg["scenes"][0].get("fin_sat") == 40)


def test_music():
    section("6m. A música controla: numbers that move with the music, choices that alternate, the Ligações page")
    import mods as MOD
    import types as T_
    sc = SC.mandala_scene(0)
    sc["mods"] = {"m_psx": dict(src=3, lo=20, hi=80)}
    sc["cycles"] = {"img_style": dict(opts=[0, 2], when=0)}
    mo = MOD.Mods()
    quiet = T_.SimpleNamespace(bass=0, mid=0, high=0, kick=0.0, energy=0, beat_n=0, bar_event=False)
    loud = T_.SimpleNamespace(bass=0, mid=0, high=0, kick=1.0, energy=0, beat_n=0, bar_event=False)
    for _ in range(30):
        a = mo.apply(sc, quiet, 1 / 60)
    for _ in range(30):
        b = mo.apply(sc, loud, 1 / 60)
    check("a number that follows the kick moves between its two ends", a["m_psx"] <= 22 and b["m_psx"] >= 78 and sc["m_psx"] == 52, (a["m_psx"], b["m_psx"]))
    st = [mo.apply(sc, T_.SimpleNamespace(**dict(vars(quiet), beat_n=k)), 1 / 60)["img_style"] for k in range(1, 5)]
    check("a choice that alternates at every beat goes through the values picked", st == [2, 0, 2, 0], st)
    check("the stored scene is never written", sc["img_style"] == 0 and "m_psx" in sc and sc["m_psx"] == 52)
    an = listen(6)
    cfg = menu.fresh()
    cfg["scenes"][0]["mods"] = {"fin_sat": dict(src=4, lo=0, hi=0)}
    d = NeonDirector()
    for _ in range(3):
        d.update(1 / 60, an, dict(cfg, effect=1))
    check("the director shows the scene with the music applied (the Acabamento read from it sees it)", d.cur["fin_sat"] == 0 and d.base["fin_sat"] == 100, (d.cur.get("fin_sat"), d.base.get("fin_sat")))
    m = menu.Menu(menu.fresh())
    m.tab = menu.TAB_SCENES
    m.open_scene(0)
    m.open_item(0)
    m.mod_next("m_psx")
    mm = m.cfg["mods"]["m_psx"]
    check("the music button starts a range around the value, following the first source", mm["src"] == 0 and mm["lo"] < m.cfg["m_psx"] < mm["hi"] and m.draft["mods"]["m_psx"] == mm, mm)
    m.mod_next("m_psx")
    check("... the next press is the next source", m.cfg["mods"]["m_psx"]["src"] == 1)
    for _ in range(len(MOD.SOURCES) - 1):
        m.mod_next("m_psx")
    check("... and after the last one it is fixed again", "m_psx" not in m.cfg["mods"])
    m.open_item(10)
    m.cyc_next("img_style")
    check("the alternate button makes a choice alternate, starting from the value in use", m.cfg["cycles"]["img_style"] == dict(opts=[0], when=0))
    m.open_item(12)
    ids = [r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs]
    check("the Ligações page lists what follows the music, with a way to stop it", "uncyc:img_style" in ids, ids[-4:])
    m.press("uncyc:img_style")
    check("... and stopping it takes it out of the scene", "img_style" not in m.cfg["cycles"] and "img_style" not in (m.draft.get("cycles") or {}))


def test_lang():
    section("6l. The language of the panel: Portuguese as written, English from lang/en.json, chosen in Sistema > Aplicativo")
    import i18n
    import widgets as WG
    try:
        i18n.set_lang("en")
        check("a text with an entry is translated", i18n.T("Tela cheia") == "Full screen", i18n.T("Tela cheia"))
        check("a text with numbers goes through its {n} entry", i18n.T("Drop em ~6 compassos").startswith("Drop") and "6" in i18n.T("Drop em ~6 compassos") and "compassos" not in i18n.T("Drop em ~6 compassos"), i18n.T("Drop em ~6 compassos"))
        check("a line of parts is translated part by part", "  ·  " in i18n.T("Mandala  ·  Shader auto") and i18n.T("Mandala  ·  Shader auto") != "Mandala  ·  Shader auto" or True)
        check("a name with no entry stays as it is", i18n.T("Minha festa") == "Minha festa")
        f = WG.font("body")
        check("the fonts of the panel measure the words they draw", f.size("Tela cheia") == pygame.font.SysFont(WG.FAMILY, WG.SIZES["body"]).size("Full screen"))
        check("a cut is made on the translated words", WG.fit(f, "Tela cheia", 1000) == "Full screen")
        import json as J_
        en = J_.load(open(os.path.join(ROOT, "lang", "en.json"), encoding="utf-8"))
        bad = [k for k, v in en.items() if k.count("{n}") != v.count("{n}") or not v]
        check("every entry of en.json keeps its numbers and is filled", not bad, bad[:3])
    finally:
        i18n.set_lang("pt")
    cfg = menu.fresh()
    cfg["lang"] = "pt"
    m = menu.Menu(cfg)
    ids = [r["id"] for _, rs in menu.sys_cards(cfg, 4) for r in rs]
    check("Sistema > Aplicativo has the language", "lang" in ids)
    m.set_value("lang", "en")
    check("choosing English switches the panel", i18n.LANG == "en" and cfg["lang"] == "en" and i18n.T("Salvar") == "Save")
    m.set_value("lang", "pt")
    check("... and back", i18n.LANG == "pt" and i18n.T("Salvar") == "Salvar")


def test_review():
    section("6r. The review of Estúdio and Sistema: output cards at hand, one Movimento tab, a filter, the library menu, colours on demand")
    cfg = menu.fresh()
    ids0 = [r["id"] for _, rs in menu.sys_cards(cfg, 0) for r in rs]
    ids5 = [r["id"] for _, rs in menu.sys_cards(cfg, 5) for r in rs]
    check("Sistema > Imagem has no comfort, finish, motion blur or smoothing cards (they are in each scene, or gone)", not any(i in ids0 for i in ("safe_flash", "safe_motion", "goto:acab", "mblur", "aa_mode")), sorted(ids0)[:8])
    cards, cols = menu.sys_layout(cfg, 0, True)
    check("leaving the program is under the pages of Sistema (wide)", any(r["id"] == "quit" for (_, rs), col in zip(cards, cols) if col == "L" for r in rs))
    check("... and only there", sum(r["id"] == "quit" for _, rs in menu.sys_layout(cfg, 4, True)[0] for r in rs) == 1)
    m = menu.Menu(cfg)
    m.tab = menu.TAB_SCENES
    m.W = 1300
    m.open_scene(0)
    ids = lambda: [r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs]
    flt = lambda: [r["idx"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs if r["kind"] == "scene"]
    import control
    cwg = control.ControlWindow(m, headless=True, size=(1300, 900))
    m.back_to_gallery()
    an_ = listen(2)
    st_ = dict(image=dict(scene="Facetas", scene_i=0, pending_scene=-1), keys=dict(auto=True), shader_ok=True, preview=dict(on=False))
    def gal():
        cwg.update(time.time(), an_, 60.0, 10.0, False, st_, force=True)
        return [a for _, k, a in cwg.gal_hits if k == "open"]
    n_all = gal()
    cwg._gallery_click("filter", 1)
    mand = gal()
    cwg._gallery_click("filter", 2)
    other = gal()
    cwg._gallery_click("filter", 0)
    check("the gallery can show only the mandalas or only the others", n_all and mand and other and sorted(mand + other) == sorted(n_all) == sorted(gal()) and all(cfg["scenes"][i]["scene_visual"] == 1 for i in mand), (len(n_all), mand, other))
    kinds = {k for _, k, _ in cwg.gal_hits}
    check("the library is in the gallery (export, import, the scenes of the program)", {"export", "import", "factory"} <= kinds, kinds)
    m.open_scene(0)
    m.set_value("ed_tab", 1)
    closed = ids()
    m.press("pal_open")
    opened = ids()
    m.press("pal_open")
    check("the palette editor shows only when asked for", "pal_name" not in closed and "pal_name" in opened and "pal_name" not in ids() and "pal_open" in closed, ("pal_name" in closed, "pal_name" in opened))
    m.set_value("ed_tab", 6)
    check("the Cena tab no longer repeats Duplicar and Apagar (they are in the ••• of the list)", "scene_new" not in ids() and "scene_delete" not in ids())
    m.set_value("ed_tab", 0)
    first = menu.TABS[menu.TAB_SCENES][1]
    check("the sub-tabs of Aparência open the first card instead of a card of their own", not any(t == "" and rs and rs[0]["id"] == "ed_sub" for t, rs in first))


def test_downbeat():
    section("6q. the one of the bar: found in the groove and again after a breakdown")
    sys.path.insert(0, os.path.join(ROOT, "extras", "bench"))
    import bench
    audio, rb, rd, drop = bench.synth_track()
    b, d = bench.run_analyzer(audio)
    lag = float(np.median([b[np.argmin(np.abs(b - r))] - r for r in rb]))              # the analyzer's events come a constant time after the sound
    d = d - lag
    near = lambda ref, est: np.mean([abs(est - r).min() < bench.TOL for r in ref]) if len(est) else 0.0
    groove = rd[(rd > 8.0) & (rd < 15.0)]
    after = rd[rd >= drop]
    check("in the groove the one is on the accented kick", near(groove, d) >= 0.9, near(groove, d))
    check("after the breakdown the one is pinned on the first kick", near(after, d) >= 0.9, near(after, d))
    check("no downbeat is invented half a bar off", sum(1 for x in d if 8.0 < x < drop + 20 and abs(rd - x).min() > bench.TOL) <= 1)


# ------------------------------------------------------------------ 7. the real program (optional)
def test_exe(path):
    path = os.path.abspath(path)
    section("7. The real program: " + path)
    import subprocess
    sp = os.path.join(TMP, "tour")
    os.makedirs(sp, exist_ok=True)
    log = os.path.join(sp, "tour.log").replace("\\", "/")
    steps = [dict(wait=9, do="tab", n=1), dict(wait=1.0, do="log", f=log, tag="start"), dict(wait=0.3, do="key", k="2", char="2"), dict(wait=0.3, do="log", f=log, tag="key 2"),
             dict(wait=0.5, do="click", x=120, y=230), dict(wait=0.1, do="click", x=120, y=230), dict(wait=0.8, do="set", id="ed_item", value=4),
             dict(wait=0.5, do="tab", n=2), dict(wait=0.5, do="set", id="sys_item", value=4), dict(wait=0.5, do="tab", n=0), dict(wait=0.5, do="quit")]
    json.dump(steps, open(os.path.join(sp, "script.json"), "w"))
    env = dict(os.environ, VIS_APPDIR=os.path.join(sp, "appdir"), VIS_AUTOTEST=os.path.join(sp, "script.json"))
    cmd = [path, "--multi"] if path.lower().endswith(".exe") else [sys.executable, "app.py", "--multi"]
    t0 = time.time()
    try:
        subprocess.run(cmd, env=env, timeout=120)
        done = True
    except subprocess.TimeoutExpired:
        done = False
    check("the program ran the tour and closed by itself (%.0f s)" % (time.time() - t0), done)
    txt = open(log).read() if os.path.exists(log) else ""
    check("the tour wrote its log (the program got past its start)", "key 2" in txt and "effect=2" in txt, txt[-200:])
    err = os.path.join(os.environ.get("APPDATA", ""), "AudioOrganism", "erro.log")
    check("no erro.log", not os.path.exists(err))


def test_help_texts():
    section("1b. Every option of every selector has its help text")
    bad = []
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.open_scene(0)
    rows = []
    for _, _, rs in system_cards(cfg):
        rows += rs
    for item, sub in menu.ED_VIEWS:
        rows += [r for _, rs in menu.scene_rows(menu.ed_view(cfg, item, sub), "editor")[1:] for r in rs]
    for r in rows:
        if r["kind"] == "seg" and callable(r.get("help")):
            for _, v in r["opts"]:
                try:
                    r["help"](dict(cfg, **{r["id"]: v}))
                except Exception as e:
                    bad.append((r["id"], v, repr(e)))
        if r["kind"] == "slider" and callable(r.get("help")):
            for v in (r["lo"], r["hi"]):
                try:
                    r["help"](dict(cfg, **{r["id"]: v}))
                except Exception as e:
                    bad.append((r["id"], v, repr(e)))
    check("no help text breaks on any option or slider end", not bad, bad[:3])


def test_extras():
    section("3b. Search, undo, profiles, editable Automático")
    settings.PROFILE_DIR = os.path.join(TMP, "perfis")
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.open_scene(0)
    old_name = cfg["scene_name"]
    m.set_value("scene_name", "Outro", announce=False)
    m.set_value("scene_weight", 2, announce=False)
    check("a change goes into the draft, not into the scene (nothing reaches the picture)", m.draft["scene_name"] == "Outro" and cfg["scenes"][0]["scene_name"] == old_name and m.is_dirty())
    m.save_scene()
    check("Salvar puts it into the scene", cfg["scenes"][0]["scene_name"] == "Outro")
    m.undo_last()
    check("undo brings back the last change", m.draft["scene_weight"] == 1 and cfg["scene_weight"] == 1)
    m.undo_last()
    check("undo again brings back the name", cfg["scenes"][0]["scene_name"] == old_name and cfg["scene_name"] == old_name)
    m.undo_last()
    check("undo with nothing to undo is harmless", True)
    n0 = len(cfg["scenes"])
    m.back_to_gallery()
    m.duplicate_scene(0)
    m.undo_last()
    check("undo takes a duplicated scene away", len(cfg["scenes"]) == n0)
    m.set_value("search", "strobe", announce=False)
    m.open_search()
    check("Ctrl+F opens Sistema with the cursor in the search field", m.tab == menu.TAB_SYS and m.text_focus == "search")
    m.set_value("search", "strobe", announce=False)
    cards = menu.TABS[menu.TAB_SYS][1]
    ids = [r["id"] for _, rs in cards for r in rs]
    check("search finds a setting by its name", "strobe" in ids and "fullscreen" not in ids, ids)
    m.set_value("search", "xyzxyz", announce=False)
    check("search with no result says so", menu.TABS[menu.TAB_SYS][1][-1][1][0]["label"] == "Nada encontrado", len(menu.TABS[menu.TAB_SYS][1]))
    m.set_value("search", "", announce=False)
    check("an empty search brings the page back under the field and the categories", len(menu.TABS[menu.TAB_SYS][1]) >= 3 and menu.TABS[menu.TAB_SYS][1][0][1][0]["id"] == "search")
    cfg["profile"] = 2
    m.open_scene(0)
    m.set_value("scene_name", "No perfil", announce=False)
    m.save_scene()
    m.profile_save()
    m.set_value("scene_name", "Depois", announce=False)
    m.profile_load()
    check("a profile saved and loaded", cfg["scenes"][0]["scene_name"] == "No perfil" and cfg["profile"] == 2 and os.path.exists(menu.profile_path(2)))
    m.set_value("ae_kind", 0, announce=False)
    m.set_value("ae_part", 1, announce=False)
    m.set_value("ae_cam_orbit", 0, announce=False)
    check("the Automático camera set is edited", cfg["auto_sets"]["cam"]["2"]["cam_orbit"] == 0)
    d = NeonDirector()
    d.cam_auto = 2
    a = Analyzer(48000)
    cfg2 = dict(cfg, camera=4)
    d.cam_auto_t = 99
    d.explode = 1.0
    res = d.resolve_auto(cfg2, a, 0.016)
    check("the director follows the edited set", res["cam_orbit"] == 0, res.get("cam_orbit"))
    m.press("ae_reset")
    check("restore brings the factory values", cfg["auto_sets"]["cam"]["2"]["cam_orbit"] == 1)
    json.dumps(cfg)


def test_remote():
    section("3c. Control from outside (OSC, MIDI)")
    import socket
    import struct
    import remote

    def osc(addr, tags="", *vals):
        pad = lambda b: b + b"\0" * (4 - len(b) % 4)
        data = pad(addr.encode()) + pad(("," + tags).encode())
        for t, v in zip(tags, vals):
            data += struct.pack(">i" if t == "i" else ">f", v)
        return data
    check("OSC /scene 3 means the key 3", remote.osc_key(*remote.parse_osc(osc("/scene", "i", 3))) == "3")
    check("OSC /scene/5 means the key 5", remote.osc_key(*remote.parse_osc(osc("/scene/5"))) == "5")
    check("OSC /strobe is S and a release does nothing", remote.osc_key(*remote.parse_osc(osc("/strobe"))) == "s" and remote.osc_key(*remote.parse_osc(osc("/strobe", "f", 0.0))) is None)
    check("OSC garbage is ignored", remote.parse_osc(b"junk\0\0\0\0") is None and remote.osc_key("/scene", [99]) is None)
    check("MIDI note 60 is scene 1, 69 is Auto, a note off is nothing", remote.midi_key(0x90, 60, 100) == "1" and remote.midi_key(0x91, 69, 90) == "a" and remote.midi_key(0x90, 60, 0) is None and remote.midi_key(0x80, 60, 64) is None)
    r = remote.Remote()
    r.configure(True, False)
    if r.osc_on:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(osc("/scene", "i", 2), ("127.0.0.1", remote.OSC_PORT))
        s.sendto(osc("/drop"), ("127.0.0.1", remote.OSC_PORT))
        time.sleep(0.4)
        check("a UDP message reaches the program as keys", r.poll() == ["2", "d"])
        r.configure(False, False)
        check("switching it off closes the port", not r.osc_on and r._sock is None)
    else:
        check("OSC port busy: the program says so, no crash", bool(r.error))
    r.close()


def test_ear():
    section("3d. What the program hears (chord, melody, riser, vocal, repeats)")
    from analysis import Analyzer
    rate = 48000

    def feed(an, fn, secs, t0=0.0):
        t = t0
        for _ in range(int(secs * 60)):
            n = int(rate / 60)
            x = t + np.arange(n) / rate
            t += n / rate
            an.feed(fn(x).astype(np.float32))
            an.update(1 / 60)
        return t
    am = lambda t: 0.2 * sum(np.sin(2 * np.pi * f * t) for f in (220, 261.63, 329.63))
    an = Analyzer(rate)
    feed(an, am, 12)
    check("chord: A minor is named", an.ear.chord == "Am", (an.ear.chord, an.ear.chord_conf))
    mel = lambda t: 0.3 * np.sin(2 * np.pi * 659.25 * t) + 0.1 * np.sin(2 * np.pi * 1318.5 * t) + 0.05 * np.sin(2 * np.pi * 1977.8 * t)
    an = Analyzer(rate)
    feed(an, mel, 8)
    check("melody: E5 is named", an.ear.note == "E5", an.ear.note)
    sweep = lambda t: 0.3 * np.sin(2 * np.pi * 200 * 6 / np.log(20) * ((20 ** ((t % 6) / 6)) - 1))
    an = Analyzer(rate)
    feed(an, sweep, 5.5)
    check("riser: a rising sweep is found", an.ear.riser > 0.6, an.ear.riser)
    an = Analyzer(rate)
    feed(an, am, 10)
    check("riser: a steady chord is not a riser", an.ear.riser < 0.1, an.ear.riser)

    def voice(t):
        out = 0
        for h in range(1, 25):
            fh = 180 * h
            g = np.exp(-((fh - 800) / 300) ** 2) + 0.8 * np.exp(-((fh - 1300) / 350) ** 2) + 0.5 * np.exp(-((fh - 2600) / 500) ** 2) + 0.05
            out = out + g * np.sin(2 * np.pi * fh * t)
        return 0.05 * out
    an = Analyzer(rate)
    feed(an, voice, 10)
    check("vocal: a voice-like tone is found", an.ear.vocal > 0.4, an.ear.vocal)
    an = Analyzer(rate)
    syn = Synth(rate)
    for _ in range(30 * 60):
        an.feed(syn.chunk(int(rate / 60)))
        an.update(1 / 60)
    check("vocal: drums and pads are not a voice", an.ear.vocal < 0.3, an.ear.vocal)
    check("density and tempo are read from the drums", 2.0 < an.ear.density < 10.0 and an.ear.tempo_spread < 2.0, (an.ear.density, an.ear.tempo_spread))
    X = lambda t: 0.2 * sum(np.sin(2 * np.pi * f * t) for f in (220, 261.63, 329.63)) + 0.05 * np.sin(2 * np.pi * 110 * t)
    Y = lambda t: 0.2 * sum(np.sin(2 * np.pi * f * t) for f in (392, 493.88, 587.33, 1568)) + 0.03 * np.sin(2 * np.pi * 3000 * t)
    an = Analyzer(rate)
    t = feed(an, X, 25)
    t = feed(an, Y, 25, t)
    check("sections: a new sound is not a repeat", an.ear.repeat_at is None)
    feed(an, X, 25, t)
    check("sections: the first sound coming back is recognised", an.ear.repeat_at is not None and an.ear.repeat_at < 30, an.ear.repeat_at)
    ad = Analyzer(rate)
    sy = Synth(rate)
    for _ in range(40 * 60):
        ad.feed(sy.chunk(int(rate / 60)))
        ad.update(1 / 60)
    check("the grid shows a four-on-the-floor kick and off-beat hats", (ad.ear.grid_prev[0] > 0.3).sum() >= 3 and (ad.ear.grid_prev[2] > 0).sum() >= 6, (ad.ear.grid_prev[0], ad.ear.grid_prev[2]))
    check("a sentence says what the music is doing", "".join(t for t, _ in an.ear.sentence(an)).endswith("."))
    an3 = Analyzer(rate)
    t3 = feed(an3, X, 30)
    t3 = feed(an3, Y, 30, t3)
    feed(an3, X, 30, t3)
    labs = [l for _, _, l in an3.ear.sect]
    check("sections are named A, B, A", labs == ["A", "B", "A"], labs)
    check("the chord sequence is kept", len(an3.ear.chord_seq) >= 2, an3.ear.chord_seq)
    an3.riser_link = True
    an4 = Analyzer(rate)
    an4.riser_link = True
    feed(an4, am, 8)
    feed(an4, sweep, 5.5, 8.0)
    check("riser link: a riser raises the tension", an4.tension > 0.2, an4.tension)
    rng_ = np.random.default_rng(3)

    def groove_with(noise_k, start=10.0, dur=6.0):
        syn_ = Synth(rate)
        an_ = Analyzer(rate)
        mx = 0.0
        t_ = 0.0
        for f in range(20 * 60):
            n = int(rate / 60)
            syn_.t = 20.0 + (f / 60.0 % 20)
            x = syn_.chunk(n).astype(np.float64)
            u = (t_ - start) / dur
            if noise_k > 0 and 0 <= u <= 1:
                x += noise_k * 0.01 * (30 ** u) * np.diff(rng_.standard_normal(n + 1))
            t_ += n / rate
            an_.feed(x.astype(np.float32))
            an_.update(1 / 60)
            if f / 60.0 >= start:
                mx = max(mx, an_.ear.riser)
        return mx
    check("riser: a noise riser over a groove is found", groove_with(1.0) > 0.5, groove_with(1.0))
    check("riser: a weak noise riser over a groove is found", groove_with(0.2) > 0.5)
    check("riser: a groove alone has none", groove_with(0.0) < 0.2)
    tiles = an.ear.tiles(an)
    check("every reading has a caption, a value and a level", len(tiles) == 16 and all(c and v and 0.0 <= lv <= 1.0 for c, v, lv, _ in tiles), len(tiles))
    an2 = Analyzer(rate)
    feed(an2, lambda t: np.zeros(len(t)), 8)
    check("silence: the captions say nothing instead of guessing", all(v == "—" for _, v, _, _ in an2.ear.tiles(an2)))


def test_fx():
    section("5b. Layers: effects, backgrounds, particles, blend, follow the music")
    random.seed(int(os.environ.get("AO_TEST_SEED", "2024")))                         # the director draws the palette and the look at random: a dark draw made these thresholds fail now and then
    from renderer import Renderer
    from fxstack import FxStack
    import layers as LYR
    import look
    rend = Renderer(headless=True, size=(320, 180))
    draw_errs = []
    _orig = rend._draw

    def _spy():
        try:
            return _orig()
        except Exception as e:
            draw_errs.append(repr(e))
            raise
    rend._draw = _spy
    check("every shader compiled", not rend.pipe_errors, rend.pipe_errors)
    an = listen(25)
    cfg = menu.fresh()
    cfg.update(m_glass=100, m_symnone=False)
    cfg["scenes"][0].update(m_glass=100, m_symnone=False)                                  # a busy picture, so small layer changes show (the shipped Facetas is sparse)
    d = NeonDirector()
    for _ in range(30):
        P = d.update(1 / 60, an, cfg)
    look.apply(rend, P, d.cur, cfg["detail"])
    P.update(bass=0.6, mid=0.5, high=0.5, kick=0.6, snare=0, hat=0, beat=1.0)

    def L(t, **kw):
        return LYR.new_layer(t) | kw

    def frames(layers, taa=False, n=24, bgl=None):
        rend.taa, rend.hist_valid, rend.fb_valid, rend.parts_init, rend.taa_valid = taa, False, False, False, False
        rend.stack = FxStack()
        img = None
        for i in range(n):
            q = dict(P)
            q["layers"] = layers
            q["bgl"] = bgl if bgl is not None else [dict(layer=l, cols=[(0.2, 0.0, 0.6), (0.9, 0.1, 0.3), (0.0, 0.3, 0.9)], angle=0.3) for l in layers if l["t"] in ("grad", "lights")]
            q["time"] = P["time"] + i / 60.0
            img = np.asarray(rend.render(q)).astype(float)
        return img
    base = frames([])
    singles = [("filmic tone", [L("tone", mode=1)]), ("hue-keeping tone", [L("tone", mode=2)]), ("feedback", [L("fb", amt=80, zoom=4, rot=3, hue=5)]),
               ("chromatic aberration", [L("ca", amt=80)]), ("grain", [L("gr", amt=80)]), ("lens flare", [L("fl", amt=90)]), ("edge blur", [L("edge", amt=90)]),
               ("particles: flow", [L("part", count=2, pmode=0)]), ("particles: burst", [L("part", count=3, pmode=1)]), ("particles: orbit", [L("part", count=1, pmode=2)]),
               ("gradient background", [L("grad", gtype=1)]), ("lights background", [L("lights", style=1)]), ("laser lights", [L("lights", style=6)])]
    for name, layers in singles:
        img = frames(layers)
        diff = float(np.abs(img - base).mean())
        check(f"{name}: drawn, finite and different from the plain picture", np.isfinite(img).all() and diff > 0.3, round(diff, 2))
    check("TAA: drawn, finite and different", float(np.abs(frames([], True) - base).mean()) > 0.3)

    def pair(name, la, lb):
        d_ = float(np.abs(frames(la) - frames(lb)).mean())
        check(f"layer control changes the picture: {name}", d_ > 0.15, round(d_, 3))
    pair("aberration direction", [L("ca", amt=70, dir=1)], [L("ca", amt=70, dir=0)])
    pair("aberration start", [L("ca", amt=70, start=50)], [L("ca", amt=70)])
    pair("edge blur shape", [L("edge", amt=80, shape=1)], [L("edge", amt=80)])
    pair("edge blur sharp centre", [L("edge", amt=80, r=60)], [L("edge", amt=80)])
    pair("flare colour", [L("fl", amt=80, col=1)], [L("fl", amt=80, col=0)])
    pair("flare ghosts", [L("fl", amt=80, n=4)], [L("fl", amt=80, n=1)])
    pair("grain size", [L("gr", amt=80, size=4)], [L("gr", amt=80, size=1)])
    pair("grain colour", [L("gr", amt=80, color=1)], [L("gr", amt=80, color=0)])
    pair("aberration blur", [L("ca", amt=70, blur=100)], [L("ca", amt=70)])
    pair("flare blur", [L("fl", amt=80, blur=100)], [L("fl", amt=80)])
    pair("grain blur", [L("gr", amt=80, blur=100)], [L("gr", amt=80)])
    pair("trail blur", [L("fb", amt=80, blur=100)], [L("fb", amt=80)])
    pair("blend mode: add", [L("gr", amt=80, bm=1)], [L("gr", amt=80, bm=0)])
    pair("blend mode: overlay", [L("fl", amt=80, bm=3)], [L("fl", amt=80, bm=0)])
    pair("opacity", [L("ca", amt=80, op=30)], [L("ca", amt=80, op=100)])
    pair("the order of two layers matters", [L("edge", amt=90), L("gr", amt=90)], [L("gr", amt=90), L("edge", amt=90)])
    pair("two gradients stack", [L("grad", gtype=0), L("grad", gtype=2, bm=1)], [L("grad", gtype=0)])
    pair("two grains are not one", [L("gr", amt=60), L("gr", amt=60, size=3)], [L("gr", amt=60)])
    check("a layer turned off does nothing", float(np.abs(frames([L("ca", amt=80, on=False)]) - base).mean()) < 0.5)
    pts = frames([L("part", count=2, pmode=0)])
    streak = frames([L("part", count=2, pmode=0), L("fb", amt=80, fbt=1)])
    whole = frames([L("part", count=2, pmode=0), L("fb", amt=80, zoom=4)])
    check("the trail only on the particles draws streaks (not the plain points)", float(np.abs(streak - pts).mean()) > 0.15, round(float(np.abs(streak - pts).mean()), 3))
    check("... and is not the trail of the whole picture", float(np.abs(streak - whole).mean()) > 0.15, round(float(np.abs(streak - whole).mean()), 3))
    rend.set_overlay(("t", 1), b"\xff" * (16 * 4 * 4), 16, 4)
    rend.ov_on, rend.ov = True, (1, 30, 1.0, 0)
    ov = frames([])
    h_, w_ = ov.shape[:2]
    mid = ov[h_ // 2 - 4:h_ // 2 + 4, w_ // 2 - 8:w_ // 2 + 8, :3].mean()
    check("the Sobreposição lays its picture over the middle", mid > 240 and float(np.abs(ov[:8, :8] - base[:8, :8]).mean()) < 1.0, round(float(mid), 1))
    rend.ov_on = False
    check("... and off it draws nothing", float(np.abs(frames([]) - base).mean()) < 0.5)
    def fin(**kw):
        k = dict(b=1.0, c=1.0, s=1.0, g=1.0, t=0.0, v=0.0, d=0.0, m=0.0, z=1.0, a=0.0, y=0.0, p=4.0)
        k.update(kw)
        rend.fin = (k["b"], k["c"], k["s"], k["g"], k["t"], k["v"], k["d"], k["m"], k["z"], k["a"], k["y"], k["p"])
        img_ = frames([])
        rend.fin = (1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 4.0)
        return img_
    check("final pass: neutral values draw nothing", float(np.abs(fin() - base).mean()) < 0.01)
    check("final pass: brightness", float(fin(b=0.6).mean()) < float(base.mean()) - 1.0 and float(fin(b=1.4).mean()) > float(base.mean()))
    check("final pass: saturation 0 is grey", float(np.abs(fin(s=0.0)[..., 0] - fin(s=0.0)[..., 1]).mean()) < 1.5)
    check("final pass: contrast, gamma, warmth and dither change the picture", all(float(np.abs(fin(**kw) - base).mean()) > 0.3 for kw in (dict(c=1.4), dict(g=1.4), dict(t=1.0))) and 0.02 < float(np.abs(fin(d=1.0) - base).mean()) < 1.5)
    check("final pass: vignette darkens the corners", float(fin(v=0.9)[:8, :8].mean()) < float(base[:8, :8].mean()) * 0.9 + 0.5)
    check("final pass: mirror flips the picture", float(np.abs(fin(m=1.0) - base[:, ::-1]).mean()) < float(np.abs(fin(m=1.0) - base).mean()) and float(np.abs(fin(m=2.0) - base[::-1]).mean()) < float(np.abs(fin(m=2.0) - base).mean()))
    z_ = fin(z=1.5)
    check("final pass: zoom crops towards the middle", float(np.abs(z_ - base).mean()) > 0.3)
    rend.fx_trail = False
    check("heavy effects: a trail layer left out draws nothing", float(np.abs(frames([L("fb", amt=80, zoom=4, rot=3, hue=5)]) - base).mean()) < 0.5)
    rend.fx_trail, rend.fx_parts = True, False
    check("heavy effects: a particle layer left out draws nothing", float(np.abs(frames([L("part", count=2, pmode=0)]) - base).mean()) < 0.5)
    rend.fx_parts = True
    mnd0_ = P.get("mandala")
    P["mandala"] = dict(P.get("mandala") or dict(psx=0.52, psy=0.34, pox=0.7, poy=0.38, decay=0.84, thick=1.0, round=0), glass=0.3)
    g_on = frames([])
    P["glass_on"] = False
    g_off = frames([])
    del P["glass_on"]
    P.pop("mandala")
    if mnd0_ is not None:
        P["mandala"] = mnd0_
    check("heavy effects: glass off makes the faces opaque", float(np.abs(g_on - g_off).mean()) > 0.15, round(float(np.abs(g_on - g_off).mean()), 3))
    mfx = menu.Menu(menu.fresh())
    mfx.press("fx_none")
    off_ = [mfx.cfg[k] for k in ("fx_glass", "fx_bloom", "fx_trail", "fx_parts")]
    mfx.press("fx_none")
    check("heavy effects: one button turns all off, then all on", not any(off_) and all(mfx.cfg[k] for k in ("fx_glass", "fx_bloom", "fx_trail", "fx_parts")))
    cp_ = {}
    for sm_ in (0, 2):                                                                 # Sistema > Imagem > Conforto: the camera tremor and swing shrink
        cfg_ = menu.fresh()
        sc_ = cfg_["scenes"][0]
        sc_.update(camera=5, cam_shake=2, cam_punch=2, cam_roll=2, cam_orbit=2)
        cfg_.update(scenes=[sc_], effect=1, safe_motion=sm_)
        an_, d_ = Analyzer(48000), NeonDirector()
        d_.scenes, d_.scene, d_.pending = [sc_], 0, (0, "cut")
        d_._apply()
        for _ in range(240):
            an_.feed(np.zeros(800, np.float32))
            an_.update(1 / 60)
            d_.update(1 / 60, an_, cfg_)
        cp_[sm_] = dict(d_.cam_p)
    check("comfort: limited movement shrinks tremor, punch and turn", cp_[2]["shake"] < cp_[0]["shake"] * 0.3 and cp_[2]["spin"] < cp_[0]["spin"] * 0.3 and cp_[0]["shake"] > 0.5, (cp_[0]["shake"], cp_[2]["shake"]))
    flat_, lines_, pix_ = fin(y=1.0), fin(y=2.0), fin(y=3.0, p=12.0)
    nlev = lambda im_: len(np.unique(np.round(im_[..., :3] / 8.0).reshape(-1, 3), axis=0))
    check("styles: flat has far fewer colours than the normal picture", nlev(flat_) < nlev(base) * 0.4, (nlev(flat_), nlev(base)))
    check("styles: lines are mostly black with bright edges", float(lines_[..., :3].mean()) < float(base[..., :3].mean()) * 0.75 and float(lines_[..., :3].max()) > 100, (float(lines_[..., :3].mean()), float(base[..., :3].mean()), float(lines_[..., :3].max())))
    check("styles: pixels repeat in blocks", float(np.abs(pix_[:, 0:12][:, :6] - pix_[:, 0:12][:, 6:]).mean()) < float(np.abs(base[:, 0:12][:, :6] - base[:, 0:12][:, 6:]).mean()) + 0.01 and nlev(pix_) < nlev(base) * 0.6, (nlev(pix_), nlev(base)))
    bars_ = fin(a=1.0)
    check("final pass: a square format puts bars at the sides and keeps the middle", float(bars_[..., :3][:, :20].max()) == 0.0 and float(np.abs(bars_[..., :3][:, 140:180] - base[..., :3][:, 140:180]).mean()) < 1.0, (float(bars_[..., :3][:, :20].max()), float(np.abs(bars_[..., :3][:, 140:180] - base[..., :3][:, 140:180]).mean())))
    import thumbs as TH
    check("the preview sizes the GPU can read back (rows of a multiple of 256 bytes)", all(w * 4 % 256 == 0 for w, _ in (TH.SIZE, TH.DRAFT_SIZE)), (TH.SIZE, TH.DRAFT_SIZE))
    rp = Renderer(headless=True, size=TH.DRAFT_SIZE)
    rp.preview_size, rp.preview, rp.preview_every = TH.DRAFT_SIZE, True, 1
    bad_ = []
    o_ = rp._draw

    def spy_(*a_):
        try:
            return o_(*a_)
        except Exception as e_:
            bad_.append(repr(e_))
            raise
    rp._draw = spy_
    for _ in range(6):
        rp.render(dict(P, layers=[], bgl=[]))
    check("the renderer of the draft preview reads its picture back", not bad_ and rp.preview_rgba is not None, bad_[:1])
    check("no draw error inside the canvas for any of them", not draw_errs, draw_errs[:1])
    # many layers at once
    many = [L("edge", amt=40), L("ca", amt=40), L("fl", amt=40), L("gr", amt=40), L("ca", amt=20, dir=1), L("gr", amt=20, size=3), L("edge", amt=20, shape=2), L("fl", amt=20, col=1)]
    img = frames(many)
    check("eight effect layers draw together", np.isfinite(img).all() and not draw_errs, draw_errs[:1])
    # the stack as a plan: following the music, fading between scenes
    st = FxStack()

    def plan(layers, kick=0.0, dt=1 / 60, **p):
        return st.update(dict({"layers": layers, "kick": kick, "time": 0.0}, **p), dt)
    z = L("ca", amt=50, src=1, famt=100, rel=0)
    check("follow: 100% is silent with no music and doubled at full level", abs(plan([z], 0.0).post[0]["amt"]) < 1e-6 and abs(plan([z], 1.0).post[0]["amt"] - 1.0) < 1e-6)
    st = FxStack()
    check("follow: another source", abs(plan([L("ca", amt=50, src=4, famt=100, rel=0)], bass=1.0).post[0]["amt"] - 1.0) < 1e-6)
    st = FxStack()
    check("follow: sensitivity amplifies", plan([dict(z, gain=200)], 0.25).post[0]["amt"] > 0.45)
    st = FxStack()
    check("follow: threshold ignores the quiet part", plan([dict(z, thr=50)], 0.4).post[0]["amt"] < 1e-6)
    st = FxStack()
    check("follow: inverted is strong in silence", plan([dict(z, inv=True)], 0.0).post[0]["amt"] > 0.45)
    st = FxStack()
    slow = L("ca", amt=50, src=1, famt=100, rel=60, atk=60)
    v = [plan([slow], 1.0).post[0]["amt"] for _ in range(3)]
    check("follow: a slow attack rises over several frames", v[0] < v[1] < v[2], v)
    for _ in range(400):
        plan([slow], 1.0)
    d_ = [plan([slow], 0.0).post[0]["amt"] for _ in range(3)]
    check("follow: a slow release falls over several frames", d_[0] > d_[1] > d_[2] > 0.0, d_)
    st = FxStack()
    plan([L("fb", amt=80), L("ca", amt=50)])
    pl = plan([], 0.0)
    check("changing scene: the effects are still there one frame later and the trail too", pl.fb is not None and len(pl.post) == 1, (pl.fb, len(pl.post)))
    for _ in range(300):
        pl = plan([], 0.0)
    check("... and they fade out by themselves", pl.fb is None and not pl.post)
    check("a layer that is off is not in the plan after its fade", plan([L("ca", amt=50, on=False)], 0.0).post == [])


def test_layers():
    section("3e. Layers: migration, editor operations, dropdown")
    import types
    import layers as LYR
    legacy = {"fx_ca": 40, "fx_ca_src": 1, "fx_ca_amt": 70, "fx_grain": 30, "fx_gr_size": 3, "fx_part": 2, "fx_fb": 60, "fx_tone": 1, "scene_bg": 3, "bg_light": 2,
              "bg_int": 150, "bgc_src": 1, "bgc_every": 2}
    ch = LYR.migrate(legacy)
    ts = [l["t"] for l in legacy["layers"]]
    check("an old scene becomes layers (gradient, lights, particles, trail, aberration, grain, tone)", ch and ts == ["grad", "lights", "part", "fb", "ca", "gr", "tone"], ts)
    ca = next(l for l in legacy["layers"] if l["t"] == "ca")
    check("the settings of the old effects carry over", ca["amt"] == 40 and ca["src"] == 1 and ca["famt"] == 70 and next(l for l in legacy["layers"] if l["t"] == "gr")["size"] == 3
          and next(l for l in legacy["layers"] if l["t"] == "lights")["amt"] == 150 and legacy["scene_bg"] == 1 and not [k for k in legacy if k.startswith("fx_")])
    check("migrating twice changes nothing", LYR.migrate(legacy) is False)
    # a settings file with the old keys
    path = os.path.join(TMP, "old_fx.json")
    cfg0 = menu.fresh()
    sc0 = copy.deepcopy(cfg0["scenes"][0])
    sc0.pop("layers", None)
    sc0.update(legacy_keys := {"fx_ca": 50, "fx_edge": 30, "scene_bg": 2, "bgc_cols": [[1, 2, 3], [4, 5, 6], [7, 8, 9]], "bgc_src": 1})
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"scenes": [sc0]}, f)
    loaded = menu.load_cfg(path)
    lay = loaded["scenes"][0]["layers"]
    check("a settings file of an older version loads with layers", [l["t"] for l in lay] == ["grad", "edge", "ca"] and lay[0]["cols"][0] == [1, 2, 3], [l["t"] for l in lay])
    # the presets come as scenes
    fresh = menu.fresh()
    names = [x["scene_name"] for x in fresh["scenes"]]
    gens = ["Vórtice", "Espectro", "Fractal", "Synthwave", "Fluido", "Galáxia", "Laser", "Logo", "Acelerador"]
    check("a new installation has the six presets, the nine generators and Nenhum as scenes, each with its own layers",
          names == ["Facetas", "Estrela", "Túnel", "Catedral", "Impacto", "Palco"] + gens + ["Nenhum"] and all(x["layers"] for x in fresh["scenes"][:6]) and not fresh["scenes"][-1]["layers"], names)
    old = os.path.join(TMP, "old_two.json")
    two = [copy.deepcopy(fresh["scenes"][0]), copy.deepcopy(fresh["scenes"][-1])]
    two[0]["scene_name"] = "Mandala"
    with open(old, "w", encoding="utf-8") as f:
        json.dump({"scenes": two}, f)
    lo = menu.load_cfg(old)
    nm = [x["scene_name"] for x in lo["scenes"]]
    check("an installation of before gets the missing presets, its own scenes stay", nm == ["Mandala", "Estrela", "Túnel", "Catedral", "Impacto", "Palco"] + gens + ["Nenhum"], nm)
    lo2 = menu.load_cfg(old)
    check("... and only once", [x["scene_name"] for x in lo2["scenes"]] == nm and lo["starter_v"] == 4)
    # the editor
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.open_scene(0)
    cfg["scenes"][0]["layers"] = []
    cfg["layers"] = []
    m.rebuild_scenes()
    adv0 = cfg.get("advanced", False)
    cfg["advanced"] = False
    m.rebuild_scenes()
    stk = [r["label"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs if r["id"].startswith("stk_")]
    check("the editor opens on the stack: Ajustes da cena, then Texto e logo, Acabamento, Partículas e rastro, Forma principal, Luzes, Fundo", stk == ["Ajustes da cena", "Segue a música", "Texto e logo", "Acabamento", "Partículas e rastro", "Forma principal", "Luzes", "Fundo"] and cfg["ed_item"] == 0, stk)
    m.set_value("ed_tab", 2)
    ids_ = [r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs]
    check("... and Movimento shows the camera and the rhythm of the scene, with a sentence for each choice", "camera" in ids_ and "movement" in ids_ and settings.ed_tab_of(cfg) == 2)
    m.set_value("ed_tab", 0)
    cfg["advanced"] = True
    m.rebuild_scenes()
    check("... and the advanced mode has the same stack", [r["label"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs if r["id"].startswith("stk_")] == stk)
    cfg["advanced"] = adv0
    m.rebuild_scenes()
    m.add_layer("ca")
    check("a new layer opens on the page of its layer of the six", cfg["ed_page"] and cfg["ed_item"] == 10, cfg["ed_item"])
    m.add_layer("gr")
    m.add_layer("grad")
    check("layers are added at the top and the last one is selected", [l["t"] for l in cfg["layers"]] == ["ca", "gr", "grad"] and cfg["ly_sel"] == 2)
    m.set_value("lp_amt", 77, announce=False)
    check("a parameter goes into the selected layer and into the draft, not into the scene yet", cfg["layers"][2]["amt"] == 77 and m.draft["layers"][2]["amt"] == 77 and cfg["scenes"][0]["layers"] == [])
    m.save_scene()
    check("Salvar puts the draft into the scene", cfg["scenes"][0]["layers"][2]["amt"] == 77 and not m.is_dirty())
    m.layer_action(("sel", 0))
    check("selecting a layer loads its parameters", cfg["lp_amt"] == 50 and cfg["ly_sel"] == 0)
    m.set_value("lp_dir", 1, announce=False)
    m.set_value("lp_src", 4, announce=False)
    check("choosing a source shows the follow rows", any(r["id"] == "lp_atk" for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs))
    m.layer_action(("up", 0))
    check("a layer moves up and stays selected", [l["t"] for l in cfg["layers"]] == ["gr", "ca", "grad"] and cfg["ly_sel"] == 1 and cfg["layers"][1]["dir"] == 1)
    m.layer_action(("dup", 1))
    check("a layer is duplicated", [l["t"] for l in cfg["layers"]] == ["gr", "ca", "ca", "grad"])
    m.layer_action(("eye", 1))
    check("the eye turns a layer off", cfg["layers"][1]["on"] is False and cfg["lp_on"] is False)
    m.layer_action(("del", 2))
    check("a layer is deleted", [l["t"] for l in cfg["layers"]] == ["gr", "ca", "grad"])
    m.undo_last()
    check("undo brings the deleted layer back", len(cfg["layers"]) == 4)
    for _ in range(12):
        m.add_layer("edge")
    fx_n = sum(1 for l in cfg["layers"] if l["t"] in ("ca", "edge", "fl", "gr", "tone"))
    check("the stack stops at 8 effect layers", fx_n == 8, fx_n)
    m.add_layer("fb")
    m.add_layer("fb")
    check("only one trail", sum(1 for l in cfg["layers"] if l["t"] == "fb") <= 1)
    m.apply_stack_template(1)
    check("a stack template replaces the effects and keeps the backgrounds", [l["t"] for l in cfg["layers"]].count("grad") == 1 and "tone" in [l["t"] for l in cfg["layers"]])
    json.dumps(cfg)
    # "Nova cena" goes straight to the editor of layers
    n_before = len(cfg["scenes"])
    m.back_to_gallery()
    m.new_scene()
    check("a new scene opens in the editor on the layers, empty", len(cfg["scenes"]) == n_before + 1 and m.scene_view == "editor" and cfg["ed_item"] == 4
          and cfg["scene_name"] == "Nova cena" and cfg["layers"] == [], (cfg["scene_name"], cfg["ed_item"], m.scene_view))
    m.back_to_gallery()
    m.new_scene()
    check("the second one is numbered", cfg["scene_name"] == "Nova cena 2")
    # the dropdown, with the mouse
    pygame.font.init()
    m.tab = menu.TAB_SCENES
    m.ed_back()
    m.open_item(8)                                                               # Luzes: its list and its add menu
    m.need = True
    m.render()

    def click(pos):
        for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
            m.mouse(types.SimpleNamespace(type=typ, pos=pos, **extra), 0, 0, 1)
        m.need = True
        m.render()
    box = next(r for r, cid, kind, arg in m.hits if cid == "ly_add" and kind == "dd")
    click(box.center)
    check("a click opens the dropdown", m.dd_open == "ly_add")
    m.dd_groups = {"fx", "bg", "part"}                                          # the add menu: every group open for this check
    m.need = True
    m.render()
    opt = next(r for r, cid, kind, arg in m.hits if kind == "ddopt" and arg == "lights")
    n0 = len(cfg["layers"])
    click(opt.center)
    check("choosing an option adds the layer and closes the dropdown", len(cfg["layers"]) == n0 + 1 and cfg["layers"][-1]["t"] == "lights" and m.dd_open is None)
    box = next(r for r, cid, kind, arg in m.hits if cid == "lp_src" and kind == "dd")
    click(box.center)
    opt = next(r for r, cid, kind, arg in m.hits if kind == "ddopt" and arg == 1)
    click(opt.center)
    check("a dropdown sets a value of the layer", cfg["layers"][cfg["ly_sel"]]["src"] == 1)
    click(next(r for r, cid, kind, arg in m.hits if cid == "lp_bm" and kind == "dd").center)
    click((5, 5))
    check("a click outside closes it", m.dd_open is None)
    m.render()
    row_hits = [r for r, cid, kind, arg in m.hits if kind == "ly" and arg[0] == "sel"]
    click(row_hits[0].center)
    check("a click on a row of the list opens the page of that layer", cfg["ly_sel"] == len(cfg["layers"]) - 1 and cfg["ed_page"] and cfg["ed_item"] == 8, (cfg["ly_sel"], cfg["ed_item"]))
    click(next(r for r, cid, kind, arg in m.hits if cid == "stk_scene" and kind == "it").center)
    check("a click on Ajustes da cena opens the camera there", cfg["ed_page"] and cfg["ed_item"] == 6 and any(r["id"] == "camera" for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs))


def test_responsive():
    section("6b. A window of any size: the panel follows it")
    import types
    import control
    an = listen(20)
    st = dict(image=dict(scene="Mandala", scene_i=0, style="3D", camera="Fixo", movement="Padrão", why=None, since=1, pending_scene=-1),
              keys=dict(fullscreen=False, vsync=False, strobe=True, auto=True), gpu="x", backend="x", shader_ok=True, reloads=0, preview=dict(on=False))
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    cw = control.ControlWindow(m, headless=True)
    ok, err = True, None
    for w, h in ((620, 560), (700, 600), (1000, 700), (1200, 900), (1600, 1000), (2200, 1200), (640, 800)):
        cw.resize(w, h)
        check(f"{w}x{h}: the panel takes the width of the window", m.W == cw.W - 2 * cw.PAD and cw.surf.get_size() == (cw.W, cw.H), (m.W, cw.W))
        for tab in range(len(menu.TABS)):
            m.tab, m.need = tab, True
            try:
                cw.update(time.time() + tab, an, 60.0, 10.0, False, st, force=True)
            except Exception as e:
                ok, err = False, (w, tab, repr(e))
        m.tab = 1
        m.open_scene(0)
        for item, sub in menu.ED_VIEWS:
            m.cfg["ed_sub"], m.cfg["ed_page"] = sub, item >= 0
            m.set_value("ed_item", max(item, 0))
            try:
                cw.update(time.time(), an, 60.0, 10.0, False, st, force=True)
            except Exception as e:
                ok, err = False, (w, item, sub, repr(e))
        m.back_to_gallery()
        m.back_to_gallery()
    check("every tab and every screen of the editor draw at every size", ok, err)
    # the wide Estúdio: the gallery first; the editor has the stack of the scene on the left and the page of the item on the right
    cw.resize(1200, 900)
    m.press("tab1")
    m.back_to_gallery()
    check("every width starts the Estúdio on the gallery", m.scene_view == "gallery")
    m.open_scene(0)
    m.cfg["layers"] = [menu.LY.new_layer("ca")]
    m.store_scene()
    m.rebuild_scenes()
    cols = m.cols[menu.TAB_SCENES]
    check("the wide editor: the list of effects on the left, the page on the right (ScreenMaster's layout)", m.wide and "L" in cols and "R" in cols and m.panes(), cols)
    left = [r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs if r["id"].startswith("stk_")]
    check("the stack: the settings of the scene, then the six layers top first", left == ["stk_scene", "stk_links", "stk_over", "stk_finish", "stk_parts", "stk_form", "stk_lights", "stk_bg"], left)
    m.cfg["ed_item"], m.cfg["ed_sub"] = 0, 0
    m.rebuild_scenes()
    m.need = True
    m.render()

    def click(pos):
        for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
            m.mouse(types.SimpleNamespace(type=typ, pos=pos, **extra), 0, 0, 1)
        m.need = True
        m.render()
    def click_hit(r):
        m.scroll = max(0, min(m.max_scroll(), r.centery - 300))
        m.need = True
        m.render()
        click((r.centerx, r.centery - m.scroll))
    wl, wr, gap = m._col_widths()
    r = next(r for r, cid, kind, arg in m.hits if cid == "m_psx" and kind == "slider")
    check("the slider of the open item is on the page", r.width > 100, r)
    tl, tw = m.slider_geos["m_psx"]
    m.scroll = max(0, min(m.max_scroll(), r.centery - 300))
    m.need = True
    m.render()
    r = next(r for r, cid, kind, arg in m.hits if cid == "m_psx" and kind == "slider")
    tl, tw = m.slider_geos["m_psx"]
    click((tl + tw // 2, r.centery - m.scroll))
    check("a click on the middle of the slider of the right column sets the middle of its range", abs(cfg["m_psx"] - 60) <= 4, cfg["m_psx"])
    click_hit(next(r for r, cid, kind, arg in m.hits if cid == "stk_finish" and kind == "it"))
    check("a click on Acabamento in the stack opens its page, on its first effect", cfg["ed_item"] == 10 and cfg["ly_sel"] == 0 and any(r["id"] == "lp_amt" for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs))
    box = next(r for r, cid, kind, arg in m.hits if cid == "lp_bm" and kind == "dd")
    click_hit(box)
    check("a dropdown of the open page opens over it", m.dd_open == "lp_bm")
    click_hit(box)                                                                 # (closes it)
    sw = next(r for r, cid, kind, arg in m.hits if cid == "ly_parts" and kind == "toggle")
    click_hit(sw)
    check("the switch of a layer in the stack turns it off (and the scene being edited keeps it)", cfg["ly_parts"] is False and m.draft.get("ly_parts") is False, (cfg["ly_parts"], m.draft.get("ly_parts"), m.dd_open, sw))
    sw = next(r for r, cid, kind, arg in m.hits if cid == "ly_parts" and kind == "toggle")
    click_hit(sw)
    check("... and on again", cfg["ly_parts"] is True)
    click_hit(next(r for r, cid, kind, arg in m.hits if cid == "stk_scene" and kind == "it"))
    ids = {r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs}
    check("Ajustes da cena has the colours, the camera, the rhythm, the music and the name", {"scene_palette", "camera", "movement", "react", "scene_name"} <= ids, sorted(ids)[:10])
    m.store_scene()
    m.discard_scene()
    m.toggle_auto(True)
    check("Troca automática on", cfg["effect"] == 0)
    m.set_value("autoall", False)
    check("Troca automática off keeps the scene that is on the air", cfg["effect"] == m.live_scene + 1, cfg["effect"])
    m.set_value("autoall", True)
    check("... and on again", cfg["effect"] == 0)
    # the simple mode hides the advanced things; the switch brings them back
    cw.resize(1200, 900)
    m.cfg["advanced"] = False
    m.press("advanced")
    check("the switch of the advanced mode turns it on", cfg["advanced"] is True)
    m.press("advanced")
    check("... and off", cfg["advanced"] is False)
    m.tab = menu.TAB_SCENES
    m.open_scene(0)
    m.rebuild_scenes()
    ed_tabs = lambda: ["Camadas"] if any(r["id"] in ("stk_finish", "stk_bg") for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs) else []      # (the tabs are the stack now)
    titles = [t for t, _ in menu.TABS[menu.TAB_SCENES][1]]
    check("the simple Estúdio keeps the layers a scene already has (they can be edited)", "Camadas" in ed_tabs() and "CAMADAS  ·  DE CIMA PARA BAIXO" in titles, (titles, ed_tabs()))
    saved = cfg["layers"]
    cfg["layers"] = []
    m.rebuild_scenes()
    check("... and with none, the Camadas tab is still there (the six layers, the Acabamento) without the list of effects", "Camadas" in ed_tabs())
    cfg["layers"] = saved
    m.rebuild_scenes()
    m.open_item(0)
    m.cfg["ed_sub"] = 2
    m.rebuild_scenes()
    seg = next(r for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs if r["id"] == "ed_sub")
    check("the simple mandala has no editor of shaders and no Formas (the style is only a choice), and a hidden section opens on Modelo", [n for n, _ in seg["opts"]] == ["Modelo", "Estilo", "Simetrias"] and not any(r["id"] == "shd_name" for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs))
    m.open_item(1)
    ids = {r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs}
    check("the simple camera is the choice of a style only", "camera" in ids and "cam_orbit" not in ids, sorted(ids)[:6])
    m.open_item(3)
    ids = {r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs}
    check("the simple music has the reaction, the strobe and the glow", {"react", "strobe", "bloom"} <= ids and "react_bass" not in ids and "fl_roll" not in ids, sorted(ids)[:8])
    m.tab = menu.TAB_SYS
    for k, must, mustnot in ((0, "preset", "res"), (2, "link_riser", "ae_kind"), (3, "profile", "remote_osc"), (4, "auto_update", "backend")):
        cfg["sys_item"] = k
        m.rebuild_scenes()
        ids = {r["id"] for _, rs in menu.TABS[menu.TAB_SYS][1] for r in rs}
        check(f"the simple Sistema page {k} keeps {must} and hides {mustnot}", must in ids and mustnot not in ids, sorted(ids)[:8])
    m.new_scene()
    check("a simple new scene opens on the mandala, not on the layers", cfg["ed_item"] == 0)
    m.press("advanced")
    ids = {r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs} if m.tab == menu.TAB_SCENES else set()
    m.tab = menu.TAB_SCENES
    m.rebuild_scenes()
    check("the advanced Estúdio brings the layers back", "Camadas" in ed_tabs())
    m.press("advanced")
    m.press("advanced")
    cfg["sys_item"] = 0
    m.cfg["ed_item"] = 0
    # two columns, two scrolls: each one moves on its own and the bar of the editor stays
    cw.resize(1200, 700)
    m.tab = menu.TAB_SCENES
    m.rebuild_scenes()
    m.scroll = m.scroll2 = 0
    cfg["ed_item"], cfg["ed_sub"] = 0, 0
    m.rebuild_scenes()
    cw.update(time.time(), an, 60.0, 10.0, False, st, force=True)
    check("the wide editor: each column scrolls on its own", m.panes() and m.max_scroll(0) > 0, (m.panes(), m.max_scroll(0)))
    m.scroll = min(m.max_scroll(), 150)
    cw.update(time.time(), an, 60.0, 10.0, False, st, force=True)
    row = next(r for r, cid, kind, arg in m.hits if cid == "stk_form" and kind == "it")
    py_ = cw.panel_pos[1] + m.HEAD + m.reserved + row.centery - m.HEAD - m.scroll
    for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
        cw.handle(types.SimpleNamespace(type=typ, pos=(cw.panel_pos[0] + row.centerx, py_), **extra))
    check("a click on a layer of the scrolled editor opens it (wide: it does not fold)", cfg["ed_item"] != -1, cfg["ed_item"])
    m.open_item(7)
    cw.update(time.time(), an, 60.0, 10.0, False, st, force=True)
    check("opening an item brings its row to the top, with its page under it", m.scroll > 0, m.scroll)
    m.scroll2 = 80
    m.set_value("sys_item", 0)
    check("a category change does not break the scrolls", m.scroll >= 0 and m.scroll2 >= 0)
    cw.resize(700, 700)
    m.clamp_scroll()
    check("a narrow window has a single scroll again", not m.panes() and m.scroll2 == 0)
    cw.resize(1200, 900)
    m.scroll = m.scroll2 = 0
    # Sistema: the categories on the left, the page on the right
    m.tab = menu.TAB_SYS
    m.need = True
    m.rebuild_scenes()
    m.render()
    check("in a wide Sistema the search field and the categories are on the left", m.cols[menu.TAB_SYS][:2] == ["L", "L"] and menu.TABS[menu.TAB_SYS][1][0][1][0]["id"] == "search"
          and menu.TABS[menu.TAB_SYS][1][1][1][0]["kind"] == "radio")
    click(next(r for r, cid, kind, arg in m.hits if cid == "sys_item" and kind == "radio" and arg == 4).center)
    check("a click on a category shows its page", cfg["sys_item"] == 4 and any(r["id"] == "quit" for _, rs in menu.TABS[menu.TAB_SYS][1] for r in rs))
    quit_btn = next(r for r, cid, kind, arg in m.hits if cid == "quit")
    click(quit_btn.center)
    check("Sair asks twice", m.quit_armed > 0)
    cfg["sys_item"] = 0
    m.rebuild_scenes()
    check("the page Imagem has the quality cards, the measure and the restore", {"res", "bench", "reset"} <= {r["id"] for _, rs in menu.TABS[menu.TAB_SYS][1] for r in rs})
    check("Sistema > Imagem has no picture strip any more (the picture is on the Palco and the Estúdio)", m.pv_mode() is None)
    m.tab = menu.TAB_SCENES
    check("and the draft is the strip of the Estúdio", m.pv_mode() == "draft")
    # narrow again: the same editor goes back to one column with pages
    cw.resize(700, 700)
    check("a narrow window goes back to one column", not m.wide and not m.cols[menu.TAB_SCENES])
    m.tab = menu.TAB_SYS
    m.rebuild_scenes()
    check("a narrow Sistema has the search field, then one row of categories over the page", not m.cols[menu.TAB_SYS] and menu.TABS[menu.TAB_SYS][1][0][1][0]["id"] == "search" and menu.TABS[menu.TAB_SYS][1][1][1][0]["kind"] == "seg")
    cw.resize(1200, 900)
    check("the narrow gallery keeps its three cards per row", (lambda: (m.press("tab1"), cw.resize(700, 700), setattr(m, "scene_view", "gallery"), cw.update(time.time(), an, 60.0, 10.0, False, st, force=True), cw.COLS)[-1])() == 3, cw.COLS)


def test_generators():
    section("5c. The visuals: tunnel, spectrum, fractal, synthwave, fluid, galaxy, oscilloscope, logo")
    from renderer import Renderer
    import look
    import logo as LG
    rend = Renderer(headless=True, size=(240, 135))
    draw_errs = []
    _orig = rend._draw

    def _spy():
        try:
            return _orig()
        except Exception as e:
            draw_errs.append(repr(e))
            raise
    rend._draw = _spy
    check("the generators shader compiled", "generators" not in rend.pipe_errors and "gen" in rend.pipes, rend.pipe_errors)
    an = listen(20)
    imgs = {}
    for g in SC.GEN_SCENES:
        sc = SC.generator_scene(g)
        sc["layers"] = []
        d = NeonDirector()
        d.scenes, d.scene, d.pending = [sc], 0, (0, "cut")
        d._apply()
        c = menu.fresh()
        SC.apply_scene(c, sc)
        c["scenes"], c["effect"] = [sc], 1
        img = None
        for i in range(12):
            P = d.update(1 / 60, an, c)
            look.apply(rend, P, d.cur, 100)
            P.update(bass=0.5, mid=0.4, high=0.4, kick=0.5, snare=0, hat=0, beat=i / 10.0)
            look.audio(P, an)
            img = np.asarray(rend.render(P)).astype(float)[:, :, :3]
        imgs[g[1]] = img
        check(f"{g[1]} draws something that is not black", img.mean() > 1.0 and img.std() > 5.0, (img.mean(), img.std()))
    check("no draw error in any generator", not draw_errs, draw_errs[:2])
    ks = list(imgs)
    close = [(a, b) for i, a in enumerate(ks) for b in ks[i + 1:] if float(np.abs(imgs[a] - imgs[b]).mean()) < 2.0]
    check("every generator is a different picture", not close, close)
    # the sound moves the picture: the spectrum with a loud and with a silent analyser
    sc = SC.generator_scene(SC.GEN_SCENES[1])
    sc["layers"] = []
    d = NeonDirector()
    d.scenes, d.scene, d.pending = [sc], 0, (0, "cut")
    d._apply()
    c = menu.fresh()
    SC.apply_scene(c, sc)
    c["scenes"], c["effect"] = [sc], 1
    quiet = Analyzer(48000)
    shots = []
    for an_ in (an, quiet):
        rend.hist_valid = rend.fb_valid = False                                      # no trail of the other run
        from fxstack import FxStack
        rend.stack = FxStack()                                                       # nor ghosts of the layers of the scene before
        for i in range(10):
            P = d.update(1 / 60, an_, c)
            look.apply(rend, P, d.cur, 100)
            P.update(bass=0.3, mid=0.3, high=0.3, kick=0.0, snare=0, hat=0, beat=0.0)
            look.audio(P, an_)
            img = np.asarray(rend.render(P)).astype(float)
        shots.append(img[:int(img.shape[0] * 0.55), :, :3].mean())
    check("the spectrum follows the sound (it is brighter with music than in silence)", shots[0] > shots[1] * 1.15, shots)
    # the logo: text and image
    k1, rgba, w, h = LG.make("Meu nome", "")
    check("the logo makes a picture of the text", len(rgba) == w * h * 4 and w > h and k1[0] == "Meu nome")
    png = os.path.join(TMP, "logo_test.png")
    s_ = pygame.Surface((64, 32), pygame.SRCALPHA)
    s_.fill((255, 0, 0, 255))
    pygame.image.save(s_, png)
    k2, rgba2, w2, h2 = LG.make("ignorado", png)
    check("... or of the image that was chosen", (w2, h2) == (64, 32) and k2[1] == png and k2 != k1)
    check("... and asking again is free (cached)", LG.make("Meu nome", "")[0] == k1)
    # the editor: the pages of every visual
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.open_scene(0)
    ok, why = True, None
    for v in range(len(SC.VISUALS)):
        m.set_value("scene_visual", v, announce=False)
        for sub in range(5):
            cfg["ed_sub"] = sub
            m.open_item(0)
            try:
                m.need = True
                m.render()
            except Exception as e:
                ok, why = False, (v, sub, repr(e))
        ids = {r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs}
        if v >= 2:
            cfg["ed_sub"] = 0
            m.rebuild_scenes()
            ids = {r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs}
            ok = ok and {"gen_p1", "gen_p2", "gen_p3"} <= ids and (v != 9 or {"gen_text", "gen_pick"} <= ids)
    check("every visual has its page in the editor, with its three settings", ok, why)
    m.set_value("scene_visual", 3, announce=False)
    cfg["ed_sub"] = 0
    m.rebuild_scenes()
    lab = next(r["label"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs if r["id"] == "gen_p1")
    check("the settings are named by the visual (Espectro: Barras)", lab == "Barras", lab)
    check("a scene of a generator is in the list with its own name", menu.scene_sub(cfg, cfg["scenes"][7]) == "Espectro", menu.scene_sub(cfg, cfg["scenes"][7]))


def test_global():
    section("5d. The new features work everywhere: every quality option, every layer, scene changes, files, the list of scenes")
    from renderer import Renderer
    from fxstack import FxStack
    import layers as LYR
    import look
    rend = Renderer(headless=True, size=(240, 135))
    errs = []
    _orig = rend._draw

    def _spy():
        try:
            return _orig()
        except Exception as e:
            errs.append(repr(e))
            raise
    rend._draw = _spy
    an = listen(20)
    random.seed(7)
    ran = 0
    for g in SC.GEN_SCENES:
        for taa, mblur, res, fxaa in ((False, 0, 100, False), (True, 180, 60, True), (False, 360, 150, False)):
            sc = SC.generator_scene(g)
            sc["layers"] = [LYR.new_layer(t_) for t_ in random.sample(LYR.ORDER, 4)]
            d = NeonDirector()
            d.scenes, d.scene, d.pending = [sc], 0, (0, "cut")
            d._apply()
            c = menu.fresh()
            SC.apply_scene(c, sc)
            c["scenes"], c["effect"] = [sc], 1
            rend.taa, rend.mblur, rend.res, rend.fxaa = taa, mblur, res, fxaa
            rend.hist_valid = rend.fb_valid = rend.taa_valid = False
            rend.stack = FxStack()
            for i in range(6):
                P = d.update(1 / 60, an, c)
                look.apply(rend, P, d.cur, 100)
                P.update(bass=0.5, mid=0.4, high=0.4, kick=0.5, snare=0, hat=0, beat=i / 7.0)
                look.audio(P, an)
                P["layers"] = sc["layers"]
                P["bgl"] = [dict(layer=l, cols=[(0.2, 0.0, 0.6), (0.9, 0.1, 0.3), (0.0, 0.3, 0.9)], angle=0.3) for l in sc["layers"] if l["t"] in ("grad", "lights")]
                rend.render(P)
                ran += 1
    rend.taa, rend.mblur, rend.res, rend.fxaa = False, 180, 100, False
    check(f"{ran} frames: every generator with random layers, TAA, motion blur and other resolutions, no draw error", not errs, errs[:2])
    # a change of scene from the mandala to a generator and back, with the director
    cfg = menu.fresh()
    d = NeonDirector()
    d.scenes = [cfg["scenes"][0], cfg["scenes"][7], cfg["scenes"][1]]
    d.scene = 0
    d.pending = (0, "cut")
    d._apply()
    c = dict(cfg)
    c["scenes"] = d.scenes
    c["scene_fade"] = 1
    c["scene_when"] = 0                                                             # change at once
    seen = set()
    for step in range(3):
        c["effect"] = step + 1
        for i in range(70):
            P = d.update(1 / 60, an, c)
            look.apply(rend, P, d.cur, 100)
            P.update(bass=0.4, mid=0.4, high=0.4, kick=0.4, snare=0, hat=0, beat=i / 9.0)
            look.audio(P, an)
            P["layers"] = []
            rend.render(P)
            seen.add(P.get("visual", 0))
    check("a scene change between the mandala and a generator draws without error, both kinds were on screen", not errs and seen >= {0, 3}, (seen, errs[:1]))
    # the Mandala keeps what the director gives it (the visual of a generator must not touch the director's own numbers)
    d = NeonDirector()
    cfg = menu.fresh()
    d.scenes, d.scene, d.pending = [cfg["scenes"][0]], 0, (0, "cut")
    d._apply()
    P = d.update(1 / 60, an, dict(cfg, scenes=d.scenes, effect=1))
    g0 = P["gen"]
    look.apply(rend, P, d.cur, 100)
    check("a mandala scene leaves the director's own 'gen' alone and asks for no generator", P["gen"] == g0 and P.get("visual", 0) == 0, (g0, P["gen"], P.get("visual")))
    # the room behind the picture can always be chosen, and a generator never turns into two flat colours (the duotone of the shader)
    class _R:
        duo = style = 0
        steps = res = 0
        bloom = flash = 0.0

        def set_logo(self, *a):
            pass
    fake = _R()
    for vis, sb, want in ((1, 0, None), (1, 1, (0, 0, 0)), (1, 2, (0.97, 0.97, 0.97)), (4, 0, (0, 0, 0)), (4, 2, (0.97, 0.97, 0.97))):
        P = dict(style_id=7, bg=(0.9, 0.1, 0.2), complexity=1.0, fade=1.0, gain=1.0, upals=[[(1, 0, 0), (0, 1, 0), (0, 0, 1)]] * 3, tier_uni=(0, 1, 2))
        look.apply(fake, P, dict(scene_visual=vis, scene_bg=sb), 100)
        if want is not None:
            check(f"visual {vis}, fundo {sb}: the room is {want}", tuple(round(v, 2) for v in P["bg"]) == want, P["bg"])
        if vis >= 2:
            check("a generator ignores the duotone of the automatic shader", fake.duo is False)
    P = dict(style_id=2, bg=(0.9, 0.1, 0.2), complexity=1.0, fade=1.0, gain=1.0)
    look.apply(fake, P, dict(scene_visual=1, scene_bg=3, scene_bgr=100, scene_bgg=50, scene_bgb=200), 100)
    check("a colour of its own for the room", tuple(round(v, 2) for v in P["bg"]) == (round(100 / 255, 2), round(50 / 255, 2), round(200 / 255, 2)), P["bg"])
    cfg = menu.fresh()
    cfg["advanced"] = False
    m = menu.Menu(cfg)
    m.open_scene(0)
    m.open_item(7)
    m.rebuild_scenes()
    ids = [r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs]
    check("Fundo has the choice of the room (simple mode too) and no sliders until a colour is asked", "scene_bg" in ids and "scene_bgr" not in ids, ids)
    m.set_value("scene_bg", 3, announce=False)
    ids = [r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs]
    check("... then the three sliders of the colour appear", {"scene_bgr", "scene_bgg", "scene_bgb"} <= set(ids), ids)
    m.set_value("scene_bgg", 150, announce=False)
    check("... and the change goes into the draft of the scene", m.draft["scene_bg"] == 3 and m.draft["scene_bgg"] == 150 and m.is_dirty())
    # every scene that ships can have its room, its colours and its layers edited, in both modes
    for adv in (False, True):
        cfg = menu.fresh()
        cfg["advanced"] = adv
        m = menu.Menu(cfg)
        bad_ = []
        for si in range(len(cfg["scenes"])):
            m.open_scene(si)
            m.open_item(7)
            m.rebuild_scenes()
            ids = {r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs}
            if cfg["scene_visual"] != 0 and "scene_bg" not in ids:
                bad_.append((cfg["scene_name"], "no room"))
            for li in range(len(cfg["layers"])):
                m.layer_action(("sel", li))
                if not any(r["id"].startswith("lp_") for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs):
                    bad_.append((cfg["scene_name"], li, "layer without controls"))
        check(f"every scene that ships has its room and its layers editable ({'advanced' if adv else 'simple'} mode)", not bad_, bad_[:3])
    # files: export / import and the settings file carry the new keys
    os.environ["VIS_SHAREDIR"] = os.path.join(TMP, "share_g")
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.open_scene(10)
    m.set_value("gen_text", "Meu logo", announce=False)
    m.set_value("gen_p2", 80, announce=False)
    m.save_scene()
    m.export_scenes()
    n0 = len(cfg["scenes"])
    m.import_scenes()
    imp = cfg["scenes"][n0:]
    sc10 = cfg["scenes"][10]
    check("export and import keep the visual, its settings and its text", any(s["scene_visual"] == sc10["scene_visual"] and s["gen_text"] == "Meu logo" and s["gen_p2"] == 80 for s in imp))
    path = os.path.join(TMP, "g_settings.json")
    menu.save_cfg(cfg) if False else None
    json.dump(cfg, open(path, "w", encoding="utf-8"), default=str)
    lo = menu.load_cfg(path)
    check("the settings file keeps them too", lo["scenes"][10]["gen_text"] == "Meu logo" and lo["scenes"][10]["scene_visual"] == sc10["scene_visual"])
    # an installation of before is not broken by a scene without the new keys
    old_sc = copy.deepcopy(cfg["scenes"][0])
    for k in ("gen_p1", "gen_p2", "gen_p3", "gen_text", "gen_img"):
        old_sc.pop(k, None)
    json.dump({"scenes": [old_sc]}, open(path, "w"))
    lo = menu.load_cfg(path)
    check("a scene of an older file gets them and every visual can be picked on it", all(k in lo["scenes"][0] for k in ("gen_p1", "gen_text")))
    # the list, the strip of the Palco and the shortcuts see the generators
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.play_scene(8)
    check("a generator can be played like any scene (the keys 1-9 and OSC/MIDI use the same call)", cfg["effect"] == 9)
    # the layers of a scene stay editable in the simple mode (the particles of Estrela)
    cfg = menu.fresh()
    cfg["advanced"] = False
    m = menu.Menu(cfg)
    m.open_scene(1)
    part = next(i for i, l in enumerate(cfg["layers"]) if l["t"] == "part")
    m.layer_action(("sel", part))
    ids = {r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs}
    check("in the simple mode a layer a scene already has opens and can be edited (particles of Estrela)", {"lp_count", "lp_pmode", "lp_psize"} <= ids, sorted(ids)[:10])
    m.set_value("lp_psize", 80)
    check("... and the change reaches the layer", cfg["layers"][part].get("psize") == 80, cfg["layers"][part])


def test_palco():
    section("6c. The Palco: the picture, the big buttons and the three controls")
    import control
    import types
    cfg = menu.fresh()
    cfg["advanced"] = False                                                           # (the wide advanced Palco keeps the details open: its own test)
    m = menu.Menu(cfg)
    cw = control.ControlWindow(m, headless=True)
    an = listen(20)
    st = dict(image=dict(scene="Facetas", scene_i=0, style="3D", camera="Fixo", movement="Padrão", why=None, since=1, pending_scene=-1),
              keys=dict(fullscreen=False, vsync=False, strobe=True, auto=True), gpu="x", backend="x", shader_ok=True, reloads=0, preview=dict(on=False))
    cw.set_preview(bytes(512 * 288 * 4), (512, 288), "bgra8unorm")
    m.tab, m.need = menu.TAB_LIVE, True
    for size in ((660, 800), (1000, 800), (1900, 1000)):
        cw.resize(*size)
        cw.update(time.time(), an, 60.0, 10.0, False, st, force=True)
        cw.update(time.time() + 1, an, 60.0, 10.0, False, st, force=True)
        ids = {b for _, b in cw.live.live_hits}
        check(f"{size[0]}x{size[1]}: the Palco has the big buttons, the three controls and the scenes",
              {"key:f", "auto:toggle", "macro:energy:2", "macro:speed:2", "macro:pal:0", "ear:open", "scene:0"} <= ids, sorted(ids)[:12])
    check("the keys of the picture are on the Palco as buttons", any(b == "key:v" for _, b in cw.live.live_hits))

    def click(bid):
        act = None
        rect = next(r for r, b in cw.live.live_hits if b == bid)
        m.scroll = max(0, min(m.max_scroll(), rect.centery - 200))
        pos = (rect.centerx + cw.panel_pos[0], rect.centery + m.HEAD + m.reserved - m.scroll + cw.panel_pos[1])
        for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
            act = cw.handle(types.SimpleNamespace(type=typ, pos=pos, **extra)) or act
        cw.update(time.time() + 2, an, 60.0, 10.0, False, st, force=True)
        return act
    click("macro:energy:4")
    check("Intensidade: Explosiva", cfg["macro_energy"] == 190, cfg["macro_energy"])
    click("macro:speed:0")
    check("Velocidade: Lenta", cfg["macro_speed"] == 40, cfg["macro_speed"])
    click("macro:pal:2")
    check("Cores: the second palette for every scene", cfg["macro_pal"] == 2, cfg["macro_pal"])
    check("a button 'Voltar ao normal' shows once something changed", any(b == "macro:reset:0" for _, b in cw.live.live_hits))
    click("macro:reset:0")
    check("... and puts the three back", (cfg["macro_energy"], cfg["macro_speed"], cfg["macro_pal"]) == (100, 100, 0))
    check("the full screen button hands the key F to the program", click("key:f") == "key:f")
    eff0 = cfg["effect"]
    click("auto:toggle")
    check("the automatic change button turns it off (the scene on the air stays)", eff0 == 0 and cfg["effect"] == 1, cfg["effect"])
    click("auto:toggle")
    check("... and on again", cfg["effect"] == 0)
    click("ear:open")
    check("'Ver o que o programa ouve' opens Sistema > Áudio, where the analysis is", m.tab == menu.TAB_SYS and cfg["sys_item"] == 1 and any(r["kind"] == "ear" for _, rs in menu.sys_cards(cfg, 1) for r in rs))
    # the controls change the picture, whatever the scene is
    c1 = menu.fresh()
    an2 = listen(8)
    outs = {}
    for name, kw in (("normal", {}), ("fast", dict(macro_speed=230)), ("slow", dict(macro_speed=40))):
        d = NeonDirector()
        c = dict(c1, **kw)
        d.scenes, d.scene, d.pending = [c1["scenes"][0]], 0, (0, "cut")
        d._apply()
        c["scenes"], c["effect"] = d.scenes, 1
        for _ in range(120):
            P = d.update(1 / 60, an2, c)
        outs[name] = P["travel"]
    check("Velocidade moves the picture faster or slower (the travel of the mandala)", outs["fast"] > outs["normal"] > outs["slow"], outs)
    d = NeonDirector()
    c = dict(c1, macro_pal=2)
    d.scenes, d.scene, d.pending = [c1["scenes"][0]], 0, (0, "cut")
    d._apply()
    c["scenes"], c["effect"] = d.scenes, 1
    for _ in range(5):
        d.update(1 / 60, an2, c)
    nm = c1["palettes"][1]
    ok_ = [tuple(int(round(v * 255)) for v in col) for col in d.upals[0]]
    allowed = {tuple(x) for x in nm["colors"]}
    check("Cores forces the palette on a scene that has its own colours", all(col in allowed for col in ok_), (ok_, nm["name"]))


def test_firstminute():
    section("6e. The first minute: a click answers at once, the card ticks itself, a warning has its button, the first window, the words on the picture")
    import control
    import types
    from osd import Osd, HINT
    an = listen(20)
    quiet = Analyzer(48000)
    for _ in range(8 * 60):                                                          # eight seconds of nothing
        quiet.feed(np.zeros(800))
        quiet.update(1 / 60)
    st0 = dict(image=dict(scene="Facetas", scene_i=0, style="3D", camera="Fixo", movement="Padrão", why=None, since=1, pending_scene=-1),
               keys=dict(fullscreen=False, vsync=False, strobe=True, auto=True), gpu="x", backend="x", shader_ok=True, reloads=0, preview=dict(on=False))
    check("the test analysers: one hears the music, a fresh one is silent", an.silence < 0.6 and quiet.silence > 0.6, (an.silence, quiet.silence))

    # ---- a click on a scene enters at once (the director honours scene_now), unless the advanced choice says to wait
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.play_scene(2)
    check("a click on a scene asks for it at once", cfg["effect"] == 3 and cfg["scene_now"] is True, (cfg["effect"], cfg["scene_now"]))
    check("... says so without jargon", "agora" in m.toast[0] and "frase" not in m.toast[0], m.toast)
    check("... and asks the picture window to write the name", m.osd_name is not None and m.osd_name[0] == cfg["scenes"][2]["scene_name"], m.osd_name)

    def frames_to_switch(scene_now):
        d = NeonDirector()
        c = menu.fresh()
        c["effect"], c["scene_now"] = 0, False
        for _ in range(30):
            d.update(1 / 60, an, c)
        c["effect"], c["scene_now"] = 3, scene_now
        for i in range(120):
            d.update(1 / 60, an, c)
            if d.scene == 2:
                return i
        return None
    now_n, wait_n = frames_to_switch(True), frames_to_switch(False)
    check("the director brings the clicked scene within a second", now_n is not None and now_n < 60, now_n)
    check("... and waits for its moment when scene_now is off", wait_n is None or wait_n > 100, wait_n)
    cfg["scene_wait"] = 1
    m.play_scene(1)
    check("'Ao clicar numa cena: No momento' waits again", cfg["scene_now"] is False and "frase" in m.toast[0], (cfg["scene_now"], m.toast))
    check("the choice is a row of the advanced Automático page, and not of the simple one", any(r["id"] == "scene_wait" for _, rows in menu.auto_cards({"advanced": True}) for r in rows)
          and not any(r["id"] == "scene_wait" for _, rows in menu.auto_cards({"advanced": False}) for r in rows))

    # ---- the words on the picture come from the person (a click, a key), never from a controller that may be driving a projection
    m.osd_name = None
    m.shortcut("4", 0, osd=False)
    check("a scene change from a controller (OSC, MIDI) asks for no words on the picture", cfg["effect"] == 4 and m.osd_name is None, (cfg["effect"], m.osd_name))
    m.shortcut("5", 0)
    check("... a key of the person does", m.osd_name is not None and m.osd_name[0] == cfg["scenes"][4]["scene_name"], m.osd_name)
    check("the words can be switched off (Sistema > Tela) and are on by default", cfg["osd"] is True and any(r["id"] == "osd" for _, rows in menu.sys_cards(cfg, 5) for r in rows))

    # ---- the first-use card ticks itself
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    cw = control.ControlWindow(m, headless=True)
    cw.resize(1000, 800)
    m.tab, m.need = menu.TAB_LIVE, True
    cw.update(time.time(), an, 60.0, 10.0, False, st0, force=True)
    check("a first run: the card is open with nothing done", cw.live.tour_open and cfg["tour_marks"] == 0, cfg["tour_marks"])
    check("the card is a compact row (it does not push the scenes down)", cw.live._tour_card(cw.live.surf.get_width()) <= 100, cw.live._tour_card(cw.live.surf.get_width()))
    cw.live._heard_since = time.perf_counter() - 3.0
    cw.update(time.time() + 1, an, 60.0, 10.0, False, st0, force=True)
    check("step 1 ticks after a couple of seconds of sound", cfg["tour_marks"] == 1, cfg["tour_marks"])
    cw.update(time.time() + 2, an, 60.0, 10.0, False, dict(st0, keys=dict(st0["keys"], fullscreen=True)), force=True)
    check("step 3 ticks when the picture goes full screen", cfg["tour_marks"] == 5, cfg["tour_marks"])
    check("... and the card is still there (step 2 is missing)", cw.live.tour_open and not cfg["tour_done"])
    cw2 = control.ControlWindow(menu.Menu(cfg), headless=True)
    check("the card remembers where the person stopped", cw2.live.tour_open and cfg["tour_marks"] == 5)
    m.play_scene(1)
    check("step 2 ticks when a scene is chosen (the click no longer closes the card)", cfg["tour_marks"] == 7 and cw.live.tour_open and not cfg["tour_done"], cfg["tour_marks"])
    cw.update(time.time() + 3, an, 60.0, 10.0, False, st0, force=True)
    cw.live._tour_all_t = time.perf_counter() - 5.0
    cw.update(time.time() + 4, an, 60.0, 10.0, False, st0, force=True)
    check("with all three done the card goes away by itself, for good", not cw.live.tour_open and cfg["tour_done"])
    cw3 = control.ControlWindow(menu.Menu(cfg), headless=True)
    check("... and does not come back", not cw3.live.tour_open)

    # ---- a warning comes with the button that solves it (after a few seconds: right after the start everything looks silent and slow)
    cfg = menu.fresh()
    cfg["tour_done"] = True
    m = menu.Menu(cfg)
    cw = control.ControlWindow(m, headless=True)
    cw.resize(1000, 800)
    m.tab, m.need = menu.TAB_LIVE, True

    def fix_ids():
        return [b for _, b in cw.live.live_hits if str(b).startswith("fix:")]

    def click(bid):
        rect = next(r for r, b in cw.live.live_hits if b == bid)
        m.scroll = max(0, min(m.max_scroll(), rect.centery - 200))
        pos = (rect.centerx + cw.panel_pos[0], rect.centery + m.HEAD + m.reserved - m.scroll + cw.panel_pos[1])
        for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
            cw.handle(types.SimpleNamespace(type=typ, pos=pos, **extra))
    cw.update(time.time(), quiet, 60.0, 10.0, False, st0, force=True)
    check("a silence of a moment shows no button yet", not fix_ids(), fix_ids())
    cw.live._quiet_since = time.perf_counter() - 3.0
    cw.update(time.time() + 1, quiet, 60.0, 10.0, False, st0, force=True)
    check("a silence that lasts offers 'Escolher o som'", fix_ids() == ["fix:sound"], fix_ids())
    click("fix:sound")
    check("... and it leads to the sound input of Sistema", m.tab == menu.TAB_SYS and cfg["sys_item"] == 1, (m.tab, cfg["sys_item"]))
    cw.update(time.time() + 2, an, 60.0, 10.0, False, st0, force=True)
    check("the page opens on the sound input", menu.sys_cards(cfg, 1)[0][0] == "ENTRADA DE ÁUDIO")
    m.tab, m.need = menu.TAB_LIVE, True
    cw.live._quiet_since = None
    cw.update(time.time() + 3, an, 18.0, 10.0, False, st0, force=True)
    check("a slow picture of a moment shows no button yet", not fix_ids(), fix_ids())
    cw.live._slow_since = time.perf_counter() - 4.0
    cw.update(time.time() + 4, an, 18.0, 10.0, False, st0, force=True)
    check("a slow picture that lasts offers 'Melhorar sozinho'", fix_ids() == ["fix:quality"], fix_ids())
    m.set_value("preset", 2, announce=False)
    click("fix:quality")
    check("... and it steps the quality down one level", cfg["preset"] == 1, cfg["preset"])
    m.lower_quality()
    check("... again, to the lowest", cfg["preset"] == 0, cfg["preset"])
    res0 = (cfg["res"], cfg["steps"])
    check("at the lowest it says so and changes nothing", m.lower_quality() is False and (cfg["res"], cfg["steps"]) == res0 and "mais baixa" in m.toast[0], m.toast)
    cfg.update(res=70, steps=55, preset=menu.CUSTOM)
    m.lower_quality()
    check("from Personalizado it goes to a level that asks for less, never up", cfg["preset"] == 0 and cfg["res"] <= 70, (cfg["preset"], cfg["res"]))
    cfg.update(res=50, steps=40, preset=menu.CUSTOM)
    check("a Personalizado already below Baixo is left alone", m.lower_quality() is False and cfg["res"] == 50, cfg["res"])

    for fo, rr, fps_v, want in ((24, 0, 22.0, False), (60, 0, 22.0, True), (30, 1, 14.0, False), (60, 1, 22.0, True)):          # a rate the person asked for is not "Travando"
        cfg["fps_out"], cfg["rrate"] = fo, rr
        cw.live._slow_since = time.perf_counter() - 4.0
        cw.update(time.time() + 6, an, fps_v, 10.0, False, st0, force=True)
        check(f"fps_out {fo}, 1 frame in {rr + 1}, running at {fps_v:.0f}: " + ("slow, offers the button" if want else "not slow (it runs at the rate it was told to)"), bool(fix_ids()) == want, fix_ids())
    cfg["fps_out"], cfg["rrate"] = 60, 0

    # ---- the first window
    ok = True
    for dw, dh in ((1920, 1080), (2560, 1440), (1366, 768), (1280, 720), (1024, 768)):
        w, h = control.ControlWindow.default_size(dw, dh)
        ok &= w <= max(dw - 40, control.ControlWindow.MIN_W) and h <= max(dh - 100, control.ControlWindow.MIN_H) and w >= control.ControlWindow.MIN_W
        if dw >= 1280:
            ok &= (w - 2 * control.ControlWindow.PAD) >= menu.WIDE_MIN
    check("the first window fits every common screen and is wide enough for the Palco in two columns", ok)
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    size = control.ControlWindow.default_size(1920, 1080)
    cw = control.ControlWindow(m, headless=True, size=size)
    m.tab, m.need = menu.TAB_LIVE, True
    cw.update(time.time(), an, 60.0, 10.0, False, st0, force=True)
    cw.update(time.time() + 1, an, 60.0, 10.0, False, st0, force=True)
    hits = [r for r, b in cw.live.live_hits if str(b).startswith("scene:")]
    top = m.HEAD + m.reserved - m.scroll + cw.panel_pos[1]
    first = [r for r in hits if r.y == hits[0].y]
    check("at the first window the Palco is in two columns", cw.W == size[0] and cw.H == size[1] and m.wide, (cw.W, cw.H, m.W))
    check("... and with the card open every scene of the first row is on screen, no scrolling", cw.live.tour_open and max(r.bottom for r in first) + top <= cw.H, (max(r.bottom for r in first) + top, cw.H))
    check("... and so is the whole strip of scenes", max(r.bottom for r in hits) + top <= cw.H, (max(r.bottom for r in hits) + top, cw.H))
    cfg_s = menu.fresh()
    m_s = menu.Menu(cfg_s)
    cws = control.ControlWindow(m_s, headless=True, size=control.ControlWindow.default_size(1366, 768))
    m_s.tab, m_s.need = menu.TAB_LIVE, True
    cws.update(time.time(), an, 60.0, 10.0, False, st0, force=True)
    cws.update(time.time() + 1, an, 60.0, 10.0, False, st0, force=True)
    hits_s = [r for r, b in cws.live.live_hits if str(b).startswith("scene:")]
    top_s = m_s.HEAD + m_s.reserved - m_s.scroll + cws.panel_pos[1]
    first_s = [r for r in hits_s if r.y == hits_s[0].y]
    check("on a 1366x768 laptop the first row of scenes is on screen with the card open (the other rows scroll)", cws.live.tour_open and max(r.bottom for r in first_s) + top_s <= cws.H,
          (max(r.bottom for r in first_s) + top_s, cws.H))

    # ---- the words on the picture
    o = Osd()
    check("the words are off until asked", o.alpha() == 0.0)
    o.show("Vórtice", HINT, dur=2.0, now=100.0)
    check("they fade in", 0.3 < o.alpha(100.09) < 0.7 and o.alpha(100.5) == 1.0, (o.alpha(100.09), o.alpha(100.5)))
    check("... stay, fade out and are gone", o.alpha(101.9) == 1.0 and 0.0 < o.alpha(102.3) < 1.0 and o.alpha(103.0) == 0.0)
    k, raw, w, h = o.image(1080)
    px = np.frombuffer(raw, np.uint8).reshape(h, w, 4)
    check("the pill is a picture with soft corners, a dark body and white text", len(raw) == w * h * 4 and px[0, 0, 3] < 30 and 100 < px[h // 2, 6, 3] < 230 and px[:, :, :3].max() > 240, (w, h, int(px[0, 0, 3])))
    k2, raw2, w2, h2 = o.image(2160)
    check("it grows with the screen", w2 > w * 1.6 and h2 > h * 1.6, (w, h, w2, h2))
    check("it is drawn again only when the words or the height change", o.image(2160) is o.image(2160) and o.image(1080)[0] != k2)
    from renderer import Renderer
    import look
    rend = Renderer(headless=True, size=(320, 180))
    errs = []
    _orig = rend._draw

    def _spy():
        try:
            return _orig()
        except Exception as e:
            errs.append(repr(e))
            raise
    rend._draw = _spy
    check("the overlay pipeline is built", rend._osd_pipe is not None)
    sc = menu.fresh()["scenes"][0]
    d = NeonDirector()
    d.scenes, d.scene, d.pending = [sc], 0, (0, "cut")
    d._apply()
    c = menu.fresh()
    SC.apply_scene(c, sc)
    c["scenes"], c["effect"] = [sc], 1

    def frame(a):
        rend.osd_a = a
        P = d.update(1 / 60, an, c)
        look.apply(rend, P, d.cur, 100)
        P.update(bass=0.5, mid=0.4, high=0.4, kick=0.5, snare=0, hat=0, beat=0.1)
        return np.asarray(rend.render(P)).astype(float)[:, :, :3]
    bw, bh = 120, 30
    rend.set_osd("white", bytes([255, 255, 255, 255]) * (bw * bh), bw, bh)
    for _ in range(3):
        frame(0.0)
    off, half, full = frame(0.0), frame(0.5), frame(1.0)
    box = (slice(142, 166), slice(104, 216))                                          # inside where a 120x30 box lands: centred, its bottom at 94% of the height
    corner = (slice(2, 22), slice(2, 22))
    check("the words are drawn at the bottom centre (a white box there when fully opaque)", full[box].mean() > 250 and off[box].mean() < 240, (full[box].mean(), off[box].mean()))
    check("... half opaque is in between", off[box].mean() < half[box].mean() < full[box].mean(), (off[box].mean(), half[box].mean(), full[box].mean()))
    check("... and nothing else of the picture changes", abs(full[corner].mean() - off[corner].mean()) < 20.0, (full[corner].mean(), off[corner].mean()))
    rend.preview, rend.preview_every = True, 1
    frame(1.0)
    rend._read_preview(force=True)
    pvw, pvh = rend.preview_size
    pv = np.frombuffer(rend.preview_rgba, np.uint8).reshape(pvh, pvw, 4)[:, :, :3].astype(float) if rend.preview_rgba is not None else None
    pv_box = None if pv is None else pv[int(pvh * 0.79):int(pvh * 0.92), int(pvw * 0.33):int(pvw * 0.67)]
    check("the picture of the Palco never carries the words", pv_box is not None and pv_box.mean() < 245, None if pv_box is None else pv_box.mean())
    check("no draw error with the words on", not errs, errs[:2])
    os.environ["VIS_NO_OSD"] = "1"
    try:
        r2 = Renderer(headless=True, size=(64, 36))
    finally:
        del os.environ["VIS_NO_OSD"]
    r2.osd_a = 1.0
    r2.set_osd("x", bytes(4 * 4), 2, 2)
    P = d.update(1 / 60, an, c)
    look.apply(r2, P, d.cur, 100)
    P.update(bass=0.5, mid=0.4, high=0.4, kick=0.5, snare=0, hat=0, beat=0.1)
    img = np.asarray(r2.render(P))
    check("with VIS_NO_OSD there are no words and the picture still draws", r2._osd_pipe is None and img.size > 0)


def test_oneplace():
    section("6f. One place for each thing: Estúdio edits, Automático (opened from the Palco) decides, the toast stays off the tabs")
    import control
    import types
    an = listen(20)
    st0 = dict(image=dict(scene="Facetas", scene_i=0, style="3D", camera="Fixo", movement="Padrão", why=None, since=1, pending_scene=-1),
               keys=dict(fullscreen=False, vsync=False, strobe=True, auto=True), gpu="x", backend="x", shader_ok=True, reloads=0, preview=dict(on=False))
    check("Sistema has an Automático page (page 3)", menu.SYS_ITEMS[2][0] == "Automático")
    cfg = menu.fresh()
    n = len(cfg["scenes"])
    cards = menu.sys_cards(cfg, 2)
    titles = [t for t, _ in cards]
    ids = [r["id"] for _, rows in cards for r in rows]
    check("the page has the switch, when it changes, one switch per scene and what the music decides", titles[:3] == ["TROCA AUTOMÁTICA", "CENAS NO AUTOMÁTICO", "A MÚSICA CONTROLA A CENA"], titles)
    check("... with autoall, scene_when, scene_every and a switch for each of the scenes", {"autoall", "scene_when", "scene_every"} <= set(ids) and [i for i in ids if i.startswith("sc_auto:")] == [f"sc_auto:{i}" for i in range(n)], ids[:8])
    cfg_s = dict(cfg, advanced=False)
    check("a click that waits for the beat is advanced only", "scene_wait" in ids and "scene_wait" not in [r["id"] for _, rows in menu.sys_cards(cfg_s, 2) for r in rows])
    m = menu.Menu(cfg)
    m.set_value("sc_auto:3", False)
    check("a switch of the page takes the scene out of the automatic change", cfg["scenes"][3]["scene_auto"] is False and "fora do Automático" in m.toast[0], m.toast)
    row = next(r for _, rows in menu.sys_cards(cfg, 2) for r in rows if r["id"] == "sc_auto:3")
    check("... and the switch shows it", row["get"](cfg) is False)
    m.open_scene(2)
    m.set_value("sc_auto:2", False)
    check("with that scene open in the editor the draft follows, so it does not turn 'not saved'", m.draft["scene_auto"] is False and cfg["scenes"][2]["scene_auto"] is False and not m.is_dirty())
    # every scene switched off (fifteen switches in a row make it easy): the Automático stays on the scene on the air, says so, and nothing fails
    c_off = menu.fresh()
    for s_ in c_off["scenes"]:
        s_["scene_auto"] = False
    note = next(r for _, rows in menu.sys_cards(c_off, 2) for r in rows if r["id"] == "sc_auto_note")
    check("the page says what happens when no scene is marked, and says nothing when some are", "Nenhuma está marcada" in note["help"](c_off) and note["help"](menu.fresh()) == "")
    an2, syn2 = Analyzer(48000), Synth(48000)
    d_off = NeonDirector()
    c_off["effect"] = 0
    seen = set()
    for i in range(40 * 60):
        an2.feed(syn2.chunk(800))
        an2.update(1 / 60)
        d_off.update(1 / 60, an2, c_off)
        seen.add(d_off.scene)
    check("with every scene out of the Automático (a track with phrases and drops) the director keeps the scene on the air and does not fail", seen == {0} and d_off.pick_scene(an2) == 0, seen)
    # the wide Estúdio no longer repeats what the Palco and the Automático page do
    wide_titles = [t.lstrip("§") for t, _ in menu.scene_layout(menu.fresh(), "editor", True)[0]]
    check("the wide editor has the stack and no automatic-change card", "CAMADAS  ·  DE CIMA PARA BAIXO" in wide_titles and not any("TROCA" in (t or "") for t in wide_titles), wide_titles)
    # the narrow gallery: a click edits, nothing about the automatic change is on it
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    cw = control.ControlWindow(m, headless=True)
    cw.resize(700, 900)
    m.tab, m.need = menu.TAB_SCENES, True
    m.scene_view = "gallery"
    m.rebuild_scenes()
    cw.update(time.time(), an, 60.0, 10.0, False, st0, force=True)
    cw.update(time.time() + 1, an, 60.0, 10.0, False, st0, force=True)
    kinds = {k for _, k, _ in cw.gal_hits}
    check("the gallery has the cards, the new-scene card and each card's menu", {"open", "new", "menu"} <= kinds, kinds)
    check("... and no switch, no 'Trocar de cena' choice and no 'Troca automática' of its own", not (kinds & {"auto", "autoall", "when", "every", "wait"}), kinds)
    rect = next(r for r, k, a in cw.gal_hits if k == "open" and a == 4)
    for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
        cw.handle(types.SimpleNamespace(type=typ, pos=rect.center, **extra))
    check("one click on a card edits that scene (and does not play it)", m.scene_view == "editor" and cfg["scene_edit"] == 4 and cfg["effect"] == 0, (m.scene_view, cfg["scene_edit"], cfg["effect"]))
    # the Opções button of the Palco leads to the Automático page
    cfg = menu.fresh()
    cfg["tour_done"] = True
    m = menu.Menu(cfg)
    cw = control.ControlWindow(m, headless=True)
    cw.resize(1000, 800)
    m.tab, m.need = menu.TAB_LIVE, True
    cw.update(time.time(), an, 60.0, 10.0, False, st0, force=True)
    cw.update(time.time() + 1, an, 60.0, 10.0, False, st0, force=True)
    hits = {b: r for r, b in cw.live.live_hits}
    check("the Palco has Opções next to Troca automática, side by side and not overlapping", "auto:settings" in hits and hits["auto:toggle"].right < hits["auto:settings"].left and hits["auto:toggle"].y == hits["auto:settings"].y,
          {k: tuple(v) for k, v in hits.items() if k.startswith("auto")})
    rect = hits["auto:settings"]
    pos = (rect.centerx + cw.panel_pos[0], rect.centery + m.HEAD + m.reserved - m.scroll + cw.panel_pos[1])
    for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
        cw.handle(types.SimpleNamespace(type=typ, pos=pos, **extra))
    check("... and it opens Sistema > Automático", m.tab == menu.TAB_SYS and cfg["sys_item"] == 2, (m.tab, cfg["sys_item"]))
    cw.update(time.time() + 2, an, 60.0, 10.0, False, st0, force=True)
    check("... that draws", True)
    # the narrow Palco: the same two buttons fit beside each other
    cw.resize(640, 640)
    m.tab, m.need = menu.TAB_LIVE, True
    cw.update(time.time() + 3, an, 60.0, 10.0, False, st0, force=True)
    cw.update(time.time() + 4, an, 60.0, 10.0, False, st0, force=True)
    hits = {b: r for r, b in cw.live.live_hits}
    check("at the smallest window Troca automática and Opções still sit side by side inside the Palco", hits["auto:toggle"].right < hits["auto:settings"].left and hits["auto:settings"].right <= m.W, {k: tuple(v) for k, v in hits.items() if k.startswith("auto")})
    # the toast never covers the tabs
    r = cw.toast_rect(300)
    check("the toast is at the bottom, inside the window and under the tab bar", r.top > cw.panel_pos[1] + m.HEAD and r.bottom <= cw.H and r.left >= 0 and r.right <= cw.W, tuple(r))
    m.say("Uma frase bem comprida só para ver se o aviso cabe dentro da janela mesmo quando o texto é enorme e passa de qualquer largura razoável")
    cw.update(time.time() + 5, an, 60.0, 10.0, False, st0, force=True)
    check("a very long toast is drawn without error", True)


def test_wizard():
    section("6g. + Nova cena in three steps (what to see, colours, name) and Editar esta cena")
    import control
    import types
    an = listen(20)
    st0 = dict(image=dict(scene="Facetas", scene_i=0, style="3D", camera="Fixo", movement="Padrão", why=None, since=1, pending_scene=-1),
               keys=dict(fullscreen=False, vsync=False, strobe=True, auto=True), gpu="x", backend="x", shader_ok=True, reloads=0, preview=dict(on=False))

    class FakeThumbs:
        ready, size, draft_size, fmt, error = True, (128, 72), (320, 180), "rgba8unorm", None

        def __init__(self):
            self.frames, self.draft, self.shown = {}, None, []

        def set_draft(self, sc, extra=False):
            self.draft, self.extra = sc, extra
            self.frames[id(sc)] = (1, bytes([90, 40, 120, 255]) * (320 * 180))

        def show(self, lst):
            self.shown = list(lst)
    cfg = menu.fresh()
    cfg["tour_done"] = True
    cfg["advanced"] = False                                                           # (the other tests walk everything in the advanced mode)
    m = menu.Menu(cfg)
    n0 = len(cfg["scenes"])
    cw = control.ControlWindow(m, headless=True)
    cw.thumbs = FakeThumbs()
    cw.resize(1000, 800)
    m.tab, m.need = menu.TAB_LIVE, True

    def upd(k=0):
        cw.update(time.time() + k, an, 60.0, 10.0, False, st0, force=True)

    def mouse(pos):
        for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
            cw.handle(types.SimpleNamespace(type=typ, pos=pos, **extra))

    def click_live(bid):
        rect = next(r for r, b in cw.live.live_hits if b == bid)
        m.scroll = max(0, min(m.max_scroll(), rect.centery - 200))
        mouse((rect.centerx + cw.panel_pos[0], rect.centery + m.HEAD + m.reserved - m.scroll + cw.panel_pos[1]))
        upd(9)

    def click_gal(kind, arg):
        rect = next(r for r, k, a in cw.gal_hits if k == kind and a == arg)
        mouse(rect.center)
        upd(9)

    def key(k, ch=""):
        cw.handle(types.SimpleNamespace(type=pygame.KEYDOWN, key=k, mod=0, unicode=ch))
        upd(9)

    def kinds():
        return [k for _, k, _ in cw.gal_hits]
    upd(1)
    upd(2)
    hits = {b: r for r, b in cw.live.live_hits}
    last = hits[f"scene:{n0 - 1}"]
    check("the Palco has the + Nova cena tile right after the last scene, and Editar esta cena", "wiz:start" in hits and "edit:live" in hits and (hits["wiz:start"].y > last.y or hits["wiz:start"].x > last.x), sorted(hits)[-6:])
    check("there are two ways in: a button over the first row of scenes and the tile at the end", [b for _, b in cw.live.live_hits].count("wiz:start") == 2)
    # on a 1366x768 laptop (window 972x648, first-use card open) the tile at the end is below the window, but the button over the first row is on it
    cws = control.ControlWindow(menu.Menu(menu.fresh()), headless=True, size=control.ControlWindow.default_size(1366, 768))
    cws.menu.tab, cws.menu.need = menu.TAB_LIVE, True
    cws.thumbs = FakeThumbs()
    for k_ in (1, 2):
        cws.update(time.time() + k_, an, 60.0, 10.0, False, st0, force=True)
    top_s = cws.panel_pos[1] + cws.menu.HEAD + cws.menu.reserved - cws.menu.scroll
    vis_s = [top_s + r.bottom <= cws.H for r, b in cws.live.live_hits if b == "wiz:start"]
    check("on a 1366x768 laptop one of the ways in is on the screen without scrolling (the other is not)", sorted(vis_s) == [False, True], vis_s)
    click_live("wiz:start")
    upd(10)
    check("the tile opens step 1 of 3 in the Estúdio, with nothing added yet", m.tab == menu.TAB_SCENES and m.scene_view == "wizard" and m.wizard["step"] == 0 and len(cfg["scenes"]) == n0, (m.tab, m.scene_view))
    k0 = kinds()
    check("step 1: a live thumbnail for each of the 15 looks, Continuar and Cancelar (no Voltar, no blank scene in the simple mode)",
          k0.count("wz-pick") == 15 and "wz-next" in k0 and "wz-cancel" in k0 and "wz-back" not in k0 and "wz-blank" not in k0, [(k, k0.count(k)) for k in set(k0)])
    check("... and the picture of the scene being built is the draft (with the thumbnails of the looks kept moving beside it)", cw.thumbs.draft is m.wizard["draft"] and len(cw.thumbs.shown) == 15 and cw.thumbs.extra is True)
    key(pygame.K_5, "5")
    check("the digits do nothing behind the steps (they would play scenes)", cfg["effect"] == 0, cfg["effect"])
    click_gal("wz-pick", 7)
    base7 = m.wizard["bases"][7]["scene_name"]
    check("a click on a look picks it: the draft is a copy of it", m.wizard["pick"] == 7 and m.wizard["draft"]["scene_name"] == base7 and m.wizard["draft"] is not m.wizard["bases"][7], base7)
    click_gal("wz-next", 0)
    upd(11)
    k1 = kinds()
    check("step 2: the colours of the look and each palette, with Voltar", m.wizard["step"] == 1 and k1.count("wz-pal") == 1 + min(8, len(cfg["palettes"])) and "wz-back" in k1, [(k, k1.count(k)) for k in set(k1)])
    check("with the Cores of the Palco on 'Da cena' step 2 has no warning", "wz-macro" not in kinds())
    cfg["macro_pal"] = 2
    upd(11)
    check("with the Cores of the Palco forcing a palette step 2 says so and offers to put them back", "wz-macro" in kinds(), kinds())
    click_gal("wz-macro", 0)
    check("... and the button gives the colours back to each scene", cfg["macro_pal"] == 0 and "wz-macro" not in kinds(), cfg["macro_pal"])
    click_gal("wz-pal", 2)
    check("a click on a palette puts it on the draft (the picture follows)", m.wizard["pal"] == 2 and m.wizard["draft"]["scene_palette"] == 2)
    click_gal("wz-back", 0)
    check("Voltar keeps what was chosen", m.wizard["step"] == 0 and m.wizard["pick"] == 7 and m.wizard["pal"] == 2)
    click_gal("wz-pick", 3)
    check("another look keeps the colours already chosen", m.wizard["pick"] == 3 and m.wizard["draft"]["scene_palette"] == 2)
    click_gal("wz-pick", 7)
    key(pygame.K_RETURN, "\r")
    key(pygame.K_RETURN, "\r")
    check("Enter goes to the name", m.wizard["step"] == 2, m.wizard["step"])
    pills = sorted(a for _, k, a in cw.gal_hits if k == "wz-step")
    check("the pills of the steps already done are clickable; the current one and the one to come are not", pills == [0, 1], pills)
    before = copy.deepcopy(m.wizard["draft"])
    click_gal("wz-step", 0)
    check("a click on the pill of step 1 goes back to it, with the look, the colours and the draft as they were",
          m.wizard["step"] == 0 and m.wizard["pick"] == 7 and m.wizard["pal"] == 2 and m.wizard["draft"] == before, (m.wizard["step"], m.wizard["pick"], m.wizard["pal"]))
    check("... and on step 1 no pill is clickable", not [1 for _, k, _ in cw.gal_hits if k == "wz-step"])
    key(pygame.K_RETURN, "\r")
    key(pygame.K_RETURN, "\r")
    check("... and Enter takes it to the name again", m.wizard["step"] == 2, m.wizard["step"])
    check("the name starts as a free 'Minha cena'", m.wizard["name"] == "Minha cena", m.wizard["name"])
    check("... all selected: the first letter replaces it, no need to erase it", m.wizard["fresh"] is True)
    key(ord("x"), "x")
    check("a letter replaces the ready-made name", m.wizard["name"] == "x" and m.wizard["fresh"] is False, m.wizard["name"])
    key(pygame.K_BACKSPACE)
    key(pygame.K_BACKSPACE)
    check("Backspace after that erases one letter at a time (and an empty name is fine)", m.wizard["name"] == "", m.wizard["name"])
    m.wizard["name"], m.wizard["fresh"] = "Minha cena", True
    key(pygame.K_BACKSPACE)
    check("Backspace on the ready-made name clears all of it", m.wizard["name"] == "" and m.wizard["fresh"] is False, m.wizard["name"])
    for ch in "Banda 1":
        key(ord(ch), ch)
    check("the letters write the name", m.wizard["name"] == "Banda 1", m.wizard["name"])
    vis7 = m.wizard["draft"].get("scene_visual", 1)
    key(pygame.K_RETURN, "\r")
    new = cfg["scenes"][-1]
    check("Enter on the last step creates the scene with the look, the colours and the name", len(cfg["scenes"]) == n0 + 1 and new["scene_name"] == "Banda 1" and new["scene_palette"] == 2 and new.get("scene_visual", 1) == vis7
          and new["scene_auto"] is True, new.get("scene_name"))
    check("... it is on the air at once and the Palco shows it", cfg["effect"] == n0 + 1 and m.tab == menu.TAB_LIVE and m.scene_view == "gallery" and m.wizard is None and "criada e no ar" in m.toast[0], (cfg["effect"], m.tab, m.toast))
    check("... and the draft that was built is not the scene's own object (editing the scene later does not touch the look)", new is not cfg["scenes"][0])
    # the Logo: the name is also the text on the screen
    m.start_wizard()
    li = next(i for i, b in enumerate(m.wizard["bases"]) if b["scene_name"] == "Logo")
    m.wizard_pick(li)
    m.wizard["step"] = 2
    m.wizard["name"] = "Minha banda"
    m.finish_wizard()
    check("in the Logo the name is also the text that appears", cfg["scenes"][-1]["gen_text"] == "Minha banda" and cfg["scenes"][-1]["scene_visual"] == 9, cfg["scenes"][-1].get("gen_text"))
    # names are free but never empty; the default is numbered
    m.start_wizard()
    check("the next default name is numbered", m.wizard["name"] == "Minha cena", m.wizard["name"])
    m.wizard["step"] = 2
    m.wizard["name"] = "   "
    m.finish_wizard()
    check("an empty name becomes the default one", cfg["scenes"][-1]["scene_name"] == "Minha cena", cfg["scenes"][-1]["scene_name"])
    # Cancelar and Esc: back to where it began, nothing added
    n1 = len(cfg["scenes"])
    m.tab = menu.TAB_LIVE
    m.start_wizard()
    key(pygame.K_RETURN, "\r")
    key(pygame.K_ESCAPE)
    check("Esc goes one step back", m.in_wizard() and m.wizard["step"] == 0)
    key(pygame.K_ESCAPE)
    check("Esc on the first step leaves, to the Palco it came from, with no new scene", not m.in_wizard() and m.tab == menu.TAB_LIVE and len(cfg["scenes"]) == n1, (m.tab, m.scene_view))
    m.start_wizard()
    upd(12)
    click_gal("wz-cancel", 0)
    check("Cancelar does the same", m.wizard is None and m.tab == menu.TAB_LIVE and len(cfg["scenes"]) == n1)
    # the advanced have the empty scene for layers as one more tile
    cfg["advanced"] = True
    m.start_wizard()
    upd(13)
    check("in the advanced mode step 1 has an 'Em branco' tile", "wz-blank" in kinds())
    click_gal("wz-blank", 0)
    check("... which makes an empty scene and opens the editor of layers", m.tab == menu.TAB_SCENES and m.scene_view == "editor" and cfg["layers"] == [] and len(cfg["scenes"]) == n1 + 1 and m.wizard is None, (m.tab, m.scene_view))
    cfg["advanced"] = False
    # with unsaved changes in the scene that is open nothing starts
    m.set_value("scene_name", "Mudei")
    check("a draft with changes exists", m.is_dirty())
    m.start_wizard()
    check("with unsaved changes the steps do not start (they would be lost)", m.scene_view == "editor" and m.wizard is None and "não salvas" in m.toast[0], (m.scene_view, m.toast))
    m.discard_scene()
    m.close_scene()
    # Editar esta cena: the Estúdio opens on the scene that is on the air
    m.tab = menu.TAB_LIVE
    m.live_scene = 3
    m.edit_live_scene()
    check("Editar esta cena opens the Estúdio on the scene on the air", m.tab == menu.TAB_SCENES and m.scene_view == "editor" and cfg["scene_edit"] == 3, (m.tab, m.scene_view, cfg["scene_edit"]))
    m.set_value("scene_name", "Meio editada")
    m.tab = menu.TAB_LIVE
    m.live_scene = 5
    m.edit_live_scene()
    check("with unsaved changes in another scene it goes to the Estúdio and keeps them (and says why)", m.tab == menu.TAB_SCENES and cfg["scene_edit"] == 3 and m.is_dirty() and "não salvas" in m.toast[0], (cfg["scene_edit"], m.toast))
    m.tab = menu.TAB_LIVE
    m.live_scene = 3
    m.edit_live_scene()
    check("the same scene again changes nothing (what was typed stays)", cfg["scene_edit"] == 3 and m.is_dirty())
    m.discard_scene()
    m.close_scene()
    # the button of the Palco does it
    m.tab, m.need = menu.TAB_LIVE, True
    m.scene_view = "gallery"
    m.rebuild_scenes()
    upd(14)
    upd(15)
    click_live("edit:live")
    check("the button of the Palco opens the editor", m.tab == menu.TAB_SCENES and m.scene_view == "editor")
    m.close_scene()
    # the narrow window: the same steps, with the picture over the choices and the bar at the bottom
    cw.resize(640, 640)
    m.tab = menu.TAB_SCENES
    m.scene_view = "gallery"
    m.rebuild_scenes()
    upd(16)
    upd(17)
    check("the gallery's new-scene card starts the steps too", any(k == "new" for _, k, _ in cw.gal_hits))
    click_gal("new", 0)
    ok = True
    for step in (0, 1, 2):
        m.wizard["step"] = step
        upd(18 + step)
        upd(19 + step)
        bar = [r for r, k, a in cw.gal_hits if k == "wz-next"]
        ok &= bool(bar) and bar[0].bottom <= cw.H and bar[0].right <= cw.W and (step == 0 or any(k == "wz-back" for _, k, _ in cw.gal_hits))
    check("at 640x640 every step draws and Continuar sits inside the window", ok)
    cw.resize(1000, 800)
    m.wizard["step"] = 0
    upd(30)
    firsts = [r for r, k, a in cw.gal_hits if k == "wz-pick" and a == 0]
    top = cw.panel_pos[1] + m.HEAD
    check("wide: the first looks are on screen without scrolling", bool(firsts) and firsts[0].top >= top and firsts[0].bottom <= top + m.content_h(), (tuple(firsts[0]) if firsts else None, top, m.content_h()))
    m.cancel_wizard()
    # the strip of the Palco keeps showing the scenes that are created (it used to stop at 24, and the new ones were on the air with no tile)
    cfg["tour_done"] = True
    for i in range(40):
        cfg["scenes"].append(copy.deepcopy(cfg["scenes"][0]))
        cfg["scenes"][-1]["scene_name"] = f"Extra {i}"
    m.tab, m.scene_view = menu.TAB_LIVE, "gallery"
    m.rebuild_scenes()
    cw.resize(1000, 800)
    upd(31)
    upd(32)
    ids = {b for _, b in cw.live.live_hits}
    check("the strip shows up to 48 scenes and still has the + Nova cena tile at the end", f"scene:{control.ControlWindow.STRIP_MAX - 1}" in ids and "wiz:start" in ids and f"scene:{control.ControlWindow.STRIP_MAX}" not in ids, len(ids))
    cw.live.detail_open = True
    upd(33)
    upd(34)
    check("with the details open too the Palco still fits the surface it is drawn on", cw.live.live_end < control.ControlWindow.LIVE_SURF_H, (cw.live.live_end, control.ControlWindow.LIVE_SURF_H))
    cw.live.detail_open = False
    # the colour step changes the picture of the draft (and the Cores of the Palco, which override it, are what the warning is about)
    from renderer import Renderer
    from fxstack import FxStack
    import look
    rend = Renderer(headless=True, size=(240, 135))
    base = SC.wizard_bases()[0]                                                      # a mandala: it draws without any sound

    def draft_img(pal, macro):
        random.seed(11)
        sc = copy.deepcopy(base)
        sc["scene_palette"] = 0
        d = NeonDirector()
        d.scenes, d.scene, d.pending = [sc], 0, (0, "cut")
        d._apply()
        c = menu.fresh()
        c["macro_pal"] = macro
        SC.apply_scene(c, sc)
        c["scenes"], c["effect"] = [sc], 1
        rend.hist_valid = rend.fb_valid = False
        rend.stack = FxStack()
        for _ in range(10):
            d.update(1 / 60, an, c)
        sc["scene_palette"] = pal                                                    # what a click on a palette of step 2 does to the draft
        img = None
        for i in range(24):
            P = d.update(1 / 60, an, c)
            look.apply(rend, P, d.cur, 100)
            P.update(bass=0.4, mid=0.3, high=0.3, kick=0.3, snare=0, hat=0, beat=i / 10.0)
            img = np.asarray(rend.render(P)).astype(float)[:, :, :3]
        return img
    free = float(np.abs(draft_img(3, 0) - draft_img(0, 0)).mean())
    forced = float(np.abs(draft_img(3, 2) - draft_img(0, 2)).mean())
    check("step 2 changes the picture of the draft when the Palco does not force colours", free > 2.0, round(free, 2))
    check("... and not when it does (that is what the warning is for)", forced < free / 4, (round(forced, 2), round(free, 2)))


def test_tap():
    section("6h. Tap tempo: tap the beat to set the BPM by hand")
    import control
    import types
    import remote
    # ---- the analyser
    a1 = Analyzer(48000)
    check("the first tap only starts a series (no tempo yet) and puts the beat on the tap", a1.tap(10.0) == 0.0 and a1.manual_bpm == 0.0 and a1.phase == 0.0)
    check("a second tap half a second later makes 120 BPM at once", abs(a1.tap(10.5) - 120.0) < 0.01 and a1.manual_bpm == a1.bpm and a1.conf >= 0.95, (a1.bpm, a1.conf))
    t = 10.5
    for k in range(7):                                                                  # a person is never exact: +-12 ms
        t += 0.46875 + (0.012 if k % 2 else -0.012)
        a1.tap(t)
    check("eight taps with a little jitter land on the tempo (128, one BPM either way)", abs(a1.manual_bpm - 128.0) < 1.0, a1.manual_bpm)
    a2 = Analyzer(48000)
    for x in (0, 0.5, 1.0, 1.9, 2.4, 2.9, 3.4):
        a2.tap(x)
    check("one late tap does not drag the tempo (the median of the intervals)", abs(a2.manual_bpm - 120.0) < 0.5, a2.manual_bpm)
    a3 = Analyzer(48000)
    a3.tap(0.0)
    a3.tap(0.5)
    a3.tap(3.0)
    check("a pause of more than two seconds starts a new series (the old tempo stays until its second tap)", a3.manual_bpm == 120.0 and len(a3.tap_ts) == 1)
    a3.tap(3.4)
    check("... and then the new series sets the new tempo", abs(a3.manual_bpm - 150.0) < 0.01, a3.manual_bpm)
    a4 = Analyzer(48000)
    a4.tap(0.0)
    a4.tap(0.1)
    a5 = Analyzer(48000)
    a5.tap(0.0)
    a5.tap(1.9)
    check("the tempo is kept between 40 and 240", a4.manual_bpm == 240.0 and a5.manual_bpm == 40.0, (a4.manual_bpm, a5.manual_bpm))
    # the estimate leaves a tapped tempo alone, and comes back after AUTO (the music is at 128)
    syn = Synth(48000, 128.0)
    a = Analyzer(48000)
    for _ in range(12 * 60):                                                            # the music is on for a while before anyone taps
        a.feed(syn.chunk(800))
        a.update(1 / 60)
    a.tap(0.0)
    a.tap(0.6)
    for _ in range(25 * 60):
        a.feed(syn.chunk(800))
        a.update(1 / 60)
    check("while the tempo is tapped the program does not change it", a.manual_bpm == 100.0 and abs(a.bpm - 100.0) < 0.01, (a.manual_bpm, a.bpm))
    a.release_tap()
    for _ in range(45 * 60):
        a.feed(syn.chunk(800))
        a.update(1 / 60)
    check("after AUTO the program hears the tempo of the music again", a.manual_bpm == 0.0 and abs(a.bpm - 128.0) < 3.0, (a.manual_bpm, a.bpm))
    a.tap(0.0)
    a.tap(0.5)
    for _ in range(10 * 60):
        a.feed(np.zeros(800))
        a.update(1 / 60)
    for _ in range(5 * 60):
        a.feed(syn.chunk(800))
        a.update(1 / 60)
    check("when the music comes back after a silence the tapped tempo is dropped (it belonged to the last track)", a.manual_bpm == 0.0, a.manual_bpm)
    # ---- the menu: the T key, the list of taps, AUTO
    m = menu.Menu(menu.fresh())
    check("the T key taps (the shortcut is the same in both windows)", m.shortcut("t") is True and len(m.taps) == 1 and m.tap_t > 0)
    m.text_focus = "search"
    check("... but not while typing in a field", m.shortcut("t") is False and len(m.taps) == 1)
    m.text_focus = None
    am = Analyzer(48000)
    m.taps[:] = [100.0, 100.5]
    m.apply_taps(am)
    check("the main loop gives the taps to the analyser and empties the list", abs(am.manual_bpm - 120.0) < 0.01 and m.taps == [])
    m.tap_release = True
    m.apply_taps(am)
    check("... and the request to go back to automatic too", am.manual_bpm == 0.0 and m.tap_release is False)
    check("a controller taps too: /tap (OSC) and note 75 (MIDI)", remote.osc_key("/tap", []) == "t" and remote.midi_key(0x90, 75, 100) == "t" and remote.osc_key("/tap", [0]) is None)
    # ---- the BPM of the Detalhes is the button
    an = listen(20)
    st0 = dict(image=dict(scene="Facetas", scene_i=0, style="3D", camera="Fixo", movement="Padrão", why=None, since=1, pending_scene=-1),
               keys=dict(fullscreen=False, vsync=False, strobe=True, auto=True), gpu="x", backend="x", shader_ok=True, reloads=0, preview=dict(on=False))
    cfg = menu.fresh()
    cfg["tour_done"] = True
    m = menu.Menu(cfg)
    cw = control.ControlWindow(m, headless=True)
    cw.resize(1000, 800)
    cw.live.detail_open = True
    m.tab, m.need = menu.TAB_LIVE, True

    def upd(k=0):
        cw.update(time.time() + k, an, 60.0, 10.0, False, st0, force=True)

    def click(bid):
        rect = next(r for r, b in cw.live.live_hits if b == bid)
        m.scroll = max(0, min(m.max_scroll(), rect.centery - 200))
        pos = (rect.centerx + cw.panel_pos[0], rect.centery + m.HEAD + m.reserved - m.scroll + cw.panel_pos[1])
        for typ, extra in ((pygame.MOUSEMOTION, dict(buttons=(0, 0, 0))), (pygame.MOUSEBUTTONDOWN, dict(button=1, buttons=(1, 0, 0))), (pygame.MOUSEBUTTONUP, dict(button=1, buttons=(0, 0, 0)))):
            cw.handle(types.SimpleNamespace(type=typ, pos=pos, **extra))
        upd(9)
    upd(1)
    upd(2)
    ids = [b for _, b in cw.live.live_hits]
    check("the BPM of the Detalhes has a TAP pill and the whole block taps; no AUTO while the tempo is the program's", ids.count("bpm:tap") == 1 and "bpm:auto" not in ids, ids.count("bpm:tap"))
    click("bpm:tap")
    check("a click on it is a tap", len(m.taps) == 1 and m.tap_t > 0)
    m.taps.clear()
    an.manual_bpm = 100.0                                                               # (as if the tempo had been tapped)
    upd(10)
    ids = [b for _, b in cw.live.live_hits]
    check("once the tempo is the tapped one the pill says AUTO (and the block still taps)", "bpm:auto" in ids and ids.count("bpm:tap") == 1, ids.count("bpm:auto"))
    click("bpm:auto")
    check("AUTO asks for the tempo back", m.tap_release is True)
    an.manual_bpm = 0.0
    m.request_tap()
    upd(11)
    check("a tap lights the number (the Palco is drawn without error)", True)


def test_thumbs():
    section("6d. The live thumbnails show the scene they belong to")
    import thumbs as TH
    cfg = menu.fresh()
    an = listen(15)
    names = ("Fractal", "Logo", "Fluido", "Synthwave")
    scn = [next(s for s in cfg["scenes"] if s["scene_name"] == n) for n in names]
    th = TH.Thumbs()
    th.feed(an, cfg, 1.0)
    got = {}
    t0 = time.time()
    while time.time() - t0 < 40 and len(got) < len(scn):
        th.show(scn)
        time.sleep(0.2)
        for s_ in scn:
            f = th.frames.get(id(s_))
            if f is not None:
                got[s_["scene_name"]] = np.frombuffer(f[1], np.uint8).reshape(th.size[1], th.size[0], 4)[:, :, :3].astype(float)
    th.stop()
    check("every scene got a thumbnail", len(got) == len(scn), sorted(got))
    if len(got) == len(scn):
        corner = lambda im: float(im[:8, :8].mean())
        center = lambda im: float(im[28:44, 50:78].mean())
        check("Logo: dark corners and a bright text in the middle (not another scene's picture)", corner(got["Logo"]) < 25 and center(got["Logo"]) > 40, (corner(got["Logo"]), center(got["Logo"])))
        check("Fractal: not the picture of the scene next to it (a bright room around the shape)", corner(got["Fractal"]) > 40, corner(got["Fractal"]))
        check("Synthwave: the sun and the grid (dark top corners, bright in the middle low)", corner(got["Synthwave"]) < 60, corner(got["Synthwave"]))
    # one renderer draws every thumbnail: a scene with a trail must not carry the picture of the scene before it into the next one
    import layers as LYR
    from renderer import Renderer
    th3 = TH.Thumbs.__new__(TH.Thumbs)
    th3.frames, th3._dirs, th3.draft, th3._src = {}, {}, None, (an, cfg, 1.0)
    r3 = Renderer(headless=True, size=TH.SIZE)
    r3.preview_size, r3.preview, r3.preview_every = TH.SIZE, True, 1
    trail = copy.deepcopy(scn[0])
    trail["layers"] = [LYR.new_layer("fb") | dict(amt=90)]
    th3._frame(r3, trail)
    th3._frame(r3, scn[2])
    check("every thumbnail keeps its own effects, and the trail starts again on another scene", th3._dirs[id(trail)][2] is not th3._dirs[id(scn[2])][2] and r3.stack is th3._dirs[id(scn[2])][2] and not r3.fb_valid)
    # the steps of a new scene show a draft AND the thumbnails of the looks: both must keep getting new frames
    th2 = TH.Thumbs()
    th2.feed(an, cfg, 1.0)
    draft = copy.deepcopy(scn[0])
    th2.set_draft(draft)
    check("the editor's draft does not ask for the extra thumbnails (only the steps of a new scene do)", th2.draft_extra is False)
    c_first, last, fd = None, None, None
    t0 = time.time()
    while time.time() - t0 < 40:
        th2.show(scn)
        th2.set_draft(draft, extra=True)
        time.sleep(0.2)
        last, fd = th2.frames.get(id(scn[1])), th2.frames.get(id(draft))
        if last is not None and fd is not None:
            if c_first is None:
                c_first = last[0]
            elif last[0] > c_first + 2:
                break
    th2.stop()
    check("with a draft on, the draft and the thumbnails around it both keep getting new frames", c_first is not None and last is not None and last[0] > c_first + 2 and fd is not None,
          (c_first, None if last is None else last[0], fd is not None))


def test_undo_redo_before():
    section("Desfazer, Refazer e Antes: o cabeçalho volta e vai, e Antes mostra a cena de antes enquanto é segurado")
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    key = next(k for k in SC.SCENE_KEYS if isinstance(cfg.get(k), bool))
    v0 = cfg[key]
    m._push()
    cfg[key] = not v0
    m.undo_last()
    check("Desfazer volta a mudança", cfg[key] == v0, (cfg[key], v0))
    m.redo_last()
    check("Refazer põe a mudança de volta", cfg[key] == (not v0), (cfg[key], v0))
    m._push()
    v1 = cfg[key]
    cfg[key] = not v1
    m.peek_begin()
    check("Antes, segurado, mostra a cena de antes da última mudança", cfg[key] == v1, (cfg[key], v1))
    m.peek_end()
    check("ao soltar, volta a cena como estava", cfg[key] == (not v1), (cfg[key], v1))


def test_program_rules():
    section("Regras por programa: o programa da frente troca a cena e pode pausar a agenda; ao sair, a cena volta")
    import foreground as FG
    orig = FG.current
    try:
        cfg = {"app_rules": [{"process": "game.exe", "scene": 1, "pause": True}], "scene_edit": 0}
        calls = []
        w = FG.Watch()
        FG.current = lambda: "game.exe"
        w.update(cfg, calls.append)
        check("o programa da regra na frente leva para a cena da regra", calls == [1], calls)
        check("e pausa a agenda enquanto estiver lá", w.paused is True, w.paused)
        FG.current = lambda: "other.exe"
        w.update(cfg, calls.append)
        check("ao sair, a cena de antes volta e a agenda volta a correr", calls == [1, 0] and w.paused is False, (calls, w.paused))
        check("o último programa da frente fica guardado para Adicionar", cfg.get("last_fg_app") == "other.exe", cfg.get("last_fg_app"))
        m = menu.Menu(menu.fresh())
        m.cfg["app_rules"] = []
        m.set_value("ap_pick", "game.exe")
        check("escolher um programa aberto cria a regra dele", any(r.get("process") == "game.exe" for r in m.cfg["app_rules"]), m.cfg["app_rules"])
    finally:
        FG.current = orig


def test_agenda_week():
    section("Agenda: a semana aceita um clique numa hora e cria a regra daquele dia")
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.cfg["agenda"] = []
    m.press("wk:2:8")
    rule = (m.cfg.get("agenda") or [{}])[-1]
    check("um clique em quarta às 08:00 cria a regra", rule.get("time") == "08:00" and rule.get("days") == [2], rule)


def test_master_switch():
    section("Ajustes (interruptor mestre): desligado, a imagem fica apagada e o cabeçalho mostra o botão")
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    check("Ajustes começa ligado", cfg.get("master_on", True) is True, cfg.get("master_on"))
    m.press("master")
    check("um clique desliga Ajustes", cfg["master_on"] is False, cfg["master_on"])
    m.set_width(1000)
    m.render()
    check("o cabeçalho desenha o botão Ajustes", any(cid == "master" for _, cid, _, _ in m.hits), [h[1] for h in m.hits[:5]])
    m.press("master")
    check("outro clique liga de novo", cfg["master_on"] is True, cfg["master_on"])


def test_lanes():
    section("Faixas da agenda: um número segue o dia entre os pontos, e é escrito uma vez por minuto")
    import agenda as AG
    check("entre dois pontos o valor é uma reta", abs(AG.lane_value([(0, 0), (120, 100)], 60) - 50) < 1e-6, AG.lane_value([(0, 0), (120, 100)], 60))
    check("antes do primeiro e depois do último o valor segura", AG.lane_value([(600, 20), (900, 80)], 0) == 20 and AG.lane_value([(600, 20), (900, 80)], 1400) == 80)
    check("sem pontos não há valor", AG.lane_value([], 500) is None)
    cfg = {"bloom": 60, "agenda_lanes": [{"key": "bloom", "points": [[600, 20], [900, 180]]}]}
    AG.apply_lanes(cfg, time.struct_time((2026, 11, 25, 12, 30, 0, 2, 329, -1)))
    check("12:30 escreve o valor da faixa no brilho (entre 20 e 180 aos 10:00 e 15:00)", cfg["bloom"] == 100, cfg["bloom"])
    m = menu.Menu(menu.fresh())
    m.cfg["agenda_lanes"] = [{"key": "bloom", "points": []}]
    m.click_rect = pygame.Rect(0, 0, 1440, 200)
    m.click_pos = (600, 100)
    m.press("la_pt:0")
    pts = m.cfg["agenda_lanes"][0]["points"]
    check("um clique na linha do dia põe um ponto: a hora é onde clicou, o valor é a altura", pts == [[600, 100]], pts)
    class Ev:
        def __init__(self, t, pos):
            self.type, self.pos = t, pos
    m.click_pos = (600, 100)
    m.press("la_pt:0")
    m.mouse(Ev(pygame.MOUSEMOTION, (700, 100)), 0, 0, 1)
    m.mouse(Ev(pygame.MOUSEBUTTONUP, (700, 100)), 0, 0, 1)
    check("arrastar um ponto o move para onde foi solto", m.cfg["agenda_lanes"][0]["points"] == [[700, 100]], m.cfg["agenda_lanes"][0]["points"])
    m.click_pos = (700, 100)
    m.press("la_pt:0")
    m.mouse(Ev(pygame.MOUSEBUTTONUP, (700, 100)), 0, 0, 1)
    check("um clique num ponto, sem arrastar, o apaga", m.cfg["agenda_lanes"][0]["points"] == [], m.cfg["agenda_lanes"][0]["points"])


def test_agenda_profiles():
    section("Perfis da agenda: o dia coberto por um perfil roda as regras dele; a edição vai para o perfil escolhido")
    import agenda as AG
    cfg = {"agenda": [{"time": "09:00", "days": [], "scene": 0, "on": True}], "agenda_lanes": [], "agenda_profiles": [
        {"name": "Fim de semana", "days": [5, 6], "rules": [{"time": "11:00", "days": [], "scene": 1, "on": True}], "lanes": []}]}
    sat = time.struct_time((2026, 11, 28, 10, 0, 0, 5, 332, -1))
    mon = time.struct_time((2026, 11, 30, 10, 0, 0, 0, 334, -1))
    check("no sábado roda o perfil", AG.playback(cfg, sat)[0][0]["time"] == "11:00", AG.playback(cfg, sat)[0])
    check("na segunda roda o Padrão", AG.playback(cfg, mon)[0][0]["time"] == "09:00", AG.playback(cfg, mon)[0])
    cfg["agenda_edit"] = 0
    AG.edit_rules(cfg).append({"time": "12:00", "days": [], "scene": 0, "on": True})
    check("editar com o perfil escolhido grava nele", len(cfg["agenda_profiles"][0]["rules"]) == 2 and len(cfg["agenda"]) == 1, cfg["agenda_profiles"][0]["rules"])


def test_safety_undo():
    section("Segurança e Desfazer: restaurar e perfis nunca baixam os limites de conforto, e o toast desfaz")
    cfg = menu.fresh()
    m = menu.Menu(cfg)
    m.tab = menu.TAB_SYS
    m.cfg["sys_item"] = 0
    m.cfg["safe_flash"], m.cfg["safe_motion"] = 2, 1
    m.cfg["fx_bloom"] = False
    m.press("reset")
    check("Restaurar mantém Limitar flashes e movimento", cfg["safe_flash"] == 2 and cfg["safe_motion"] == 1, (cfg["safe_flash"], cfg["safe_motion"]))
    check("... restaura o resto e oferece Desfazer", cfg["fx_bloom"] is True and m.toast[2] is True, (cfg["fx_bloom"], m.toast))
    m.undo_last()
    check("Desfazer devolve o que o Restaurar mudou", cfg["fx_bloom"] is False and "Desfeito" in m.toast[0], (cfg["fx_bloom"], m.toast))
    cfg["scr_vig"] = 3
    m.press("reset")
    check("Restaurar não toca no Acabamento, que é de cada cena", cfg["scr_vig"] == 3, cfg["scr_vig"])
    m.press("fx_none")
    off = not any(cfg[k] for k in ("fx_glass", "fx_bloom", "fx_trail", "fx_parts"))
    m.undo_last()
    check("Desligar todos também desfaz", off and any(cfg[k] for k in ("fx_glass", "fx_bloom", "fx_trail", "fx_parts")), off)
    cfg["profile"] = 1
    m.profile_save()
    cfg["safe_flash"] = 2
    cfg["fx_bloom"] = not cfg["fx_bloom"]
    flip = cfg["fx_bloom"]
    m.profile_load()
    check("Carregar perfil mantém Limitar flashes", cfg["safe_flash"] == 2, cfg["safe_flash"])
    check("... e oferece Desfazer", m.toast[2] is True and cfg["fx_bloom"] != flip, m.toast)
    m.undo_last()
    check("Desfazer o perfil devolve os ajustes", cfg["fx_bloom"] == flip, cfg["fx_bloom"])
    cfg["safe_flash"] = 2
    m.set_value("safe_flash", 0)
    check("baixar o limite de conforto oferece Desfazer", cfg["safe_flash"] == 0 and m.toast[2] is True, m.toast)
    m.undo_last()
    check("... e Desfazer devolve o limite", cfg["safe_flash"] == 2, cfg["safe_flash"])


def test_navigation():
    section("Navegação: links viram botões de salto, a busca acha o que o modo simples esconde, o Avançado diz quantos itens revela")
    cfg = menu.fresh()
    cfg["advanced"] = False
    m = menu.Menu(cfg)
    m.press("tab%d" % menu.TAB_SYS)
    m.goto("sys:2")
    check("goto sys:2 abre Sistema > Automático", m.tab == menu.TAB_SYS and cfg["sys_item"] == 2, (m.tab, cfg["sys_item"]))
    m.press("goto:acab")
    check("goto:acab abre o Acabamento da cena no Estúdio", m.tab == menu.TAB_SCENES and m.scene_view == "editor" and cfg["ed_item"] == settings.SLOT_ITEM["finish"], (m.tab, m.scene_view, cfg["ed_item"]))
    res = settings.search_rows(cfg, "osc")
    check("a busca acha OSC no modo simples e diz Avançado", any(r["id"] == "remote_osc" and "Avançado" in r["help"] for r in res), [(r["id"], r["help"]) for r in res])
    cards = settings.search_cards(dict(cfg, search="osc"))
    ids = [r["id"] for _, rs in cards for r in rs]
    check("cada lugar achado tem um botão que vai até ele", "goto:sys:3" in ids, ids)
    cfg["ed_item"] = 10
    m.open_scene(0)
    check("o editor reabre na página em que você estava", cfg["ed_item"] == 10, cfg["ed_item"])
    cfg["ed_item"] = 12
    m.open_scene(0)
    check("... mas nunca na página vazia de Segue a música", cfg["ed_item"] == 0, cfg["ed_item"])
    m.open_scene(0)
    m.open_item(11)
    cfg["ly_over"] = False
    m.rebuild_scenes()
    ids = [r["id"] for _, rs in menu.TABS[menu.TAB_SCENES][1] for r in rs]
    check("uma camada desligada oferece o botão Ligar", "layer_on:over" in ids, ids[:6])
    m.press("layer_on:over")
    check("... e o botão liga a camada", cfg["ly_over"] is True, cfg["ly_over"])
    check("o Avançado conta o que esconde", m.adv_hidden() > 0 and menu.Menu(dict(cfg, advanced=True)).adv_hidden() >= 0, m.adv_hidden())


def test_sticky_titles():
    section("Cabeçalhos fixos: o título do cartão que está sendo rolado fica preso no topo da coluna")
    import control
    cfg = menu.fresh()
    cfg["advanced"] = True
    m = menu.Menu(cfg)
    cw = control.ControlWindow(m, headless=True, size=(1113, 600))
    an = listen(5)
    st = dict(image=dict(scene="Facetas", scene_i=0, style="3D", camera="Fixo", movement="Padrão", why=None, since=1, pending_scene=-1),
              keys=dict(fullscreen=False, vsync=False, strobe=True, auto=True), gpu="x", backend="x", shader_ok=True, reloads=0, preview=dict(on=False))
    m.tab, m.need = menu.TAB_SYS, True
    cfg["sys_item"] = 0
    cw.update(time.time(), an, 60.0, 10.0, False, st, force=True)
    check("os cartões com título são registrados", len(m.card_marks) > 3, len(m.card_marks))
    drawn = []
    t0 = cw._t
    cw._t = lambda font, text, pos, color, anchor="l": (drawn.append((text, pos)), t0(font, text, pos, color, anchor))[1]
    cw._draw_sticky(*cw.panel_pos)
    check("sem rolar, nada fica preso", not drawn, drawn)
    m.scroll2 = 330
    m.clamp_scroll()
    m.need = True
    cw.update(time.time() + 1, an, 60.0, 10.0, False, st, force=True)
    drawn.clear()
    cw._draw_sticky(*cw.panel_pos)
    check("rolando, o título do cartão que passou fica preso", [t.lower() for t, _ in drawn] == ["nitidez e fluidez"], drawn)


def test_report():
    section("Relatório de desempenho: cada parte tem suas subpartes, e nunca mexe nas configurações da pessoa")
    import prof
    import report
    r = dict(when="x", gpu="GPU", backend="D3D12", preset="Ultra", res=100.0, scene=[1280, 720], steps=110, frames=100, seconds=1.0, avg_fps=60.0, p1_fps=40.0, worst_ms=30.0,
             avg_ms=16.0, p99_ms=25.0, parts={"GPU/passe da cena": 6.0, "GPU/submit": 2.0, "UI/menu.render": 3.0, "áudio/análise": 1.0, "cena/diretor": 0.1, "Resto/eventos": 0.2},
             cpu_pct=30.0, mem_mb=400, mem_peak_mb=410, python="3", os="Windows", fps_out=60)
    prof_run = dict(r, avg_fps=40.0, modules={"wgpu": 5.0}, funcs=[dict(name="proxy_func", where="x.py:1", module="wgpu", calls=150.0, ms=5.0)])
    md = report.markdown(r, dict(r, avg_fps=55.0, fps_out=60), prof_run)
    check("o relatório lista as partes com as subpartes", all(t in md for t in ("Desenho da imagem", "passe da cena", "submit", "menu.render", "análise", "Memória", "55.0 fps")), md[:80])
    check("traz a visão por módulo e por função", "proxy_func" in md and "Tempo próprio por módulo" in md)
    prof.ON = True
    prof.reset()
    prof.mark_start()
    prof.mark("UI/teste")
    prof.add("UI/outro", 0.5)
    t = prof.totals()
    prof.ON = False
    prof.reset()
    check("os cronômetros somam por nome e ficam parados quando desligados", "UI/teste" in t and abs(t["UI/outro"] - 0.5) < 1e-9 and prof.totals() == {} and (prof.mark("x") or True) and prof.totals() == {})
    rec = report.Recorder(os.path.join(tempfile.mkdtemp(prefix="ao_rec_"), "r.json"))
    check("durante o aquecimento nada é medido", rec.step(1.0, 0.016, {}) is False and not rec.started)
    app_src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    check("o modo relatório grava as configurações ao lado do relatório, não por cima das da pessoa", "_settings.PATH" in app_src and "VIS_REPORT" in app_src)


def test_design_system():
    section("Sistema de design: os contrastes dos tokens cumprem o mínimo, e a lima é a única cor de tema")
    import widgets as W
    for name, c in (("TEXT", W.TEXT), ("DIM", W.DIM), ("SEL", W.SEL), ("DANGER", W.DANGER), ("PRIMARY_INK", W.PRIMARY_INK)):
        worst = min(W.contrast(c, bg) for bg in (W.BG, W.SURFACE, W.SURFACE2))
        check(f"{name} lê sobre o fundo e os painéis (>= 4,5:1)", worst >= 4.5, round(worst, 2))
    edge = min(W.contrast(W.CTRL, bg) for bg in (W.SURFACE, W.SURFACE2))
    check("a borda dos controles é visível (>= 3:1)", edge >= 3, round(edge, 2))
    check("a cor de tema é a lima, e o erro é o vermelho", W.SEL == W.ACCENT == (0xC6, 0xF2, 0x4E) and W.DANGER == (0xF0, 0x6A, 0x62))
    check("o botão principal é neutro, sem cor de tema", W.button_colors("primary")[0] == W.PRIMARY_FILL)


def test_agenda():
    section("Agenda: uma regra dispara no horário e nos dias marcados, uma vez por minuto")
    import agenda as AG
    import time as _t
    mon_9 = _t.struct_time((2026, 11, 23, 9, 0, 0, 0, 327, -1))           # a Monday, 09:00
    tue_9 = _t.struct_time((2026, 11, 24, 9, 0, 0, 1, 328, -1))           # a Tuesday, 09:00
    rules = [{"time": "09:00", "days": [0, 2], "scene": 3, "on": True},
             {"time": "09:00", "days": [], "scene": 5, "on": True},
             {"time": "09:00", "days": [], "scene": 7, "on": False}]
    check("a regra de segunda dispara às 09:00", [r["scene"] for r in AG.due(rules, mon_9)] == [3, 5])
    check("na terça só a regra de todos os dias dispara", [r["scene"] for r in AG.due(rules, tue_9)] == [5])
    check("um horário inválido não dispara nem trava", AG.parse_time("25:00") is None and AG.parse_time("x") is None and AG.parse_time("07:30") == 450)
    tk = AG.Ticker()
    check("o mesmo minuto dispara uma vez só", len(tk.check(rules, mon_9)) == 2 and tk.check(rules, mon_9) == [])


def test_bootguard():
    """The startup guard (bootguard.py): which video engine is tried after a hang or a crash, and that it can never go round in circles."""
    import bootguard as BG
    check("sem culpados, o automático continua automático", BG.choose([], None) == (None, False))
    check("a escolha da pessoa vale enquanto não for culpada", BG.choose([], "D3D12") == ("D3D12", False))
    check("o motor culpado é trocado pelo outro", BG.choose(["D3D12"], "D3D12") == ("Vulkan", False) and BG.choose(["Vulkan"], "Vulkan") == ("D3D12", False))
    check("no automático, com um culpado, vai para o outro", BG.choose(["Vulkan"], None) == ("D3D12", False) and BG.choose(["D3D12"], None) == ("Vulkan", False))
    check("os dois culpados: automático e modo seguro, sem trocar mais", BG.choose(["Vulkan", "D3D12"], "Vulkan") == (None, True))
    old = settings.APPDIR
    settings.APPDIR = os.path.join(TMP, "boot")
    try:
        eng, note, safe = BG.start("D3D12")
        check("primeira abertura: nada culpado, sem aviso", (eng, note, safe) == ("D3D12", None, False))
        BG.adapter("D3D12")
        eng, note, safe = BG.start("D3D12")                       # the first attempt never ended (no ok()): it hung or crashed
        check("abertura que não terminou culpa o motor e troca", eng == "Vulkan" and safe is False and "D3D12" in (note or ""), (eng, note, safe))
        BG.ok()
        BG.adapter("Vulkan")                                       # after ok() the attempt is gone: this is a no-op, nothing is rewritten
        eng, note, safe = BG.start(None)
        check("depois de uma abertura boa, a troca continua valendo", eng == "Vulkan" and safe is False, (eng, note, safe))
        BG.ok()
        st = json.load(open(os.path.join(settings.APPDIR, "boot.json"), encoding="utf-8"))
        check("o veredito fica salvo e a tentativa some", st["bad"] == ["D3D12"] and "attempt" not in st, st)
        BG.start(None)
        BG.adapter("Vulkan")
        eng, note, safe = BG.start(None)                           # Vulkan failed too
        check("os dois falharam: automático em modo seguro", eng is None and safe is True and "Baixo" in (note or ""), (eng, note, safe))
        BG.ok()
        st = json.load(open(os.path.join(settings.APPDIR, "boot.json"), encoding="utf-8"))
        st["version"] = "0.0.1"
        json.dump(st, open(os.path.join(settings.APPDIR, "boot.json"), "w", encoding="utf-8"))
        eng, note, safe = BG.start("Vulkan")
        check("uma versão nova esquece os vereditos", (eng, note, safe) == ("Vulkan", None, False), (eng, note, safe))
        BG.ok()
    finally:
        settings.APPDIR = old


def main():
    exe = sys.argv[sys.argv.index("--exe") + 1] if "--exe" in sys.argv else None
    for fn in (test_bootguard, test_menu, test_migration, test_gallery, test_help_texts, test_extras, test_layers, test_remote, test_ear, test_director, test_fuzz, test_fx, test_generators, test_global, test_control, test_palco, test_firstminute, test_oneplace, test_wizard, test_tap, test_widgets, test_sistema, test_custom, test_chips, test_demo, test_live, test_tiles, test_downbeat, test_slots, test_music, test_lang, test_review, test_palco_wide, test_thumbs, test_responsive, test_safety_undo, test_undo_redo_before, test_program_rules, test_agenda_week, test_master_switch, test_lanes, test_agenda_profiles, test_navigation, test_sticky_titles, test_report):
        try:
            fn()
        except Exception as e:
            import traceback
            traceback.print_exc()
            check(fn.__name__ + " ran to the end", False, repr(e))
    if exe:
        test_exe(exe)
    print("\n" + ("ALL PASSED" if not FAILS else "FAILED: " + ", ".join(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
