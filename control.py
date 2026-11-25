"""Control window: live music monitor on the left, settings on the right.

The display window renders only the effect; everything else lives here.
"""
import math
import os
import time

os.environ.setdefault("SDL_RENDER_DRIVER", "software")   # keep this window off the OpenGL context

import prof
import pygame

import ui
import widgets as wg

import types

import layers as LY
import menu as M
import scenes as SC
from deck import DeckWindow




class ControlWindow:
    """One column: the tab bar on top (Ao vivo, Cenas, Câmera, ...) and the tab below. The Ao vivo tab is the deck (deck.py)."""
    PAD = 16
    MIN_W, MIN_H = 620, 560
    LIVE_SURF_H = 2400                 # the surface the Palco is drawn on: tall enough for the strip of scenes (up to 48 of them) with the details open
    STRIP_MAX = 48                     # the scenes of the strip of the Palco (a new scene goes to the end: past this one it is only in the Estúdio and in Automático)

    HEAD_ROW = 64                      # the one row over the editor: back, name, state and the buttons (it was a strip of 190 px)

    def pv_size(self):
        """The preview under the tab bar: 296 px wide in a narrow window, bigger (up to 500 px) in a wide one; always 16:9."""
        pw = max(296, min(420, int(self.menu.W * 0.33)))
        if self.menu.pv_mode() == "draft":                        # editing: the picture is a reference, the tabs and the controls get the room
            pw = max(240, min(340, int(self.menu.W * 0.24)))
        if self.menu.pv_mode() == "live":                         # Sistema > Imagem: the picture is a check on the settings, not the star: the settings get the height
            pw = max(240, min(pw, 264))
        if self.menu.wide:                                        # in two columns the strip must leave room for them: at most ~30% of the window's height
            pw = max(296, min(pw, int((self.view_h - self.menu.HEAD) * 0.30 * 16 / 9)))
        return pw, pw * 9 // 16

    def resize(self, w, h):
        """The window has a new size (the user dragged it, or maximised it): the panel takes the whole width and the layout adapts (menu.set_width)."""
        w, h = max(self.MIN_W, int(w)), max(self.MIN_H, int(h))
        if (w, h) == (self.W, self.H) and self.surf.get_size() == (w, h):
            return
        mw = self.menu
        self.W, self.H = w, h
        self.view_h = h - self.PAD * 2
        mw.view_h = self.view_h
        mw.set_width(w - self.PAD * 2)
        self.surf = pygame.Surface((w, h))
        self.live.surf = pygame.Surface((mw.W, self.LIVE_SURF_H))
        if self.win is not None:
            from pygame._sdl2 import video
            self.tex = video.Texture(self.ren, (w, h), streaming=True)
        mw.clamp_scroll()
        self.force = True
        mw.need = True

    @classmethod
    def default_size(cls, dw, dh):
        """The window of a first run: wide enough for the Palco in two columns (the picture beside its buttons, the scenes right under them) and as tall as the
        screen allows. Never wider than the screen."""
        w = min(max(M.WIDE_MIN + cls.PAD * 2 + 40, min(1120, int(dw * 0.58))), dw - 40)
        h = min(860, dh - 120)
        return max(cls.MIN_W, w), max(cls.MIN_H, h)

    def __init__(self, menu, pos=None, headless=False, size=None):
        self.menu = menu
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except Exception:
            dw, dh = 1920, 1080
        if size is None and not headless:                                   # the real program opens wide; the headless window of the tests keeps the old size
            size = self.default_size(dw, dh)
        if size is not None:
            menu.set_width(size[0] - self.PAD * 2)
        self.W = self.PAD * 2 + menu.W
        self.view_h = min(menu.H, max(560, min(980, dh - 130)))          # as tall as the screen allows, the tab scrolls
        if size is not None:
            self.view_h = size[1] - self.PAD * 2
        menu.view_h = self.view_h
        self.H = size[1] if size is not None else max(self.view_h, 600) + self.PAD * 2
        self.panel_pos = (self.PAD, self.PAD)
        self.surf = pygame.Surface((self.W, self.H))
        self.fb = wg.font("body", True)
        self.fs = wg.font("small")
        self.fm = wg.font("lead", True)                               # the scene name: the title size (lead), the same as the other titles of the panel
        self.live = DeckWindow(headless=True)                          # used only to draw the Ao vivo tab
        self.live.ear_open = bool(menu.cfg.get("ear_open", True))
        self.live.tour_open = not menu.cfg.get("tour_done", False)
        self.live.detail_open = bool(menu.cfg.get("detail_open", False))
        self.live.cfg = menu.cfg                                       # the Palco shows the three big controls from the settings
        self.live.tour_cb = menu.tour_mark                            # the steps of the first-use card tick themselves
        self.live.tour_close = self.close_tour
        self.live.preview_cb = self._palco_preview
        self.live.strip_cb = lambda surf, y, Wc, hits: self._live_strip(surf, y, Wc, hits, self._last_status)
        self.live.next_cb = self._next_thumb
        self._last_status = None
        self.live.surf = pygame.Surface((menu.W, self.LIVE_SURF_H))
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
        self._menu_anchor = None
        self.preview_err = None
        self.gal_armed = 0.0               # the restore button asks twice
        self.del_armed = (-1, 0.0)         # (scene, until) the delete button of a card asks twice
        self.win = self.ren = self.tex = None
        if not headless:
            from pygame._sdl2 import video
            self.win = video.Window("Audio Organism - Controles", (self.W, self.H), position=pos, resizable=True)       # it can be resized and maximised: the panel follows
            try:
                self.win.minimum_size = (self.MIN_W, self.MIN_H)
            except Exception:
                pass
            self.ren = video.Renderer(self.win)
            self.tex = video.Texture(self.ren, (self.W, self.H), streaming=True)
            self.id = self.win.id

    def close_tour(self):
        """The first-use card goes away for good (skipped, or all three steps done)."""
        self.live.tour_open = False
        self.menu.cfg["tour_done"] = True
        self.menu.touch()

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
        mx = pygame.mouse.get_pos()[0]                                        # a wheel event has no position: where the pointer is decides
        if e.type == pygame.MOUSEWHEEL and self.menu.side_on() and self.panel_pos[0] <= mx <= self.panel_pos[0] + self.menu.side_w():
            self.side_scroll = max(0, getattr(self, "side_scroll", 0) - e.y * 40)
            self.force = True
            return None
        if e.type == pygame.MOUSEBUTTONDOWN and getattr(e, "button", 0) == 1 and self.menu.side_on():
            hit = next((i for r, i in getattr(self, "side_hits", []) if r.collidepoint(e.pos)), None)
            if hit is not None:
                self.menu.switch_scene(hit)                                # the list of scenes: open that scene (a scene with changes asks first)
                self.force = True
                return None
        if e.type == pygame.KEYDOWN:
            if self.menu.wizard is not None and self.menu.tab == M.TAB_SCENES and self.menu.wizard_key(e):       # the three steps of a new scene own the keyboard
                self.force = True
                return None
            if self.menu.text_key(e):
                return None
            if e.key == pygame.K_z and getattr(e, "mod", 0) & pygame.KMOD_CTRL:
                self.menu.undo_last()
                return None
            if e.key == pygame.K_s and getattr(e, "mod", 0) & pygame.KMOD_CTRL and self.menu.scene_view == "editor":
                self.menu.save_scene()                                 # Ctrl+S saves the scene being edited
                self.force = True
                return None
            if e.key in (pygame.K_f, pygame.K_k) and getattr(e, "mod", 0) & pygame.KMOD_CTRL:
                self.menu.open_search()
                self.force = True
                return None
            if self.menu.shortcut(getattr(e, "unicode", ""), int(getattr(self, "live_scene", 0))):
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
        if (e.type == pygame.MOUSEBUTTONDOWN and getattr(e, "button", 0) == 1 and mw.toast and len(mw.toast) > 2 and mw.toast[2]
                and getattr(self, "_toast_btn", None) is not None and self._toast_btn.collidepoint(e.pos)):
            mw.undo_last()                                         # the Desfazer of the toast
            self.force = True
            return None
        ox, oy = self.panel_pos
        rel = e.pos[1] - oy
        if rel < mw.HEAD:
            surf_y = rel                                           # the tab bar: fixed
        elif rel < mw.HEAD + mw.reserved:
            if e.type == pygame.MOUSEBUTTONDOWN and getattr(e, "button", 0) == 1:
                hit = next((cid for r, cid in getattr(self, "bar_hits", []) if r.collidepoint(e.pos)), None)
                if hit and mw.pv_mode() == "draft":
                    mw.press(hit)                                  # a button of the editor, drawn in the strip
                    self.force = True
            return None                                            # the preview strip
        else:
            surf_y = mw.surf_y_at(e.pos[0] - ox, rel - mw.reserved)         # the content: scrolled (in two columns each one by its own)
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
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and surf_y >= mw.HEAD:
                bid = self.live.live_click((pos[0], pos[1]))
                if bid:
                    if str(bid).startswith("scene:"):                                  # a scene of the strip of the Ao vivo tab (it also ticks step 2 of the first-use card)
                        mw.play_scene(int(str(bid)[6:]))
                        return None
                    if bid == "bpm:tap":                                               # the BPM of the Detalhes: tap the beat (the same as the T key)
                        mw.request_tap()
                        return None
                    if bid == "bpm:auto":                                              # ... and give the tempo back to the program
                        mw.tap_release = True
                        mw.need = True
                        return None
                    if bid == "wiz:start":                                             # the "+ Nova cena" tile at the end of the scenes
                        mw.start_wizard()
                        return None
                    if bid == "next:now":                                              # the scene that waits for its moment comes in at once
                        mw.cfg["scene_now"] = True
                        mw.touch()
                        return None
                    if bid == "ear:open":                                              # what the program hears, in detail: Sistema > Áudio
                        mw.open_sys(1)
                        return None
                    if bid == "edit:live":                                             # "Editar esta cena": the Estúdio opens on the scene on the air
                        mw.edit_live_scene()
                        return None
                    if str(bid).startswith("fix:"):                                    # the button of a warning of the Palco: it does what the warning says
                        mw.fix(str(bid)[4:])
                        self.live._quiet_since = self.live._slow_since = None          # the warning starts counting again
                        return None
                    if str(bid).startswith("macro:"):                                  # Intensidade, Velocidade, Cores of the Palco
                        _, kind, idx = str(bid).split(":")
                        mw.set_macro(kind, int(idx))
                        return None
                    if bid == "auto:toggle":
                        mw.toggle_auto()
                        return None
                    if bid == "auto:settings":                                         # Opções, next to Troca automática: which scenes the automatic change may bring, and when
                        mw.open_sys(2)
                        return None
                    if bid == "detail:toggle":                                         # the details of the music and of the program
                        self.live.detail_open = not self.live.detail_open
                        mw.cfg["detail_open"] = self.live.detail_open
                        mw.touch()
                        return None
                    if bid == "tour:close":                                            # the first-use card is closed (skipped, or done): it does not come back
                        self.close_tour()
                        return None
                    if bid == "ear:toggle":                                            # the analysis card opens and closes
                        self.live.ear_open = not self.live.ear_open
                        mw.cfg["ear_open"] = self.live.ear_open
                        self.live._ear_cache = None
                        mw.touch()
                        return None
                    return bid if str(bid).startswith("key:") else None             # a shortcut button: the program sends the key to the picture
        elif mw.tab != M.TAB_LIVE:
            self.live.mouse = None
        ne = types.SimpleNamespace(type=e.type, pos=(e.pos[0], surf_y - mw.scroll + oy), button=getattr(e, "button", 0),
                                   buttons=getattr(e, "buttons", (0, 0, 0)))
        return mw.mouse(ne, ox, oy, 1.0)

    # ----------------------------------------------------------------- draw
    def draw(self, an, fps, lat, vsync, status=None):
        self._last_status = status
        s = self.surf
        s.fill(wg.BG)
        # tab bar (fixed), the preview strip, then the scrolling content, a scrollbar and the confirmation toast
        mw = self.menu
        info = (status or {}).get("image") or {}
        li, pi = int(info.get("scene_i", 0)), int(info.get("pending_scene", -1))
        if (li, pi) != (mw.live_i, mw.pend_i):                         # the list of scenes says which one is on the air and which one waits
            mw.live_i, mw.pend_i = li, pi
            mw.need = True
        mw.live_scene = self.live_scene = li
        mw.reserved = (self.HEAD_ROW if mw.pv_mode() == "draft" else (self.pv_size()[1] + 18 if mw.pv_mode() else 0))
        mw.clamp_scroll()
        prof.mark_start()
        mw.render()
        prof.mark("UI/painel: desenhar linhas e cartões (menu.render)")
        px, py = self.panel_pos
        s.blit(mw.surf, (px, py), pygame.Rect(0, 0, mw.W, mw.HEAD))
        if mw.reserved:
            self._draw_preview(px, py + mw.HEAD, status)
        prof.mark("UI/faixa de cima (prévia e botões)")
        if mw.panes():                                                  # two columns, each one scrolling on its own under what stays fixed (the bar of the editor)
            fixed, _, _ = mw.pane_dims()
            wl, wr, gap = mw._col_widths()
            top = py + mw.HEAD + mw.reserved
            ph = mw.pane_view_h()
            if fixed:
                s.blit(mw.surf, (px, top), pygame.Rect(0, mw.HEAD, mw.W, fixed))
            sd = mw.side_w()
            s.blit(mw.surf, (px + sd, top + fixed), pygame.Rect(sd, mw.HEAD + fixed + mw.scroll, wl, ph))
            s.blit(mw.surf, (px + sd + wl + gap, top + fixed), pygame.Rect(sd + wl + gap, mw.HEAD + fixed + mw.scroll2, wr, ph))
        else:
            area = pygame.Rect(0, mw.HEAD + mw.scroll, mw.W, mw.content_h())
            s.blit(mw.surf, (px, py + mw.HEAD + mw.reserved), area)
        prof.mark("UI/conteúdo e rolagem (cópia para a janela)")
        self._draw_sticky(px, py)
        self._draw_float_pic()
        if mw.tab == M.TAB_SYS and getattr(mw, "ear_slots", None):
            self._draw_ear(an)
        if mw.in_gallery():
            self._draw_gallery(status)
        elif mw.tab == M.TAB_SCENES:
            self._draw_scene_thumbs()
        if mw.tab == M.TAB_LIVE:
            self.live.tap_t = mw.tap_t
            end = self.live.draw_live(an, fps, lat, vsync, status, (status or {}).get("genre", "?"), self.now)
            if end != mw.live_h:                                        # the content grew or shrank
                mw.live_h = end
                mw.heights[M.TAB_LIVE] = mw.HEAD + end + 8 + mw.FOOT
                mw.clamp_scroll()
                mw.need = True
            clip = s.get_clip()
            s.set_clip(pygame.Rect(px, py + mw.HEAD, mw.W, mw.content_h()))
            s.blit(self.live.surf, (px, py + mw.HEAD + mw.reserved - mw.scroll))
            s.set_clip(clip)
        if mw.panes():
            fixed, hl, hr = mw.pane_dims()
            wl, wr, gap = mw._col_widths()
            for pane, (hh, sc, tx) in enumerate(((hl, mw.scroll, px + mw.side_w() + wl + 3), (hr, mw.scroll2, px + mw.W + 4))):
                if mw.max_scroll(pane) > 0:
                    top = py + mw.HEAD + mw.reserved + fixed
                    ch = mw.pane_view_h()
                    th = max(40, int(ch * ch / max(1, hh)))
                    ty = top + int((ch - th) * sc / mw.max_scroll(pane))
                    ui.rect(s, (36, 40, 58), (tx, top, 5, ch), border_radius=3)
                    ui.rect(s, wg.ACCENT2, (tx, ty, 5, th), border_radius=3)
        elif mw.max_scroll() > 0:
            top = py + mw.HEAD + mw.reserved
            ch = mw.content_h()
            tx = px + mw.W + 4
            th = max(40, int(ch * ch / max(1, mw.heights[mw.tab] - mw.HEAD)))
            ty = top + int((ch - th) * mw.scroll / mw.max_scroll())
            ui.rect(s, (36, 40, 58), (tx, top, 5, ch), border_radius=3)
            ui.rect(s, wg.ACCENT2, (tx, ty, 5, th), border_radius=3)
        self._draw_scene_bar(px, py + mw.HEAD + mw.reserved)
        if mw.problems:
            txt = " · ".join(mw.problems.values())
            while len(txt) > 8 and self.fs.size(txt)[0] > mw.W - 40:
                txt = txt[:-2]
            r = pygame.Rect(self.panel_pos[0] + 8, self.panel_pos[1] + mw.HEAD + mw.reserved - 28, mw.W - 16, 24)
            ui.rect(s, (150, 30, 50), r, border_radius=12)
            self._t(self.fs, txt, (r.centerx, r.y + 4), (255, 255, 255), "c")
        if mw.toast:                                                    # at the bottom, centred: at the top it covered the tabs
            txt = mw.toast[0]
            while len(txt) > 8 and self.fb.size(txt)[0] + 28 > self.W - 32:
                txt = txt[:-2]
            can_undo = len(mw.toast) > 2 and mw.toast[2]
            btn_w = self.fb.size("Desfazer")[0] + 22 if can_undo else 0
            r = self.toast_rect(self.fb.size(txt)[0] + 28 + btn_w)
            ui.rect(s, wg.OK, r, border_radius=15)
            self._toast_btn = None
            if can_undo:
                self._t(self.fb, txt, (r.x + 14 + self.fb.size(txt)[0] // 2, r.y + 5), wg.ON_LIGHT, "c")
                b = pygame.Rect(r.right - btn_w - 4, r.y + 4, btn_w, r.h - 8)
                ui.rect(s, wg.ON_LIGHT, b, border_radius=11)
                self._t(self.fb, "Desfazer", (b.centerx, b.y + 2), wg.OK, "c")
                self._toast_btn = b
            else:
                self._t(self.fb, txt, (r.centerx, r.y + 5), wg.ON_LIGHT, "c")

    STICKY_H = 30

    def _draw_sticky(self, px, py):
        """The title of the card that is being scrolled past stays pinned at the top of its column, so a long page never loses where you are."""
        mw = self.menu
        if mw.tab == M.TAB_LIVE or mw.in_gallery() or not getattr(mw, "card_marks", None):
            return
        s = self.surf
        base = py + mw.HEAD + mw.reserved
        if mw.panes():
            fixed, _, _ = mw.pane_dims()
            wl, wr, gap = mw._col_widths()
            panes = ((0, mw.scroll), (wl + gap, mw.scroll2))
            top, view = base + fixed, mw.HEAD + fixed
        else:
            panes = ((0, mw.scroll),)
            top, view = base, mw.HEAD
        for pane, (x_from, sc) in enumerate(panes):
            edge = view + sc                                               # the surface row at the top of the visible part
            if sc <= 0:
                continue
            x_to = panes[pane + 1][0] if pane + 1 < len(panes) else 10 ** 6
            for x0, y, ch, wc, title in mw.card_marks:
                if x_from <= x0 < x_to and y >= view and y + 14 < edge and y + ch - self.STICKY_H > edge:
                    r = pygame.Rect(px + x0 + 1, top, wc - 2, self.STICKY_H)
                    ui.rect(s, wg.SURFACE2, r, border_radius=8)
                    ui.rect(s, wg.BORDER, pygame.Rect(r.x, r.bottom - 2, r.w, 2))
                    self._t(mw.f_sb, title, (r.x + 17, r.y + 7), wg.TITLE)
                    break

    def _draw_scene_bar(self, px, y):
        """The list of scenes on the left of the wide editor: a fixed bar (it does not scroll with the page). A click opens that scene."""
        mw = self.menu
        self.side_hits = []
        if not mw.side_on():
            return
        s, cfg = self.surf, mw.cfg
        w, h = mw.side_w(), mw.content_h()
        ui.rect(s, wg.SURFACE, (px, y, w, h))
        ui.rect(s, wg.BORDER, (px + w - 1, y, 1, h))
        self._t(wg.font("cap", True), "CENAS", (px + 12, y + 10), wg.TITLE)
        top = y + 32
        total = len(cfg.get("scenes") or []) * 62
        self.side_scroll = max(0, min(getattr(self, "side_scroll", 0), total - (h - 32)))     # the list scrolls with the wheel over it
        old_clip = s.get_clip()
        s.set_clip(pygame.Rect(px, top, w, h - 32))
        yy = top - self.side_scroll
        for i, sc in enumerate(cfg.get("scenes") or []):
            r = pygame.Rect(px + 8, yy, w - 16, 56)
            cur = i == int(cfg.get("scene_edit", 0))
            ui.rect(s, wg.ACCENT_DIM if cur else wg.SURFACE2, r, border_radius=8)
            if cur:
                ui.rect(s, wg.SEL, (r.x, r.y + 8, 3, r.h - 16), border_radius=2)
            name = sc.get("scene_name", "?")
            self._t(wg.font("label"), wg.fit(wg.font("label"), name, r.w - 70), (r.x + 12, r.y + 8), wg.TEXT if cur else wg.DIM)
            self._t(wg.font("small"), wg.fit(wg.font("small"), M.settings.scene_sub(cfg, sc), r.w - 24), (r.x + 12, r.y + 30), wg.DIM)
            if i == getattr(self, "live_scene", -1):
                self._pill(pygame.Rect(r.right - 60, r.y + 8, 52, 18), "NO AR", wg.ACCENT, wg.ON_ACCENT)
            if top <= r.y and r.bottom <= y + h:
                self.side_hits.append((r, i))
            yy += 62
        s.set_clip(old_clip)

    def toast_rect(self, tw):
        """Where the confirmation toast goes: centred near the bottom of the window, never over the tabs."""
        return pygame.Rect((self.W - tw) // 2, self.H - 46, tw, 30)

    def _palco_preview(self, surf, rect):
        """The live picture inside the Palco (the deck asks for it)."""
        if self.preview is not None:
            surf.blit(self._rounded(self.preview, rect.size, 12), rect.topleft)
        else:
            img = self.fs.render("preparando a imagem…", True, wg.DIM)
            surf.blit(img, (rect.centerx - img.get_width() // 2, rect.centery - 8))
        if self.menu.cfg.get("safe_flash"):                             # the comfort limit is on: the Palco says so, where the picture is
            self._pill_on(surf, pygame.Rect(rect.x + 10, rect.y + 10, 150, 20), "FLASHES LIMITADOS", wg.ACCENT2, wg.ON_LIGHT)

    def set_preview(self, rgba, size, fmt):
        """Take the thumbnail bytes the renderer read back."""
        try:
            self.preview = self._opaque(rgba, size, fmt)
            self.preview_err = None
        except Exception as e:
            self.preview = None
            self.preview_err = repr(e)[:90]

    def _chip(self, x, y, text, color=None):
        return wg.chip(self.surf, self.fs, x, y, text, color, pad=9, dy=1) + 6

    def _draw_preview(self, x, y, status):
        """The strip under the tab bar: a small picture of what the output shows right now, and what is being set up."""
        s = self.surf
        mw = self.menu
        if mw.pv_mode() == "draft":
            return self._draw_editor_head(x, y, status)
        pw, ph = self.pv_size()
        r = pygame.Rect(x, y + 6, pw, ph)
        ui.rect(s, (6, 7, 11), r, border_radius=10)
        mode = mw.pv_mode()
        editing = mode == "draft" and self.thumbs is not None
        dimg = None
        if editing:                                                              # the picture of the DRAFT: what is being edited, not what is on the air
            self.thumbs.set_draft(mw.draft, extra=any(isinstance(x, dict) for _, x in mw.thumb_slots))          # the tiles of Modelo and Cores need their frames too
            dimg = self._tsurface(mw.draft)
        if dimg is not None:
            s.blit(self._rounded(dimg, (pw, ph), 10), r.topleft)
            if mw.cfg.get("ed_page") and int(mw.cfg.get("ed_item", 0)) == 0 and int(mw.cfg.get("ed_sub", 0)) == 3 and mw.cfg.get("scene_visual", 1) == 1:
                self._fold_overlay(r)
        elif editing:
            self._t(self.fs, "preparando o rascunho…", (r.centerx, r.centery - 8), wg.DIM, "c")
        elif self.preview is not None:
            s.blit(self._rounded(self.preview, (pw, ph), 10), r.topleft)
        else:
            pv = (status or {}).get("preview") or {}
            why = ("preview desligado" if not pv.get("on", True) else (pv.get("err") or self.preview_err or ("aguardando o 1º quadro (%s)" % pv.get("n", 0)))) if pv else "preview…"
            self._t(self.fs, self._fit(self.fs, why, pw - 16), (r.centerx, r.centery - 8), wg.DIM, "c")
        ui.rect(s, wg.BORDER, r, width=1, border_radius=10)
        if editing:
            self._pill(pygame.Rect(r.x + 8, r.y + 8, 84, 20), "RASCUNHO" if mw.is_dirty() else "EDITANDO", wg.ACCENT2, wg.ON_LIGHT)
        info = (status or {}).get("image") or {}
        cfg = mw.cfg
        scn = cfg.get("scenes") or []
        ed = scn[cfg["scene_edit"]]["scene_name"] if 0 <= cfg.get("scene_edit", 0) < len(scn) else "?"
        tx = x + pw + 16
        live_i = int(info.get("scene_i", -1))
        if mode == "live":
            self._t(self.fm, info.get("scene", "?"), (tx, y + 8), wg.TEXT)
            self._t(self.fs, "na imagem agora" + ("  ·  automático" if cfg.get("effect", 0) == 0 else ""), (tx, y + 32), wg.DIM)
            self._t(self.fs, "AJUSTANDO", (tx, y + 62), wg.TITLE)
            self._t(self.fm, M.SYS_ITEMS[M.SYS_IMAGE][0], (tx, y + 78), wg.TEXT)
            self._t(self.fs, "vale para todas as cenas", (tx, y + 102), wg.DIM)
            return

    def _margin_pic(self):
        """Where the big picture of the draft goes: in the free margin to the right of the editor, when the window is wide enough (else None)."""
        mw = self.menu
        px, py = self.panel_pos
        free = (mw.W - mw.EDITOR_W) // 2
        if free < 280:
            return None
        w = min(360, free - 24)
        return pygame.Rect(px + (mw.W + mw.EDITOR_W) // 2 + 12, py + mw.HEAD + mw.reserved + 8, w, w * 9 // 16)

    def _draft_pic(self, r, status, label=True):
        """The picture of the DRAFT (what is being edited, not what is on the air) in rectangle r."""
        s, mw = self.surf, self.menu
        ui.rect(s, (6, 7, 11), r, border_radius=10)
        if self.thumbs is not None:
            self.thumbs.set_draft(mw.draft, extra=any(isinstance(x, dict) for _, x in mw.thumb_slots))          # the tiles of Modelo and Cores need their frames too
            dimg = self._tsurface(mw.draft)
            if dimg is not None:
                s.blit(self._rounded(dimg, r.size, 10), r.topleft)
                if mw.cfg.get("ed_page") and int(mw.cfg.get("ed_item", 0)) == 0 and int(mw.cfg.get("ed_sub", 0)) == 3 and mw.cfg.get("scene_visual", 1) == 1:
                    self._fold_overlay(r)
            else:
                if r.w >= 160:                                                  # a small thumbnail (the header) has no room for words: it stays a dark square
                    self._t(self.fs, "preparando o rascunho…", (r.centerx, r.centery - 8), wg.DIM, "c")
        ui.rect(s, wg.BORDER, r, width=1, border_radius=10)
        if label:
            self._pill(pygame.Rect(r.x + 8, r.y + 8, 84, 20), "RASCUNHO" if mw.is_dirty() else "EDITANDO", wg.ACCENT2, wg.ON_LIGHT)

    def _draw_float_pic(self):
        """The big picture of the draft, pinned in the margin beside the editor (it stays in sight while the page scrolls)."""
        mw = self.menu
        r = self._margin_pic()
        if r is not None and mw.pv_mode() == "draft":
            self._draft_pic(r, None)

    def _draw_editor_head(self, x, y, status):
        """The ONE row over the editor: ‹ Galeria, the name, NO AR and the state on the left; Ao vivo, Descartar (only with changes) and Salvar on the right.
        A small picture of the draft sits at its start when there is no margin for the big one."""
        s, mw = self.surf, self.menu
        cfg, info = mw.cfg, (status or {}).get("image") or {}
        scn = cfg.get("scenes") or []
        ed = scn[cfg["scene_edit"]]["scene_name"] if 0 <= cfg.get("scene_edit", 0) < len(scn) else "?"
        cw_ = min(mw.W, mw.EDITOR_W)                                              # the row lines up with the column of the editor under it
        row = pygame.Rect(x + (mw.W - cw_) // 2, y + 4, cw_, self.HEAD_ROW - 8)
        cx = row.x
        if self._margin_pic() is None:
            tr = pygame.Rect(row.x, row.y, 96, 54)
            self._draft_pic(tr, status, label=False)
            cx = tr.right + 12
        self.bar_hits = []
        right = row.right - 4
        dirty, live = mw.is_dirty(), bool(cfg.get("live"))
        for cid, label, on, primary in (("ed_save", "Salvar", dirty, True), ("ed_discard", "Voltar ao que era" if live else "Descartar", dirty, False)):
            if cid == "ed_discard" and not dirty:
                continue                                                          # nothing to discard: the button is not there
            w = max(74, self.fb.size(label)[0] + 26)
            br = pygame.Rect(right - w, row.centery - 15, w, 30)
            wg.button(s, self.fb, br, label, "primary" if (primary and on) else "plain", hover=False, enabled=on, radius=9, dy=1)
            if on:
                self.bar_hits.append((br, cid))
            right = br.x - 8
        pill = pygame.Rect(right - 46, row.centery - 13, 46, 26)                  # Ao vivo: a real switch with its name
        ui.rect(s, wg.OK if live else (74, 80, 108), pill, border_radius=13)
        ui.circle(s, (255, 255, 255), (pill.right - 13 if live else pill.left + 13, pill.centery), 9)
        self._t(self.fs, "Ao vivo", (pill.x - 8, row.centery - 8), wg.OK if live else wg.DIM, "r")
        hit = pygame.Rect(pill.x - 70, pill.y - 4, 70 + pill.w, pill.h + 8)
        self.bar_hits.append((hit, "live_toggle"))
        right = hit.x - 6
        bw = max(64, self.fb.size("‹ Galeria")[0] + 22)                           # back is navigation, not an action: first, on the left
        br = pygame.Rect(cx, row.centery - 15, bw, 30)
        wg.button(s, self.fb, br, "‹ Galeria", "plain", hover=False, enabled=True, radius=9, dy=1)
        self.bar_hits.append((br, "scene_back"))
        nx = br.right + 14
        col, txt = mw.ed_status()
        sw = self.fb.size(txt)[0] + 18
        live_here = cfg.get("scene_edit", -1) == int(info.get("scene_i", -1))
        extra = (70 if live_here else 0) + sw + 12
        self._t(self.fm, self._fit(self.fm, ed, max(60, right - nx - extra)), (nx, row.centery - 12), wg.TEXT)
        nx += min(self.fm.size(ed)[0], max(60, right - nx - extra)) + 12
        if live_here:
            self._pill(pygame.Rect(nx, row.centery - 11, 58, 22), "NO AR", wg.ACCENT, (255, 255, 255))
            nx += 70
        if nx + sw < right:
            ui.circle(s, col, (nx + 5, row.centery), 5)
            self._t(self.fb, txt, (nx + 16, row.centery - 9), wg.DIM)

    def _draw_ear(self, an):
        """The analysis of the music in Sistema > Áudio: the card the Palco used to have, painted live over the slot the panel leaves for it."""
        mw = self.menu
        px, py = self.panel_pos
        top, bottom = py + mw.HEAD + mw.reserved, py + mw.HEAD + mw.reserved + mw.content_h()
        wl, wr, gap = mw._col_widths() if mw.panes() else (mw.W, 0, 0)
        if mw.panes():
            top += mw.pane_dims()[0]
        clip = self.surf.get_clip()
        lv = self.live
        for r in mw.ear_slots:
            right = mw.panes() and r.x >= wl
            sy = mw.scroll2 if right else mw.scroll
            slot = pygame.Rect(px + r.x, py + mw.reserved + r.y - sy, r.w, r.h)
            if slot.bottom < top or slot.top > bottom:
                continue
            self.surf.set_clip(pygame.Rect(px + (wl + gap if right else 0), top, wr if right else wl, bottom - top))
            full, hits, mouse, opened = lv.surf, lv.live_hits, lv.mouse, lv.ear_open
            lv.surf = pygame.Surface(slot.size, pygame.SRCALPHA)
            lv.live_hits, lv.mouse, lv.ear_open = [], None, True
            try:
                lv._ear_card(an, 0, slot.w)
                self.surf.blit(lv.surf, slot.topleft)
            finally:
                lv.surf, lv.live_hits, lv.mouse, lv.ear_open = full, hits, mouse, opened
        self.surf.set_clip(clip)

    def _draw_scene_thumbs(self):
        """The live thumbnails of the Estúdio: the panel leaves a dark slot for each and they are painted over it, so they move while the panel stays cached. A slot is a
        scene of the list or, in the tiles of the editor (a model of the mandala, a palette), the scene being edited as it would be with that choice."""
        mw = self.menu
        if self.thumbs is None or not mw.thumb_slots:
            return
        scn = mw.cfg["scenes"]
        self.thumbs.show(list(scn) + [x for _, x in mw.thumb_slots if isinstance(x, dict)])
        px, py = self.panel_pos
        top, bottom = py + mw.HEAD + mw.reserved, py + mw.HEAD + mw.reserved + mw.content_h()
        wl, wr, gap = mw._col_widths() if mw.panes() else (mw.W, 0, 0)
        if mw.panes():
            top += mw.pane_dims()[0]                                      # under the bar of the editor, which does not scroll
        clip = self.surf.get_clip()
        for r, i in mw.thumb_slots:
            sc = i if isinstance(i, dict) else (scn[i] if 0 <= i < len(scn) else None)
            if sc is None:
                continue
            right = mw.panes() and r.x >= wl                              # the two columns scroll on their own
            sy = mw.scroll2 if right else mw.scroll
            self.surf.set_clip(pygame.Rect(px + (wl + gap if right else 0), top, wr if right else wl, bottom - top))
            slot = pygame.Rect(px + r.x, py + mw.reserved + r.y - sy, r.w, r.h)
            if slot.bottom < top or slot.top > bottom or (mw.popup_rect is not None and slot.colliderect(mw.popup_rect.move(px, py + mw.reserved - sy))):
                continue
            img = self._tsurface(sc)
            if sc.get("scene_visual", 1) == 0 and not LY.has_bg(sc):
                ui.rect(self.surf, (0, 0, 0), slot, border_radius=6)
            elif img is not None:
                self.surf.blit(self._rounded(img, slot.size, 6), slot.topleft)
        self.surf.set_clip(clip)

    def _fold_overlay(self, r):
        """On the preview: the sector that is REAL (drawn by the engine) stays clear, the mirrors of the kaleidoscope are darkened and the mirror lines are drawn.
        It follows the symmetry under the pointer, or the one touched last, or the first one on."""
        mw = self.menu
        cfg = mw.cfg
        hov = mw.hover if isinstance(mw.hover, str) and mw.hover.startswith("m_sym") else None
        k = (8 if hov == "m_symnone" else int(hov[5:])) if hov else mw.preview_sym
        if k is None:
            k = next((i for i in range(SC.SYM_COUNT) if cfg.get("m_sym%d" % i)), 8)
        if k == 8:
            self._t(self.fs, "sem espelho: tudo é real", (r.centerx, r.bottom - 22), wg.TEXT, "c")
            return
        w, h = r.size
        cx, cy = w / 2.0, h / 2.0
        big = 4.0 * max(w, h)
        P = lambda x, y: (cx + x, cy - y)                                        # the engine's space (y up) to the preview's pixels
        lines, poly = [], []
        if k == 0:
            poly = [(0, 0), (big, 0), (big, big), (0, big)]
            lines = [0, 90]
        elif k == 1:
            poly = [(0, -big), (big, -big), (big, big), (0, big)]
            lines = [90]
        elif k == 6:
            poly = [(-big, 0), (big, 0), (big, big), (-big, big)]
            lines = [0]
        elif k == 5:
            poly = [(0, 0), (big, 0), (big, big)]
            lines = [0, 90, 45, 135]
        else:
            n = {2: 6, 3: 8, 4: 5, 7: 12}[k]
            a = math.pi / n
            poly = [(0, 0), (big, 0), (big * math.cos(a), big * math.sin(a))]
            lines = [math.degrees(a) * i for i in range(2 * n)]
        ov = pygame.Surface((w, h), pygame.SRCALPHA)
        ov.fill((8, 10, 22, 150))
        pts = [P(x, y) for x, y in poly]
        pygame.draw.polygon(ov, (0, 0, 0, 0), pts)
        for ang in lines:
            ar = math.radians(ang)
            pygame.draw.line(ov, (255, 255, 255, 120), P(-big * math.cos(ar), -big * math.sin(ar)), P(big * math.cos(ar), big * math.sin(ar)), 1)
        pygame.draw.polygon(ov, (*wg.ACCENT, 230), pts, 2)
        self.surf.blit(ov, r.topleft)
        # which part the label goes on: the middle of the real sector
        label_at = {0: (w * 0.28, h * 0.30), 1: (w * 0.25, 0.0), 6: (0.0, h * 0.25)}.get(k)
        if label_at is None:
            a = math.pi / ({2: 6, 3: 8, 4: 5, 7: 12}.get(k, 8)) / 2.0
            rad = h * 0.30
            label_at = (rad * math.cos(a), rad * math.sin(a))
        lx, ly = P(*label_at)
        self._t(self.fs, "real", (r.x + lx, r.y + ly - 8), (255, 255, 255), "c")
        self._t(self.fs, "claro = real  ·  escuro = espelho  ·  " + SC.SYM_LABELS[k], (r.centerx, r.bottom - 22), wg.TEXT, "c")

    # ------------------------------------------------------------- gallery of scenes
    COLS, GAP_G = 3, 12
    WHEN_PILL = {0: "ENTRANDO", 1: "NO COMPASSO", 2: "NA FRASE", 3: "NA MÚSICA", 4: "NA FRASE"}

    def pending_text(self, info):
        """The pill of a scene that waits for its moment: where it waits for and, when it is known, in how many seconds."""
        base = self.WHEN_PILL.get(int(self.menu.cfg.get("scene_when", 2)), "")
        eta = info.get("pending_eta")
        return f"{base} · {eta:.0f} s" if eta is not None and eta >= 0.5 else base

    def _next_thumb(self, surf, rect, i):
        """The live picture of the scene that waits for its moment (the only thumbnail the Palco draws)."""
        scn = self.menu.cfg["scenes"]
        if self.thumbs is None or not 0 <= i < len(scn):
            return
        self.thumbs.show([scn[i]])
        img = self._tsurface(scn[i])
        if img is not None:
            surf.blit(self._rounded(img, rect.size, 8), rect.topleft)

    def _live_strip(self, surf, y, Wc, hits, status):
        """The scenes of the Palco: a list of names (no pictures: the picture is on the big screen), the one on the air and the one that waits marked, the
        keys 1..9 of the picture window written on them. Click = play."""
        mw = self.menu
        scn = mw.cfg["scenes"]
        f = self.live.fonts
        info = (status or {}).get("image") or {}
        live_i = info.get("scene_i", 0)
        pend = info.get("pending_scene", -1)
        if self.thumbs is not None and not 0 <= pend < len(scn):
            self.thumbs.show([])                                            # nothing waits: no thumbnail to draw (the graphics card rests)
        self._t_on(surf, "xs", "CENAS  ·  clique para tocar", (0, y), wg.TITLE)
        nl = "+ Nova cena"
        nw = f["xs"].size(nl)[0] + 22
        nb = pygame.Rect(Wc - nw, y - 4, nw, wg.MIN_H)
        wg.button(surf, f["xs"], nb, nl, "plain", hover=self.live.mouse is not None and nb.collidepoint(self.live.mouse), radius=nb.h // 2)
        hits.append((nb, "wiz:start"))
        gap = 8
        ncol = max(2, min(5, (Wc + gap) // (150 + gap)))
        cw_ = (Wc - (ncol - 1) * gap) // ncol
        rh = 40
        y0 = y + 26
        for k, sc in enumerate(scn[:self.STRIP_MAX]):
            r = pygame.Rect((k % ncol) * (cw_ + gap), y0 + (k // ncol) * (rh + gap), cw_, rh)
            lit, waits = k == live_i, k == pend
            hv = self.live.mouse is not None and r.collidepoint(self.live.mouse)
            ui.rect(surf, (42, 34, 20) if waits else (wg.SURFACE2 if hv else wg.SURFACE), r, border_radius=10)
            ui.rect(surf, wg.ACCENT if lit else ((245, 184, 74) if waits else (wg.HOVER_EDGE if hv else wg.BORDER)), r, width=2 if (lit or waits) else 1, border_radius=10)
            x = r.x + 10
            if k < 9:
                self._t_on(surf, "xs", str(k + 1), (x, r.y + 12), wg.DIM)
                x += 16
            tag = "no ar" if lit else ("a seguir" if waits else "")
            tw = f["xs"].size(tag)[0] + 8 if tag else 0
            label = self._fit(self.fs, sc["scene_name"], r.right - 10 - tw - x)
            surf.blit(self.fs.render(label, True, wg.DIM if lit else wg.TEXT), (x, r.y + 11))
            if tag:
                self._t_on(surf, "xs", tag, (r.right - 8 - f["xs"].size(tag)[0], r.y + 13), wg.ACCENT if lit else (245, 184, 74))
            hits.append((r, "scene:%d" % k))
        k = min(len(scn), self.STRIP_MAX)                                  # the last item makes a new scene (also up there, by the title)
        r = pygame.Rect((k % ncol) * (cw_ + gap), y0 + (k // ncol) * (rh + gap), cw_, rh)
        hv = self.live.mouse is not None and r.collidepoint(self.live.mouse)
        ui.rect(surf, wg.SURFACE2 if hv else wg.SURFACE, r, border_radius=10)
        ui.rect(surf, wg.HOVER_EDGE if hv else wg.CTRL, r, width=1, border_radius=10)
        surf.blit(self.fs.render("+  Nova cena", True, wg.ACCENT2 if hv else wg.DIM), (r.x + 10, r.y + 11))
        hits.append((r, "wiz:start"))
        rows = (k + 1 + ncol - 1) // ncol
        return 26 + rows * (rh + gap) - gap

    def _t_on(self, surf, font, text, pos, color):
        surf.blit(self.live.fonts[font].render(text, True, color), pos)

    def _pill_on(self, surf, rect, text, fill, fg):
        wg.pill(surf, self.fs, rect, text, fill, fg)

    def _fit(self, font, text, w):
        return wg.fit(font, text, w)

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
                img = self._opaque(f[1], th.draft_size if sc is th.draft else th.size, th.fmt)
            except Exception:
                return cur[1] if cur else None
            cur = (f[0], img)
            self._tsurf[id(sc)] = cur
        return cur[1]

    def _gallery_click(self, kind, arg):
        mw = self.menu
        cfg = mw.cfg
        if kind in ("mi-bg", "wz-bg"):
            return
        if kind == "filter":
            cfg["sc_filter"] = int(arg)
            mw.scroll = 0
            mw.touch()
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
        elif kind in ("open", "edit"):                                 # a click on a card edits that scene (playing it is the Palco's job, or "Tocar agora" in the card's menu)
            mw.open_scene(arg)
        elif kind == "play":                                          # bring this scene to the picture
            mw.play_scene(arg)
        elif kind == "new":
            mw.start_wizard()                                           # three steps: what to see, colours, name
        elif kind == "wz-pick":
            mw.wizard_pick(arg)
        elif kind == "wz-pal":
            mw.wizard_palette(arg)
        elif kind == "wz-next":
            mw.wizard_next()
        elif kind == "wz-back":
            mw.wizard_back()
        elif kind == "wz-step":                                         # the pill of a step already done
            mw.wizard_goto(arg)
        elif kind == "wz-cancel":
            mw.cancel_wizard()
        elif kind == "wz-blank":
            mw.wizard_blank()
        elif kind == "wz-macro":                                        # the Cores of the Palco back to "Da cena": the colours chosen in the steps show
            mw.set_macro("pal", 0)
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
        elif kind == "export":
            mw.export_scenes()
        elif kind == "import":
            mw.import_scenes()
        elif kind == "factory":
            now = self.now or 0.0
            if self.gal_armed > now:
                self.gal_armed = 0.0
                mw.press("scene_factory")
            else:
                self.gal_armed = now + 3.0

    def _pill(self, rect, text, fill, fg):
        wg.pill(self.surf, self.fs, rect, text, fill, fg)

    def _draw_card(self, rect, sc, i, kind, status, live):
        s = self.surf
        mw = self.menu
        cfg = mw.cfg
        hov = self.gal_hover is not None and self.gal_hover[0] in ("open", "pick") and self.gal_hover[1] == i
        info = (status or {}).get("image", {})
        pending = kind == "open" and info.get("pending_scene", -1) == i
        fixed = kind == "open" and cfg["effect"] == i + 1
        off = kind == "open" and not sc.get("scene_auto", True)
        edge = wg.ACCENT if live else (wg.SEL if pending else (wg.HOVER_EDGE if hov else wg.BORDER))
        ui.rect(s, wg.SURFACE2 if hov else wg.SURFACE, rect, border_radius=14)
        ui.rect(s, edge, rect, width=2 if (live or pending or hov) else 1, border_radius=14)
        tw = rect.width - 8
        tr = pygame.Rect(rect.x + 4, rect.y + 4, tw, tw * 9 // 16)
        img = self._tsurface(sc)
        if sc.get("scene_visual", 1) == 0 and not LY.has_bg(sc):
            ui.rect(s, (0, 0, 0), tr, border_radius=10)
            self._t(self.fs, "tela preta", (tr.centerx, tr.centery - 8), wg.DIM, "c")
        elif img is not None:
            s.blit(self._rounded(img, tr.size, 10), tr.topleft)
        else:
            ui.rect(s, (6, 7, 11), tr, border_radius=10)
            bad = self.thumbs is not None and not self.thumbs.ready and self.thumbs.error
            self._t(self.fs, "preview indisponível" if bad else "…", (tr.centerx, tr.centery - 8), wg.DIM, "c")
        if off:                                                           # out of the Auto: the picture is faded
            sh = self._masks.get(("off", tr.size))
            if sh is None:
                sh = pygame.Surface(tr.size, pygame.SRCALPHA)
                ui.rect(sh, (10, 9, 22, 150), (0, 0, tr.w, tr.h), border_radius=10)
                self._masks[("off", tr.size)] = sh
            s.blit(sh, tr.topleft)
        ui.rect(s, wg.BORDER, tr, width=1, border_radius=10)
        # state badge: what this scene is doing right now
        if kind == "open":
            if live:
                txt, col, fg = "NO AR" + ("  ·  FIXA" if fixed else ""), wg.ACCENT, wg.ON_ACCENT
            elif pending:
                txt, col, fg = self.pending_text(info), wg.ACCENT2, wg.ON_LIGHT
            elif fixed:
                txt, col, fg = "FIXA", wg.ACCENT2, wg.ON_LIGHT
            elif off:
                txt, col, fg = "FORA DO AUTOMÁTICO", (46, 50, 72), wg.DIM
            else:
                txt = ""
            if txt:
                self._pill(pygame.Rect(tr.x + 6, tr.y + 6, self.fs.size(txt)[0] + 20, 20), txt, col, fg)
        # name, the Auto switch and what the scene is made of
        ny = tr.bottom + 8
        namew = rect.width - 20
        self._t(self.fb, self._fit(self.fb, sc["scene_name"], namew), (rect.x + 10, ny), wg.TEXT)
        shs = cfg.get("shaders") or []
        sid = int(sc.get("scene_shader", 0))
        if int(sc.get("scene_visual", 1)) >= 2:
            sub = SC.VISUALS[min(int(sc["scene_visual"]), len(SC.VISUALS) - 1)][0]
        elif sc.get("scene_visual", 1) == 0:
            sub = "Nenhum visual" + ("  ·  " + ("", "Aurora", "Feixes", "Pulsos", "Estrelas", "Faixas", "Lasers", "Feixe")[LY.lights_style(sc) % 8] if LY.lights_style(sc) else "")
        else:
            pn = SC.PRESET_NAMES[SC.preset_of(sc)]
            shn = "Shader auto" if sid == 0 or sid > len(shs) else shs[sid - 1]["name"]
            sub = shn if mw.scene_view == "preset" else ("Mandala" if pn == sc["scene_name"] else "Mandala " + pn) + "  ·  " + shn          # in the preset step "Mandala" is already said
        if kind == "open":
            nl = sum(1 for k_, _, _ in LY.SLOTS if LY.slot_on(sc, k_))
            sub += f"  ·  {nl} camadas"
        self._t(self.fs, self._fit(self.fs, sub, rect.width - 20), (rect.x + 10, ny + 22), wg.DIM)
        self.gal_hits.append((rect, "open" if kind == "open" else "pick", i))          # the card first: the controls (added next) win where they overlap
        if kind != "open":
            return
        # the menu button (three dots) on the picture
        mb = pygame.Rect(tr.right - 32, tr.y + 6, 26, 26)
        mh = self.gal_hover == ("menu", i) or self.card_menu == i
        ui.rect(s, wg.ACCENT2 if self.card_menu == i else (wg.SURFACE2 if mh else (13, 15, 24)), mb, border_radius=13)
        ui.rect(s, wg.HOVER_EDGE if mh else wg.BORDER, mb, width=1, border_radius=13)
        for dx in (-6, 0, 6):
            ui.circle(s, wg.ON_LIGHT if self.card_menu == i else wg.TEXT, (mb.centerx + dx, mb.centery), 2)
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
        items = [("edit", "Editar", wg.TEXT)]
        if not live:
            items.append(("play", "Tocar agora", wg.TEXT))
        items.append(("dup", "Duplicar", wg.TEXT))
        if len(mw.cfg["scenes"]) > 1:
            items.append(("del", "Apagar mesmo?" if armed else "Apagar", wg.DANGER))
        a = self._menu_anchor
        w, rh = 156, 32
        pr = pygame.Rect(a.right - w, a.bottom + 4, w, rh * len(items) + 12)
        ui.rect(s, (0, 0, 0, 110), pr.move(0, 3), border_radius=12)
        ui.rect(s, (26, 29, 44), pr, border_radius=12)
        ui.rect(s, wg.BORDER, pr, width=1, border_radius=12)
        self.gal_hits.append((pr, "mi-bg", i))                    # clicks on the menu's own background do nothing (and do not close it)
        for k, (act, label, col) in enumerate(items):
            ir = pygame.Rect(pr.x + 6, pr.y + 6 + k * rh, w - 12, rh - 2)
            hv = self.gal_hover == ("mi", (i, act))
            if hv:
                ui.rect(s, wg.DANGER if (act == "del") else wg.SURFACE2, ir, border_radius=8)
            self._t(self.fb if (act == "del" and armed) else self.fs, label, (ir.x + 12, ir.y + 6), wg.ON_LIGHT if (hv and act == "del") else col)
            self.gal_hits.append((ir, "mi", (i, act)))

    WZ_STEPS = ("Visual", "Cores", "Nome")
    WZ_ASK = ("O que você quer ver?", "Quais cores?", "Como ela se chama?")
    WZ_SUB = ("Escolha um visual: depois dá para mudar tudo", "As cores valem só para esta cena", "O nome aparece na lista de cenas")

    def _wz_button(self, rect, label, kind, arg, primary=False):
        wg.button(self.surf, self.fb, rect, label, "primary" if primary else "plain", hover=self.gal_hover == (kind, arg), radius=12)
        self.gal_hits.append((rect, kind, arg))

    def _draw_wizard(self, status):
        """"+ Nova cena" in three steps, drawn where the gallery is: 1 what to see (live thumbnails), 2 colours, 3 name. The picture of the scene being built is always
        there, Voltar and Continuar stay at the bottom of the window (they never scroll away), Cancelar is at the top."""
        s = self.surf
        mw = self.menu
        w = mw.wizard
        step = w["step"]
        px, py = self.panel_pos
        top = py + mw.HEAD
        view_h = mw.content_h()
        clip = s.get_clip()
        s.set_clip(pygame.Rect(px - 4, top, mw.W + 8, view_h))
        self.gal_hits = []
        y = top - mw.scroll
        if self.thumbs is not None:
            self.thumbs.show(w["bases"])
            self.thumbs.set_draft(w["draft"], extra=True)                       # the picture of the scene AND the thumbnails of the looks keep moving
        # ---- the three steps and the way out
        x = px
        for k, nm in enumerate(self.WZ_STEPS):
            lab = f"{k + 1}  {nm}"
            pw_ = max(92, self.fb.size(lab)[0] + 30)
            r = pygame.Rect(x, y + 6, pw_, 28)
            cur, done = k == step, k < step
            if cur:                                                                  # where you are: the chosen colour, dark ink, bold
                wg.pill(s, self.fb, r, lab, wg.SEL, wg.ON_SEL, dy=1)
            elif done:                                                               # a step already done: a tick, and a click goes back to it
                hv = self.gal_hover == ("wz-step", k)
                ui.rect(s, wg.HOVER_FILL if hv else wg.SURFACE2, r, border_radius=14)
                ui.rect(s, wg.HOVER_EDGE if hv else wg.SEL, r, width=1, border_radius=14)
                pygame.draw.lines(s, wg.SEL, False, [(r.x + 12, r.centery), (r.x + 16, r.centery + 4), (r.x + 23, r.centery - 4)], 2)
                self._t(self.fb, nm, (r.x + 30, r.y + 5), wg.SEL)
                self.gal_hits.append((r, "wz-step", k))
            else:                                                                    # a step to come: only a label, no edge (it is not a tab: Continuar goes there)
                ui.rect(s, wg.SURFACE2, r, border_radius=14)
                self._t(self.fs, lab, (r.centerx, r.y + 6), wg.DIM, "c")
            x += pw_ + 8
        cb = pygame.Rect(px + mw.W - 96, y + 6, 96, 28)
        hv = self.gal_hover == ("wz-cancel", 0)
        ui.rect(s, wg.HOVER_FILL if hv else wg.SURFACE, cb, border_radius=14)
        ui.rect(s, wg.HOVER_EDGE if hv else wg.BORDER, cb, width=1, border_radius=14)
        self._t(self.fs, "Cancelar", (cb.centerx, cb.y + 6), wg.TEXT if hv else wg.DIM, "c")
        self.gal_hits.append((cb, "wz-cancel", 0))
        self._t(self.fm, self.WZ_ASK[step], (px, y + 46), wg.TEXT)
        self._t(self.fs, self.WZ_SUB[step], (px, y + 74), wg.DIM)
        y0 = y + 104
        # ---- the picture of the scene being built, with what it is made of under it
        wide = mw.W >= 900
        pvw = min(420, int(mw.W * 0.36)) if wide else min(mw.W, 340)
        pvh = pvw * 9 // 16
        pr = pygame.Rect(px, y0, pvw, pvh)
        ui.rect(s, (6, 7, 11), pr, border_radius=12)
        dimg = self._tsurface(w["draft"])
        if dimg is not None:
            s.blit(self._rounded(dimg, pr.size, 12), pr.topleft)
        else:
            self._t(self.fs, "preparando a imagem…", (pr.centerx, pr.centery - 8), wg.DIM, "c")
        ui.rect(s, wg.BORDER, pr, width=1, border_radius=12)
        self._pill(pygame.Rect(pr.x + 8, pr.y + 8, 92, 20), "SUA CENA", wg.ACCENT2, wg.ON_LIGHT)
        pals = mw.cfg.get("palettes") or []
        cname = pals[w["pal"] - 1]["name"] if 0 < w["pal"] <= len(pals) else "cores do visual"
        self._t(self.fs, self._fit(self.fs, f"{w['bases'][w['pick']]['scene_name']}  ·  {cname}", pvw), (pr.x, pr.bottom + 8), wg.DIM)
        if wide:
            cx, cy, cwid = px + pvw + 24, y0, mw.W - pvw - 24
        else:
            cx, cy, cwid = px, pr.bottom + 36, mw.W
        end = pr.bottom + 36
        gap = 10
        if step == 0:                                                            # what to see: a live thumbnail of each look (the advanced have "Em branco" too)
            items = w["bases"]
            n = len(items) + (1 if mw.cfg.get("advanced") else 0)
            ncol = max(2, (cwid + gap) // (132 + gap))
            tw = (cwid - gap * (ncol - 1)) // ncol
            th = tw * 9 // 16
            rh = th + 28
            for k in range(n):
                r = pygame.Rect(cx + (k % ncol) * (tw + gap), cy + (k // ncol) * (rh + gap), tw, rh)
                real = k < len(items)
                kind = "wz-pick" if real else "wz-blank"
                hv = self.gal_hover == (kind, k if real else 0)
                sel = real and k == w["pick"]
                ui.rect(s, wg.SURFACE2 if hv else wg.SURFACE, r, border_radius=10)
                tr = pygame.Rect(r.x + 4, r.y + 4, tw - 8, th)
                if real:
                    img = self._tsurface(items[k])
                    if img is not None:
                        s.blit(self._rounded(img, tr.size, 8), tr.topleft)
                    else:
                        ui.rect(s, (6, 7, 11), tr, border_radius=8)
                    label = items[k]["scene_name"]
                else:
                    ui.rect(s, (13, 15, 24), tr, border_radius=8)
                    plus = self.fm.render("+", True, wg.ACCENT2)
                    s.blit(plus, (tr.centerx - plus.get_width() // 2, tr.centery - plus.get_height() // 2))
                    label = "Em branco"
                ui.rect(s, wg.SEL if sel else (wg.HOVER_EDGE if hv else wg.BORDER), r, width=3 if sel else 1, border_radius=10)
                self._t(self.fs, self._fit(self.fs, label, tw - 12), (r.x + 8, r.y + th + 9), wg.TEXT if sel else wg.DIM)
                self.gal_hits.append((r, kind, k if real else 0))
            end = max(end, cy + ((n + ncol - 1) // ncol) * (rh + gap))
        elif step == 1:                                                          # colours: the look's own, or one of the palettes
            macro = int(mw.cfg.get("macro_pal", 0))
            if macro > 0:                                                        # the Palco forces one palette on every scene: the choice below would not show, so this says so
                allp = mw.cfg.get("palettes") or []
                mname = allp[macro - 1]["name"] if macro <= len(allp) else "uma paleta"
                nr = pygame.Rect(cx, cy, cwid, 62)
                ui.rect(s, (44, 36, 20), nr, border_radius=10)
                ui.rect(s, (255, 200, 90), nr, width=1, border_radius=10)
                self._t(self.fs, self._fit(self.fs, f"As Cores do Palco estão em {mname} para todas as cenas.", nr.w - 196), (nr.x + 12, nr.y + 11), (255, 200, 90))
                self._t(self.fs, self._fit(self.fs, "Por isso a escolha abaixo não aparece na imagem.", nr.w - 196), (nr.x + 12, nr.y + 33), wg.DIM)
                self._wz_button(pygame.Rect(nr.right - 176, nr.y + 14, 164, 34), "Usar as da cena", "wz-macro", 0)
                cy += nr.h + 12
            cards = [None] + list((mw.cfg.get("palettes") or [])[:8])
            ncol = max(2, (cwid + gap) // (150 + gap))
            cw2 = (cwid - gap * (ncol - 1)) // ncol
            chh = 66
            for k, p in enumerate(cards):
                r = pygame.Rect(cx + (k % ncol) * (cw2 + gap), cy + (k // ncol) * (chh + gap), cw2, chh)
                hv = self.gal_hover == ("wz-pal", k)
                sel = k == w["pal"]
                ui.rect(s, wg.SURFACE2 if hv else wg.SURFACE, r, border_radius=10)
                if p is None:
                    self._t(self.fb, "Da cena", (r.centerx, r.y + 12), wg.TEXT, "c")
                    self._t(self.fs, "as cores do visual", (r.centerx, r.y + 36), wg.DIM, "c")
                else:
                    cols = [tuple(c) for c in p["colors"][:4]] or [(128, 128, 128)]
                    sw = (r.w - 16) // len(cols)
                    for j, col in enumerate(cols):
                        ui.rect(s, col, pygame.Rect(r.x + 8 + j * sw, r.y + 8, sw - 2 if j < len(cols) - 1 else sw, 28), border_radius=5)
                    self._t(self.fs, self._fit(self.fs, p["name"], r.w - 12), (r.centerx, r.y + 42), wg.TEXT if sel else wg.DIM, "c")
                ui.rect(s, wg.SEL if sel else (wg.HOVER_EDGE if hv else wg.BORDER), r, width=3 if sel else 1, border_radius=10)
                self.gal_hits.append((r, "wz-pal", k))
            end = max(end, cy + ((len(cards) + ncol - 1) // ncol) * (chh + gap))
        else:                                                                    # the name: the field is always the one that is typed into
            self._t(self.fs, "Nome da cena", (cx, cy), wg.DIM)
            fr = pygame.Rect(cx, cy + 22, min(cwid, 440), 52)
            ui.rect(s, wg.SURFACE2, fr, border_radius=12)
            ui.rect(s, wg.FOCUS, fr, width=2, border_radius=12)
            txt = w["name"]
            fresh = bool(w.get("fresh"))
            caret = "" if fresh else ("|" if int(time.perf_counter() * 2) % 2 == 0 else " ")
            img = self.fm.render(txt + caret, True, wg.TEXT)
            while img.get_width() > fr.w - 28 and len(txt) > 1:
                txt = txt[1:]
                img = self.fm.render(txt + caret, True, wg.TEXT)
            if fresh:                                                            # the ready-made name is selected: typing replaces it
                sel = pygame.Rect(fr.x + 10, fr.centery - img.get_height() // 2 - 2, img.get_width() + 8, img.get_height() + 4)
                ui.rect(s, (46, 78, 150), sel, border_radius=6)
            s.blit(img, (fr.x + 14, fr.centery - img.get_height() // 2))
            hint = ("No Logo, o nome também é o texto que aparece na tela" if int(w["draft"].get("scene_visual", 1)) == 9
                    else ("Digite para trocar o nome  ·  Enter cria a cena" if fresh else "Enter cria a cena"))
            self._t(self.fs, hint, (cx, fr.bottom + 10), wg.DIM)
            end = max(end, fr.bottom + 40)
        # ---- the bottom bar: it stays on the window while the rest scrolls
        fh = 64
        fy = top + view_h - fh
        s.fill(wg.BG, pygame.Rect(px - 4, fy, mw.W + 8, fh))
        pygame.draw.line(s, wg.BORDER, (px - 4, fy), (px + mw.W + 4, fy))
        self.gal_hits.append((pygame.Rect(px - 4, fy, mw.W + 8, fh), "wz-bg", 0))          # what is under the bar is not clickable through it
        if step > 0:
            self._wz_button(pygame.Rect(px, fy + 12, 120, 40), "‹ Voltar", "wz-back", 0)
        self._wz_button(pygame.Rect(px + mw.W - 170, fy + 12, 170, 40), "Criar cena" if step == 2 else "Continuar ›", "wz-next", 0, primary=True)
        if mw.W >= 640:
            self._t(self.fs, "Enter continua  ·  Esc volta", (px + mw.W // 2, fy + 23), wg.DIM, "c")
        s.set_clip(clip)
        mw.set_gal_h(end + mw.scroll - top + fh + 12)

    def _draw_gallery(self, status):
        """The Cenas tab, gallery and picker: a card per scene, each with a live thumbnail drawn at a very low resolution."""
        if self.menu.in_wizard():
            return self._draw_wizard(status)
        s = self.surf
        mw = self.menu
        cfg = mw.cfg
        self.COLS = max(3, (mw.W + self.GAP_G) // (230 + self.GAP_G))             # more cards per row when the window is wide
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
            self._t(self.fm, "Escolha o preset da mandala" if mw.scene_view == "preset" else "Escolha um modelo", (px, y + 8), wg.TEXT)
            br = pygame.Rect(px + mw.W - 110, y + 6, 110, 30)
            hv = self.gal_hover == ("cancel", 0)
            ui.rect(s, wg.SURFACE2 if hv else wg.SURFACE, br, border_radius=10)
            ui.rect(s, wg.HOVER_EDGE if hv else wg.BORDER, br, width=1, border_radius=10)
            self._t(self.fb, "‹ Voltar" if mw.scene_view == "preset" else "Cancelar", (br.centerx, br.y + 5), wg.ACCENT2, "c")
            self.gal_hits.append((br, "cancel", 0))
            self._t(self.fs, "Os números do preset viram da cena: depois é só ajustar" if mw.scene_view == "preset" else "A cena entra na galeria e abre para você configurar", (px, y + 34), wg.DIM)
        else:                                                                 # one verb: a click edits (playing is the Palco's job, the ••• menu of a card also plays)
            self._t(self.fm, "Cenas", (px, y + 8), wg.TEXT)
            self._t(self.fs, "cada cena é uma pilha de camadas  ·  clique para editar", (px, y + 34), wg.DIM)
            fx = px + mw.W
            for k_, lab in reversed(list(enumerate(("Todas", "Mandalas", "Outras")))):          # which scenes the gallery shows
                fw = self.fs.size(lab)[0] + 26
                fx -= fw
                fr_ = pygame.Rect(fx, y + 10, fw, 30)
                on = int(cfg.get("sc_filter", 0)) == k_
                hv = self.gal_hover == ("filter", k_)
                ui.rect(s, wg.SEL if on else (wg.SURFACE2 if hv else wg.SURFACE), fr_, border_radius=8)
                ui.rect(s, wg.SEL if on else (wg.HOVER_EDGE if hv else wg.BORDER), fr_, width=1, border_radius=8)
                self._t(self.fs, lab, (fr_.centerx, fr_.y + 6), wg.ON_SEL if on else wg.TEXT, "c")
                self.gal_hits.append((fr_, "filter", k_))
                fx -= 4
        y += 56
        cw = (mw.W - self.GAP_G * (self.COLS - 1)) // self.COLS
        ch = (cw - 8) * 9 // 16 + 4 + 8 + 22 + 22 + 14
        flt = 0 if picker else int(cfg.get("sc_filter", 0))
        idx = [i for i, sc in enumerate(items) if flt == 0 or (sc.get("scene_visual", 1) == 1) == (flt == 1)]          # the cards shown (their place in the list stays their index)
        n = len(idx) + (0 if picker else 1)
        live_i = self.live_scene
        for j in range(n):
            k = idx[j] if j < len(idx) else len(items)
            r = pygame.Rect(px + (j % self.COLS) * (cw + self.GAP_G), y + (j // self.COLS) * (ch + self.GAP_G), cw, ch)
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
                ui.rect(s, wg.SURFACE2 if hv else wg.SURFACE, r, border_radius=12)
                ui.rect(s, wg.HOVER_EDGE if hv else wg.BORDER, r, width=2 if hv else 1, border_radius=12)
                self._t(self.fm, "+", (r.centerx, r.centery - 28), wg.ACCENT2, "c")
                self._t(self.fb, "Nova cena", (r.centerx, r.centery + 4), wg.TEXT, "c")
                self._t(self.fs, "em 3 passos", (r.centerx, r.centery + 26), wg.DIM, "c")
                self.gal_hits.append((r, "new", 0))
        rows = (n + self.COLS - 1) // self.COLS
        end = y + rows * (ch + self.GAP_G)
        if not picker:
            self._draw_card_menu()                            # on top of the cards
        if not picker:
            for k_, (lab, bw_, bx_) in enumerate((("Exportar", 112, 0), ("Importar", 112, 120))):          # share the scenes as a file
                br_ = pygame.Rect(px + bx_, end + 4, bw_, 34)
                hv_ = self.gal_hover == (lab.lower(), 0)
                ui.rect(s, wg.SURFACE2 if hv_ else wg.SURFACE, br_, border_radius=10)
                ui.rect(s, wg.HOVER_EDGE if hv_ else wg.BORDER, br_, width=1, border_radius=10)
                self._t(self.fs, lab, (br_.centerx, br_.y + 8), wg.TEXT if hv_ else wg.DIM, "c")
                self.gal_hits.append((br_, "export" if k_ == 0 else "import", 0))
            fr = pygame.Rect(px + 240, end + 4, 250, 34)
            armed = self.gal_armed > self.now
            hv = self.gal_hover == ("factory", 0)
            ui.rect(s, wg.DANGER if armed else (wg.SURFACE2 if hv else wg.SURFACE), fr, border_radius=10)
            ui.rect(s, wg.DANGER if (armed or hv) else wg.BORDER, fr, width=1, border_radius=10)
            self._t(self.fs, "Confirmar? Apaga suas cenas" if armed else "Restaurar cenas de fábrica", (fr.centerx, fr.y + 8), wg.ON_LIGHT if armed else wg.DIM, "c")
            self.gal_hits.append((fr, "factory", 0))
            end += 44
        s.set_clip(clip)
        mw.set_gal_h(end + mw.scroll - top + 8)

    def update(self, now, an, fps, lat, vsync, status=None, force=False):
        if self.win is not None:
            sz = tuple(self.win.size)
            if sz[0] < self.MIN_W or sz[1] < self.MIN_H:                  # the window manager let it go under the minimum: it is brought back, a panel in a strip is unusable
                try:
                    self.win.size = sz = (max(sz[0], self.MIN_W), max(sz[1], self.MIN_H))
                except Exception:
                    pass
            if sz != (self.W, self.H):
                self.resize(*sz)
        iv = self.interval                                              # set by FPS do painel in Ajustes
        if not (force or self.force or self.menu.need or now - self.last >= iv):
            return
        self.last = now
        self.now = now
        self.force = False
        self.draw(an, fps, lat, vsync, status)
        prof.mark("UI/Palco, galeria, rolagem e avisos (resto do desenho)")
        if self.win is not None:
            self.tex.update(self.surf)
            prof.mark("UI/enviar a imagem do painel à janela (textura)")
            self.ren.clear()
            self.tex.draw()
            self.ren.present()
            prof.mark("UI/apresentar a janela do painel")

    def destroy(self):
        try:
            if self.win is not None:
                self.win.destroy()
        except Exception:
            pass
