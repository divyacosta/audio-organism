"""Control window: live music monitor on the left, settings on the right.

The display window renders only the effect; everything else lives here.
"""
import os
import time

os.environ.setdefault("SDL_RENDER_DRIVER", "software")   # keep this window off the OpenGL context

import pygame

import ui

import types

import menu as M
import scenes as SC
from deck import DeckWindow


class ControlWindow:
    """One column: the tab bar on top (Ao vivo, Cenas, Câmera, ...) and the tab below. The Ao vivo tab is the deck (deck.py)."""
    PAD = 16

    def __init__(self, menu, pos=None, headless=False):
        self.menu = menu
        self.W = self.PAD * 2 + menu.W
        try:
            dh = pygame.display.get_desktop_sizes()[0][1]
        except Exception:
            dh = 1080
        self.view_h = min(menu.H, max(560, min(980, dh - 130)))          # as tall as the screen allows, the tab scrolls
        menu.view_h = self.view_h
        self.H = max(self.view_h, 600) + self.PAD * 2
        self.panel_pos = (self.PAD, self.PAD)
        self.surf = pygame.Surface((self.W, self.H))
        self.fb = pygame.font.SysFont("segoeui", 15, bold=True)
        self.fs = pygame.font.SysFont("segoeui", 13)
        self.fm = pygame.font.SysFont("segoeui", 20, bold=True)
        self.live = DeckWindow(headless=True)                          # used only to draw the Ao vivo tab
        self.live.surf = pygame.Surface((menu.W, 1500))
        self.last = -1.0
        self.now = 0.0
        self.interval = 0.05
        self.view = 2                      # (kept for older settings: the live tab always shows the equalizer and the deck)
        self.force = True
        self.preview = None                # the thumbnail of the picture (a pygame surface), set by the app
        self.thumbs = None                 # live thumbnails of the scene gallery (thumbs.Thumbs), set by the app
        self._tsurf = {}                   # id(scene) -> (frame counter, surface)
        self.gal_hits = []                 # (rect on the window, kind, argument) of the gallery, rebuilt at every draw
        self.gal_hover = None
        self.card_menu = -1                # the scene whose card menu is open
        self._masks = {}                   # cached overlays
        self._last_card, self._last_card_t = None, 0.0     # for the double click on a card
        self._menu_anchor = None
        self.preview_err = None
        self.gal_armed = 0.0               # the restore button asks twice
        self.del_armed = (-1, 0.0)         # (scene, until) the delete button of a card asks twice
        self.win = self.ren = self.tex = None
        if not headless:
            from pygame._sdl2 import video
            self.win = video.Window("Audio Organism - Controles", (self.W, self.H), position=pos)
            self.ren = video.Renderer(self.win)
            self.tex = video.Texture(self.ren, (self.W, self.H), streaming=True)
            self.id = self.win.id

    @staticmethod
    def _opaque(buf, size, fmt):
        """A pygame surface from the raw bytes the renderer read back (the alpha byte is not trusted: it is forced to opaque)."""
        img = pygame.image.frombuffer(buf, size, "BGRA" if str(fmt).startswith("bgra") else "RGBA").copy()
        pygame.surfarray.pixels_alpha(img)[:] = 255
        return img

    @staticmethod
    def _rounded(img, size, radius):
        """`img` scaled to `size` with rounded corners. No convert()/convert_alpha(): the app has no pygame display mode (its windows are SDL2 windows)."""
        out = pygame.Surface(size, pygame.SRCALPHA)
        out.blit(pygame.transform.smoothscale(img, size), (0, 0))
        mk = pygame.Surface(size, pygame.SRCALPHA)
        ui.rect(mk, (255, 255, 255, 255), (0, 0, size[0], size[1]), border_radius=radius)
        out.blit(mk, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return out

    def _t(self, font, text, pos, color, anchor="l"):
        img = font.render(text, True, color)
        x, y = pos
        if anchor == "r":
            x -= img.get_width()
        elif anchor == "c":
            x -= img.get_width() // 2
        self.surf.blit(img, (x, y))
        return img.get_width()

    # ---------------------------------------------------------------- input
    def handle(self, e):
        """Route an event from the control window; returns an action string or None."""
        if e.type == pygame.KEYDOWN:
            if self.menu.text_key(e):
                return None
            return self.menu.key(e.key, getattr(e, "mod", 0))
        mw = self.menu
        if e.type not in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL):
            return None
        if e.type == pygame.MOUSEBUTTONDOWN and getattr(e, "button", 0) == 6:           # the mouse's Back button: out of the scene editor / the picker
            if mw.tab == M.TAB_SCENES and mw.scene_view != "gallery":
                mw.back_to_gallery()
                self.force = True
            return None
        if e.type == pygame.MOUSEWHEEL:
            return mw.mouse(e, self.panel_pos[0], self.panel_pos[1], 1.0)
        ox, oy = self.panel_pos
        rel = e.pos[1] - oy
        if rel < mw.HEAD:
            surf_y = rel                                           # the tab bar: fixed
        elif rel < mw.HEAD + mw.reserved:
            return None                                            # the preview strip
        else:
            surf_y = rel - mw.reserved + mw.scroll                 # the content: scrolled
        if mw.in_gallery() and surf_y >= mw.HEAD and e.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            hit = next(((k, a) for r, k, a in reversed(self.gal_hits) if r.collidepoint(e.pos)), None)
            if e.type == pygame.MOUSEMOTION:
                if hit != self.gal_hover:
                    self.gal_hover = hit
                    self.force = True
            elif e.button == 1:
                if hit:
                    self._gallery_click(*hit)
                    self.force = True
                    return None
                if self.card_menu >= 0:                       # a click outside the card menu closes it
                    self.card_menu = -1
                    self.force = True
                    return None
        if mw.tab == M.TAB_LIVE and e.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            pos = (e.pos[0] - ox, surf_y - mw.HEAD)
            self.live.mouse = pos if surf_y >= mw.HEAD else None
            self.force = True
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and surf_y >= mw.HEAD and self.live.live_click((pos[0], pos[1])):
                return None
        elif mw.tab != M.TAB_LIVE:
            self.live.mouse = None
        ne = types.SimpleNamespace(type=e.type, pos=(e.pos[0], surf_y - mw.scroll + oy), button=getattr(e, "button", 0),
                                   buttons=getattr(e, "buttons", (0, 0, 0)))
        return mw.mouse(ne, ox, oy, 1.0)

    # ----------------------------------------------------------------- draw
    def draw(self, an, fps, lat, vsync, status=None):
        s = self.surf
        s.fill(M.BG)
        # tab bar (fixed), the preview strip, then the scrolling content, a scrollbar and the confirmation toast
        mw = self.menu
        tname = M.TABS[mw.tab][0]
        mw.reserved = (M.PV_H if (tname in M.PV_TABS and not mw.in_gallery()) else 0)
        mw.scroll = min(mw.scroll, mw.max_scroll())
        mw.render()
        px, py = self.panel_pos
        s.blit(mw.surf, (px, py), pygame.Rect(0, 0, mw.W, mw.HEAD))
        if mw.reserved:
            self._draw_preview(px, py + mw.HEAD, status)
        area = pygame.Rect(0, mw.HEAD + mw.scroll, mw.W, mw.content_h())
        s.blit(mw.surf, (px, py + mw.HEAD + mw.reserved), area)
        if mw.in_gallery():
            self._draw_gallery(status)
        if mw.tab == M.TAB_LIVE:
            self.live.blend = mw.cfg.get("wave_blend", 0)
            end = self.live.draw_live(an, fps, lat, vsync, status, (status or {}).get("genre", "?"), self.now)
            if end != mw.live_h:                                        # the content grew or shrank
                mw.live_h = end
                mw.heights[M.TAB_LIVE] = mw.HEAD + end + 8 + mw.FOOT
                mw.scroll = min(mw.scroll, mw.max_scroll())
                mw.need = True
            clip = s.get_clip()
            s.set_clip(pygame.Rect(px, py + mw.HEAD, mw.W, mw.content_h()))
            s.blit(self.live.surf, (px, py + mw.HEAD + mw.reserved - mw.scroll))
            s.set_clip(clip)
        if mw.max_scroll() > 0:
            top = py + mw.HEAD + mw.reserved
            ch = mw.content_h()
            tx = px + mw.W + 4
            th = max(40, int(ch * ch / max(1, mw.heights[mw.tab] - mw.HEAD)))
            ty = top + int((ch - th) * mw.scroll / mw.max_scroll())
            ui.rect(s, (46, 44, 84), (tx, top, 5, ch), border_radius=3)
            ui.rect(s, M.ACCENT2, (tx, ty, 5, th), border_radius=3)
        if mw.toast:
            txt = mw.toast[0]
            tw = self.fb.size(txt)[0] + 28
            r = pygame.Rect(self.panel_pos[0] + mw.W - tw, self.panel_pos[1] + 6, tw, 30)
            ui.rect(s, M.OK, r, border_radius=15)
            self._t(self.fb, txt, (r.centerx, r.y + 5), M.ON_ACCENT, "c")

    def set_preview(self, rgba, size, fmt):
        """Take the thumbnail bytes the renderer read back."""
        try:
            self.preview = self._opaque(rgba, size, fmt)
            self.preview_err = None
        except Exception as e:
            self.preview = None
            self.preview_err = repr(e)[:90]

    def _chip(self, x, y, text, color=None):
        img = self.fs.render(text, True, color or M.TEXT)
        r = pygame.Rect(x, y, img.get_width() + 18, 22)
        ui.rect(self.surf, M.SURFACE2, r, border_radius=11)
        ui.rect(self.surf, M.BORDER, r, width=1, border_radius=11)
        self.surf.blit(img, (x + 9, y + 3))
        return r.width + 6

    def _draw_preview(self, x, y, status):
        """The strip under the tab bar: a small picture of what the output shows right now, and what is being set up."""
        s = self.surf
        mw = self.menu
        pw, ph = 296, 166
        r = pygame.Rect(x, y + 6, pw, ph)
        ui.rect(s, (6, 5, 15), r, border_radius=10)
        if self.preview is not None:
            s.blit(self._rounded(self.preview, (pw, ph), 10), r.topleft)
        else:
            pv = (status or {}).get("preview") or {}
            why = ("preview desligado" if not pv.get("on", True) else (pv.get("err") or self.preview_err or ("aguardando o 1º quadro (%s)" % pv.get("n", 0)))) if pv else "preview…"
            self._t(self.fs, self._fit(self.fs, why, pw - 16), (r.centerx, r.centery - 8), M.DIM, "c")
        ui.rect(s, M.BORDER, r, width=1, border_radius=10)
        info = (status or {}).get("image") or {}
        cfg = mw.cfg
        scn = cfg.get("scenes") or []
        ed = scn[cfg["scene_edit"]]["scene_name"] if 0 <= cfg.get("scene_edit", 0) < len(scn) else "?"
        tx = x + pw + 16
        live_name = info.get("scene", "?")
        self._t(self.fm, live_name, (tx, y + 8), M.TEXT)
        self._t(self.fs, "na imagem agora" + ("  ·  automático" if cfg.get("effect", 0) == 0 else ""), (tx, y + 32), M.DIM)
        part = {"Cenas": "cena", "Gráficos": "qualidade"}.get(M.TABS[mw.tab][0], "")
        if M.TABS[mw.tab][0] == "Cenas":
            part = "seção: " + next((n for n, v in M.SEC_OPTS if v == cfg.get("scene_sec", 0)), "")
        self._t(self.fs, "EDITANDO", (tx, y + 62), M.ACCENT)
        self._t(self.fm, ed, (tx, y + 78), M.TEXT)
        self._t(self.fs, part, (tx, y + 102), M.DIM)
        cx, cy = tx, y + 130
        for txt in (f"{info.get('style', '--')}", f"Câmera {info.get('camera', '--')}", f"Movimento {info.get('movement', '--')}"):
            w = self.fs.size(txt)[0] + 18 + 6
            if cx + w > x + mw.W - 4:
                cx, cy = tx, cy + 26
            cx += self._chip(cx, cy, txt)

    # ------------------------------------------------------------- gallery of scenes
    COLS, GAP_G = 3, 12
    WHEN_OPTS = [(0, "Agora"), (1, "No compasso"), (2, "Na frase"), (3, "Pela música"), (4, "A cada N s")]
    WHEN_WHEN = {0: "agora", 1: "no próximo compasso", 2: "na próxima frase", 3: "no próximo evento da música", 4: "na próxima frase"}
    WHEN_PILL = {0: "ENTRANDO", 1: "NO COMPASSO", 2: "NA FRASE", 3: "NA MÚSICA", 4: "NA FRASE"}
    EVERY_OPTS = [15, 30, 60, 120]

    def _seg(self, x, y, opts, cur, kind, label_fn):
        """A row of choices drawn as one segmented control, each one a gallery hit."""
        s = self.surf
        widths = [max(52, self.fb.size(label_fn(v))[0] + 24) for v in opts]
        n = len(opts)
        for i, (v, w) in enumerate(zip(opts, widths)):
            r = pygame.Rect(x, y, w, 30)
            sel = cur == v
            hv = self.gal_hover == (kind, v)
            fill = M.ACCENT if sel else ((44, 42, 84) if hv else (34, 32, 66))
            rad = dict(border_top_left_radius=9 if i == 0 else 0, border_bottom_left_radius=9 if i == 0 else 0,
                       border_top_right_radius=9 if i == n - 1 else 0, border_bottom_right_radius=9 if i == n - 1 else 0)
            ui.rect(s, fill, r, **rad)
            ui.rect(s, M.BORDER, r, width=1, **rad)
            self._t(self.fb if sel else self.fs, label_fn(v), (r.centerx, r.y + 6), M.ON_ACCENT if sel else M.TEXT, "c")
            self.gal_hits.append((r, kind, v))
            x += w

    def _fit(self, font, text, w):
        if font.size(text)[0] <= w:
            return text
        while text and font.size(text + "…")[0] > w:
            text = text[:-1]
        return text + "…"

    def _tsurface(self, sc):
        """The live thumbnail of a scene as a pygame surface (None until the first frame arrives)."""
        th = self.thumbs
        if th is None or not th.ready:
            return None
        f = th.frames.get(id(sc))
        if f is None:
            return None
        cur = self._tsurf.get(id(sc))
        if cur is None or cur[0] != f[0]:
            try:
                img = self._opaque(f[1], th.size, th.fmt)
            except Exception:
                return cur[1] if cur else None
            cur = (f[0], img)
            self._tsurf[id(sc)] = cur
        return cur[1]

    def _gallery_click(self, kind, arg):
        mw = self.menu
        cfg = mw.cfg
        if kind == "mi-bg":
            return
        if kind not in ("mi", "menu"):
            self.card_menu = -1
        if kind == "menu":
            self.card_menu = -1 if self.card_menu == arg else arg
            self.del_armed = (-1, 0.0)
        elif kind == "mi":
            i, act = arg
            if act == "del":
                now = self.now or 0.0
                if self.del_armed[0] == i and self.del_armed[1] > now:
                    self.del_armed = (-1, 0.0)
                    self.card_menu = -1
                    mw.delete_scene(i)
                else:
                    self.del_armed = (i, now + 3.0)
                return
            self.card_menu = -1
            if act == "edit":
                mw.open_scene(i)
            elif act == "play":
                self._gallery_click("play", i)
            elif act == "dup":
                mw.duplicate_scene(i)
        elif kind == "open":                                           # a click pre-selects the scene to play; a double click opens its editor
            now = time.perf_counter()
            if self._last_card == (arg, ) and now - self._last_card_t < 0.45:
                self._last_card = None
                mw.open_scene(arg)
            else:
                self._last_card, self._last_card_t = (arg, ), now
                self._gallery_click("play", arg)
        elif kind == "edit":
            mw.open_scene(arg)
        elif kind == "auto":
            sc = cfg["scenes"][arg]
            sc["scene_auto"] = not sc.get("scene_auto", True)
            if arg == cfg.get("scene_edit"):
                cfg["scene_auto"] = sc["scene_auto"]
            mw.touch()
            mw.say(f"{sc['scene_name']}: " + ("entra no Auto" if sc["scene_auto"] else "fora do Auto"))
        elif kind == "when":
            cfg["scene_when"] = arg
            mw.touch()
            mw.say("Trocar de cena: " + dict(self.WHEN_OPTS)[arg])
        elif kind == "every":
            cfg["scene_every"] = arg
            mw.touch()
        elif kind == "play":                                          # bring this scene to the picture, at the moment "Trocar de cena" says
            cfg["effect"] = arg + 1
            cfg["scene_now"] = False
            mw.touch()
            mw.say(f"{cfg['scenes'][arg]['scene_name']}: entra " + self.WHEN_WHEN[int(cfg.get("scene_when", 2))])
        elif kind == "new":
            mw.scene_view = "picker"
            mw.scroll = 0
            mw.rebuild_scenes()
        elif kind == "cancel":
            mw.scene_view = "picker" if mw.scene_view == "preset" else "gallery"          # the preset step goes back to the models
            mw.scroll = 0
            mw.rebuild_scenes()
        elif kind == "pick":
            if mw.scene_view == "preset":
                mw.add_preset(arg)
            elif mw.templates[arg].get("scene_visual", 1) == 1:                          # Mandala: now the preset
                mw.scene_view = "preset"
                mw.scroll = 0
                mw.rebuild_scenes()
            else:
                mw.add_scene(arg)
        elif kind == "del":
            now = self.now or 0.0
            if self.del_armed[0] == arg and self.del_armed[1] > now:
                self.del_armed = (-1, 0.0)
                mw.delete_scene(arg)
            else:
                self.del_armed = (arg, now + 3.0)
                mw.say("Clique de novo em Apagar para confirmar")
        elif kind == "autoall":
            if cfg["effect"] != 0:
                cfg["effect"] = 0
            else:
                cfg["effect"] = int(getattr(self, "live_scene", 0)) + 1
            mw.touch()
            mw.say("Troca automática: " + ("ligada" if cfg["effect"] == 0 else "desligada (cena fixa)"))
        elif kind == "factory":
            now = self.now or 0.0
            if self.gal_armed > now:
                self.gal_armed = 0.0
                mw.press("scene_factory")
            else:
                self.gal_armed = now + 3.0

    def _pill(self, rect, text, fill, fg):
        ui.rect(self.surf, fill, rect, border_radius=rect.height // 2)
        self._t(self.fs, text, (rect.centerx, rect.y + (rect.height - self.fs.get_height()) // 2), fg, "c")

    def _toggle(self, x, y, on, dim, hov):
        """A small switch (36 x 20). `dim`: the Auto is off as a whole, so the choice of each scene is shown faded."""
        s = self.surf
        r = pygame.Rect(x, y, 36, 20)
        col = M.OK if on else (66, 64, 112)
        ui.rect(s, M.dimmed(col, 0.55) if dim else col, r, border_radius=10)
        ui.circle(s, M.dimmed((255, 255, 255), 0.7) if dim else (255, 255, 255), (r.right - 10 if on else r.left + 10, r.centery), 7)
        if hov:
            ui.rect(s, M.ACCENT2, r.inflate(4, 4), width=1, border_radius=12)
        return r

    def _draw_card(self, rect, sc, i, kind, status, live):
        s = self.surf
        mw = self.menu
        cfg = mw.cfg
        hov = self.gal_hover is not None and self.gal_hover[0] in ("open", "pick") and self.gal_hover[1] == i
        info = (status or {}).get("image", {})
        pending = kind == "open" and info.get("pending_scene", -1) == i
        fixed = kind == "open" and cfg["effect"] == i + 1
        off = kind == "open" and not sc.get("scene_auto", True)
        edge = M.ACCENT if live else (M.ACCENT2 if pending else (M.ACCENT2 if hov else M.BORDER))
        ui.rect(s, M.SURFACE2 if hov else M.SURFACE, rect, border_radius=14)
        ui.rect(s, edge, rect, width=2 if (live or pending or hov) else 1, border_radius=14)
        tw = rect.width - 8
        tr = pygame.Rect(rect.x + 4, rect.y + 4, tw, tw * 9 // 16)
        img = self._tsurface(sc)
        if sc.get("scene_visual", 1) == 0 and not sc.get("bg_light", 0):
            ui.rect(s, (0, 0, 0), tr, border_radius=10)
            self._t(self.fs, "tela preta", (tr.centerx, tr.centery - 8), M.DIM, "c")
        elif img is not None:
            s.blit(self._rounded(img, tr.size, 10), tr.topleft)
        else:
            ui.rect(s, (6, 5, 15), tr, border_radius=10)
            bad = self.thumbs is not None and not self.thumbs.ready and self.thumbs.error
            self._t(self.fs, "preview indisponível" if bad else "…", (tr.centerx, tr.centery - 8), M.DIM, "c")
        if off:                                                           # out of the Auto: the picture is faded
            sh = self._masks.get(("off", tr.size))
            if sh is None:
                sh = pygame.Surface(tr.size, pygame.SRCALPHA)
                ui.rect(sh, (10, 9, 22, 150), (0, 0, tr.w, tr.h), border_radius=10)
                self._masks[("off", tr.size)] = sh
            s.blit(sh, tr.topleft)
        ui.rect(s, M.BORDER, tr, width=1, border_radius=10)
        # state badge: what this scene is doing right now
        if kind == "open":
            if live:
                txt, col, fg = "NO AR" + ("  ·  FIXA" if fixed else ""), M.ACCENT, M.ON_ACCENT
            elif pending:
                txt, col, fg = self.WHEN_PILL.get(int(cfg.get("scene_when", 2)), ""), M.ACCENT2, M.ON_ACCENT
            elif fixed:
                txt, col, fg = "FIXA", M.ACCENT2, M.ON_ACCENT
            elif off:
                txt, col, fg = "FORA DO AUTO", (54, 52, 98), M.DIM
            else:
                txt = ""
            if txt:
                self._pill(pygame.Rect(tr.x + 6, tr.y + 6, self.fs.size(txt)[0] + 20, 20), txt, col, fg)
        # name, the Auto switch and what the scene is made of
        ny = tr.bottom + 8
        namew = rect.width - 20 - (52 if kind == "open" else 0)
        self._t(self.fb, self._fit(self.fb, sc["scene_name"], namew), (rect.x + 10, ny), M.TEXT)
        shs = cfg.get("shaders") or []
        sid = int(sc.get("scene_shader", 0))
        if sc.get("scene_visual", 1) == 0:
            sub = "Nenhum visual" + ("  ·  " + ("", "Aurora", "Feixes", "Pulsos")[int(sc.get("bg_light", 0)) % 4] if sc.get("bg_light", 0) else "")
        else:
            pn = SC.PRESET_NAMES[SC.preset_of(sc)]
            shn = "Shader auto" if sid == 0 or sid > len(shs) else shs[sid - 1]["name"]
            sub = shn if mw.scene_view == "preset" else ("Mandala" if pn == sc["scene_name"] else "Mandala " + pn) + "  ·  " + shn          # in the preset step "Mandala" is already said
        self._t(self.fs, self._fit(self.fs, sub, rect.width - 20), (rect.x + 10, ny + 22), M.DIM)
        self.gal_hits.append((rect, "open" if kind == "open" else "pick", i))          # the card first: the controls (added next) win where they overlap
        if kind != "open":
            return
        dim = cfg["effect"] != 0
        tg = self._toggle(rect.right - 10 - 36, ny - 1, sc.get("scene_auto", True), dim, self.gal_hover == ("auto", i))
        self.gal_hits.append((tg.inflate(10, 8), "auto", i))
        # the menu button (three dots) on the picture
        mb = pygame.Rect(tr.right - 32, tr.y + 6, 26, 26)
        mh = self.gal_hover == ("menu", i) or self.card_menu == i
        ui.rect(s, M.ACCENT2 if self.card_menu == i else (M.SURFACE2 if mh else (16, 14, 34)), mb, border_radius=13)
        ui.rect(s, M.ACCENT2 if mh else M.BORDER, mb, width=1, border_radius=13)
        for dx in (-6, 0, 6):
            ui.circle(s, M.ON_ACCENT if self.card_menu == i else M.TEXT, (mb.centerx + dx, mb.centery), 2)
        self.gal_hits.append((mb, "menu", i))
        if self.card_menu == i:
            self._menu_anchor = mb

    def _draw_card_menu(self):
        """The small menu of a card: Editar, Tocar agora, Duplicar, Apagar."""
        mw = self.menu
        i = self.card_menu
        if i < 0 or i >= len(mw.cfg["scenes"]) or getattr(self, "_menu_anchor", None) is None:
            return
        s = self.surf
        live = i == self.live_scene
        now = self.now or 0.0
        armed = self.del_armed[0] == i and self.del_armed[1] > now
        items = [("edit", "Editar", M.TEXT)]
        if not live:
            items.append(("play", "Tocar agora", M.TEXT))
        items.append(("dup", "Duplicar", M.TEXT))
        if len(mw.cfg["scenes"]) > 1:
            items.append(("del", "Apagar mesmo?" if armed else "Apagar", M.DANGER))
        a = self._menu_anchor
        w, rh = 156, 32
        pr = pygame.Rect(a.right - w, a.bottom + 4, w, rh * len(items) + 12)
        ui.rect(s, (0, 0, 0, 110), pr.move(0, 3), border_radius=12)
        ui.rect(s, (30, 28, 60), pr, border_radius=12)
        ui.rect(s, M.BORDER, pr, width=1, border_radius=12)
        self.gal_hits.append((pr, "mi-bg", i))                    # clicks on the menu's own background do nothing (and do not close it)
        for k, (act, label, col) in enumerate(items):
            ir = pygame.Rect(pr.x + 6, pr.y + 6 + k * rh, w - 12, rh - 2)
            hv = self.gal_hover == ("mi", (i, act))
            if hv:
                ui.rect(s, M.DANGER if (act == "del") else M.SURFACE2, ir, border_radius=8)
            self._t(self.fb if (act == "del" and armed) else self.fs, label, (ir.x + 12, ir.y + 6), M.ON_ACCENT if (hv and act == "del") else col)
            self.gal_hits.append((ir, "mi", (i, act)))

    def _draw_gallery(self, status):
        """The Cenas tab, gallery and picker: a card per scene, each with a live thumbnail drawn at a very low resolution."""
        s = self.surf
        mw = self.menu
        cfg = mw.cfg
        picker = mw.scene_view in ("picker", "preset")
        px, py = self.panel_pos
        top = py + mw.HEAD
        clip = s.get_clip()
        s.set_clip(pygame.Rect(px - 4, top, mw.W + 8, mw.content_h()))
        self.gal_hits = []
        y = top - mw.scroll
        info = (status or {}).get("image") or {}
        self.live_scene = info.get("scene_i", 0)
        items = (mw.preset_templates if mw.scene_view == "preset" else (mw.templates if picker else cfg["scenes"]))
        if self.thumbs is not None:
            self.thumbs.show(items)
        # header
        if picker:
            self._t(self.fm, "Escolha o preset da mandala" if mw.scene_view == "preset" else "Escolha um modelo", (px, y + 8), M.TEXT)
            br = pygame.Rect(px + mw.W - 110, y + 6, 110, 30)
            hv = self.gal_hover == ("cancel", 0)
            ui.rect(s, M.SURFACE2 if hv else M.SURFACE, br, border_radius=10)
            ui.rect(s, M.ACCENT2 if hv else M.BORDER, br, width=1, border_radius=10)
            self._t(self.fb, "‹ Voltar" if mw.scene_view == "preset" else "Cancelar", (br.centerx, br.y + 5), M.ACCENT2, "c")
            self.gal_hits.append((br, "cancel", 0))
            self._t(self.fs, "Os números do preset viram da cena: depois é só ajustar" if mw.scene_view == "preset" else "A cena entra na galeria e abre para você configurar", (px, y + 34), M.DIM)
        else:
            self._t(self.fm, "Cenas no ar", (px, y + 8), M.TEXT)
            n_auto = sum(1 for sc_ in items if sc_.get("scene_auto", True))
            self._t(self.fs, f"{n_auto} de {len(items)} cenas no Auto  ·  clique para tocar, duplo clique para editar", (px, y + 34), M.DIM)
            auto = cfg["effect"] == 0
            lab = "Troca automática"
            lw = self.fb.size(lab)[0]
            pill = pygame.Rect(px + mw.W - 46, y + 12, 46, 26)
            col = M.OK if auto else (66, 64, 112)
            ui.rect(s, col, pill, border_radius=13)
            ui.circle(s, (255, 255, 255), (pill.right - 13 if auto else pill.left + 13, pill.centery), 9)
            self._t(self.fb, lab, (pill.left - 12, y + 15), M.TEXT, "r")
            self.gal_hits.append((pygame.Rect(pill.left - lw - 16, y + 6, lw + 16 + 46, 38), "autoall", 0))
        y += 56
        if not picker:
            self._t(self.fs, "Trocar de cena", (px, y + 6), M.DIM)
            self._seg(px + 118, y, [v for v, _ in self.WHEN_OPTS], int(cfg.get("scene_when", 2)), "when", lambda v: dict(self.WHEN_OPTS)[v])
            y += 40
            if int(cfg.get("scene_when", 2)) == 4:
                self._t(self.fs, "A cada", (px, y + 6), M.DIM)
                self._seg(px + 118, y, self.EVERY_OPTS, int(cfg.get("scene_every", 30)), "every", lambda v: f"{v} s")
                y += 40
        cw = (mw.W - self.GAP_G * (self.COLS - 1)) // self.COLS
        ch = (cw - 8) * 9 // 16 + 4 + 8 + 22 + 22 + 14
        n = len(items) + (0 if picker else 1)
        live_i = self.live_scene
        for k in range(n):
            r = pygame.Rect(px + (k % self.COLS) * (cw + self.GAP_G), y + (k // self.COLS) * (ch + self.GAP_G), cw, ch)
            if r.bottom < top or r.top > top + mw.content_h():
                if k < len(items):
                    self.gal_hits.append((r, "pick" if picker else "open", k))
                else:
                    self.gal_hits.append((r, "new", 0))
                continue
            if k < len(items):
                self._draw_card(r, items[k], k, "pick" if picker else "open", status, (not picker) and k == live_i)
            else:
                hv = self.gal_hover == ("new", 0)
                ui.rect(s, M.SURFACE2 if hv else M.SURFACE, r, border_radius=12)
                ui.rect(s, M.ACCENT2 if hv else M.BORDER, r, width=2 if hv else 1, border_radius=12)
                self._t(self.fm, "+", (r.centerx, r.centery - 28), M.ACCENT2, "c")
                self._t(self.fb, "Nova cena", (r.centerx, r.centery + 4), M.TEXT, "c")
                self._t(self.fs, "escolha um modelo", (r.centerx, r.centery + 26), M.DIM, "c")
                self.gal_hits.append((r, "new", 0))
        rows = (n + self.COLS - 1) // self.COLS
        end = y + rows * (ch + self.GAP_G)
        if not picker:
            self._draw_card_menu()                            # on top of the cards
        if not picker:
            fr = pygame.Rect(px, end + 4, 250, 34)
            armed = self.gal_armed > self.now
            hv = self.gal_hover == ("factory", 0)
            ui.rect(s, M.DANGER if armed else (M.SURFACE2 if hv else M.SURFACE), fr, border_radius=10)
            ui.rect(s, M.DANGER if (armed or hv) else M.BORDER, fr, width=1, border_radius=10)
            self._t(self.fs, "Confirmar? Apaga suas cenas" if armed else "Restaurar cenas de fábrica", (fr.centerx, fr.y + 8), M.ON_ACCENT if armed else M.DIM, "c")
            self.gal_hits.append((fr, "factory", 0))
            end += 44
        s.set_clip(clip)
        mw.set_gal_h(end + mw.scroll - top + 8)

    def update(self, now, an, fps, lat, vsync, status=None, force=False):
        iv = min(self.interval, 1.0 / 30.0) if (self.menu.tab == M.TAB_LIVE or self.menu.in_gallery()) else self.interval          # the beat blink needs a smooth refresh
        if not (force or self.force or self.menu.need or now - self.last >= iv):
            return
        self.last = now
        self.now = now
        self.force = False
        self.draw(an, fps, lat, vsync, status)
        if self.win is not None:
            self.tex.update(self.surf)
            self.ren.clear()
            self.tex.draw()
            self.ren.present()

    def destroy(self):
        try:
            if self.win is not None:
                self.win.destroy()
        except Exception:
            pass
