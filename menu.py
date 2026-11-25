"""Settings panel (mouse + keyboard): it draws the pages of settings.py, takes the keys and the mouse and edits the settings (the steps of "+ Nova cena" are in wizard.py).

Design: three tabs (Palco, Estúdio, Sistema), grouped in cards; in a wide window the Estúdio and Sistema have two columns. Every option has a label, a one-line explanation and a
clearly stateful control: toggle, segmented choice or slider. Disabled controls say why. Keyboard focus is
always visible. Changes apply instantly and show a short confirmation.
"""
import json
import math
import os
import time

import copy

import pygame

import palettes as PAL
import icons
import ui
import layers as LY
import mods as MOD
import i18n
import scenes as SC
import settings
import shaderpresets as SP
import widgets
from widgets import (SURFACE, SURFACE2, BORDER, CTRL, TITLE, TEXT, DIM, ACCENT, ACCENT2, OK, DANGER, ON_ACCENT, ON_LIGHT, ON_SEL, SEL,
                     CTRL_FILL, HOVER_FILL, HOVER_EDGE, FOCUS, dimmed)         # the colour tokens live in widgets.py
from wizard import WizardMixin
from settings import (ae_current, auto_cards, CAM_AUTO, CAM_KEYS, CAM_MANUAL, CAM_OPTS, CAM_PRESETS, CUSTOM, DEFAULTS, ed_view, ED_VIEWS, fresh,
                      GFX_KEYS, FIN_KEYS, LIVE_H, load_ae, load_cfg, load_palette_edit, load_shader_edit, MACRO_ENERGY, macro_index, MACRO_SPEED,
                      match_camera, match_movement, match_preset, MV_AUTO, MV_KEYS, MV_MANUAL, MV_OPTS, MV_PRESETS, NAMES, PRESETS,
                      profile_path, save_cfg, scene_layout, scene_rows, scene_sub, sys_cards, SYS_IMAGE, SYS_ITEMS, sys_layout,
                      TAB_LIVE, TAB_SCENES, TAB_SYS, TABS, WIDE_MIN, _item_text)        # the data and the file on disk live in settings.py; these names stay readable as menu.X


class Menu(WizardMixin):
    W = 640
    HEAD = 44
    ROW = 52
    GAP = 12
    FOOT = 28

    def __init__(self, cfg):
        self.cfg = cfg
        if not cfg.get("lang"):                                                  # the first time: the language of Windows
            cfg["lang"] = i18n.system_lang()
        i18n.set_lang(cfg["lang"])
        self.dirty = False
        self.dirty_t = 0.0
        self.need = True
        self.f = widgets.font("body")
        self.fb = widgets.font("body", True)
        self.f_s = widgets.font("small")                              # help lines: the same size everywhere (small)
        self.f_sb = widgets.font("cap", True)
        self.title = widgets.font("title", True)
        self.ftab = widgets.font("label", True)                      # tabs and the choices of a row: label, bold
        self.hits = []
        self._tile_cache, self._tile_sig = {}, None
        self.base, self._live_eff = None, None             # the scene as it was saved when the editor opened (Live), and the Auto / fixed choice to bring back when Live ends
        self.order = []
        self.order_val = []
        self.focus = 0
        self.kbd = False
        self.hover = None
        self.drag = None
        self.toast = None
        self.draft, self.leave_armed = None, 0.0                       # the copy of the scene being edited, and until when a second press on Galeria leaves without saving
        self.preview_sym = None                                        # the symmetry the preview shows (the last one touched)
        self.dd_open, self.dd_hl, self.dd_rects = None, 0, {}          # the dropdown that is open, the option lit, and where each dropdown box is on the surface
        self.undo, self._undo_last = [], (None, 0.0)           # snapshots of the scenes, shaders and palettes (Ctrl+Z)
        self._reveal = None                                    # the item just opened: the next frame scrolls its row to the top
        self.sys_undo = []                                     # (when, label, restore function) of the Sistema actions with no confirmation: the toast offers "Desfazer"
        self._push_t = 0.0                                     # when the last scene snapshot was taken (Ctrl+Z undoes the newest of the two stacks)
        self.del_armed = (-1, 0.0)             # (scene, until) the delete button of a row of the list of scenes asks twice
        self.restore_armed = 0.0               # the same for "Cenas de fábrica"
        self.live_i, self.pend_i, self.live_scene = 0, -1, 0       # the scene on the air and the one that waits (the control window reports them)
        self.thumb_slots, self.popup_rect = [], None               # where the list of scenes wants its live thumbnails (the control window draws them)
        self.ear_slots = []                                            # where Sistema > Áudio wants the analysis of the music (the control window draws it)
        self.card_marks = []
        self._opening, self._extra = False, None
        self.osd_name = None                                  # (name, when) of the scene the person just brought to the picture: the picture window writes it once (osd.py)
        self.wizard = None                                    # "+ Nova cena" in three steps (what to see, colours, name) while scene_view is "wizard"
        self.taps, self.tap_release, self.tap_t = [], False, 0.0     # tap tempo asked for since the last frame (times), "back to automatic" asked for, and when the last tap was
        self._pending_img = None
        self.problems = {}                      # persistent warnings (audio, shader, thumbnails): key -> text, shown until they go away
        self.quit_armed = 0.0
        self.last_click = (None, 0.0)
        self.frects = {}
        self.scroll = self.scroll2 = 0
        self.view_h = 10 ** 6
        self.tab = max(0, min(int(os.environ.get("VIS_TAB", self.cfg.get("ui_tab", 0))), 2))        # the tab you left it on (VIS_TAB: test hook)
        self.live = ""
        self._info = ""                # version / update status, shown in Sistema > Aplicativo
        self._upd_label = ""           # text of the "update to vX" button (empty = no update to offer)
        self._notes = ""
        self.live_h = LIVE_H                           # current height of the live tab's content (the deck reports it)
        self.text_focus = None                         # id of the text field being typed into
        self.reserved = 0                              # height of the preview strip under the tab bar (the control window sets it)
        self.heights = []
        self.audio_devices, self.monitors = [], 1       # asked of the system by the app once it is open
        self.scene_view = "gallery"                    # the Cenas tab: gallery (all scenes), picker (a new scene) or editor (one scene)
        self.gal_h = 420                               # height of the gallery content (the control window reports it)
        self.templates = SC.templates()                # the scenes the picker offers (kept, so their live thumbnails stay the same)
        self.preset_templates = SC.preset_templates()  # the second step: a mandala preset
        self._eff_before = 0                           # the Auto / fixed-scene choice to bring back when the editor closes
        self.W = type(self).W                          # the width of the panel: it follows the window (set_width)
        self.mx = 0                                    # where the pointer was last (x on the panel): the wheel scrolls the column under it
        self.cols = {TAB_SCENES: [], TAB_SYS: []}      # the column of each card when the window is wide: "F" full width, "L" left, "R" right
        self.slider_geos = {}                          # cid -> (left of the track, its length), on the surface
        self.rebuild_scenes(first=True)
        self.H = max(self.heights)                  # the surface fits the tallest tab (with room for more scenes)
        self.surf = pygame.Surface((self.W, self.H + 800), pygame.SRCALPHA)

    def _compute_heights(self):
        self.heights = []
        wl, wr, _g = self._col_widths()
        wcol = {"F": self.W, "L": wl, "R": wr}
        for t, (tname, secs) in enumerate(TABS):
            h = self.HEAD
            cols = self.cols.get(t) or []
            if cols and len(cols) == len(secs):
                tot = {"F": 0, "L": 0, "R": 0}
                run = 0
                for (ttl, rows), col in zip(secs, cols):
                    if col == "F":
                        run += max(tot["L"], tot["R"]) + self._card_h(rows, ttl, wcol[col]) + self.GAP
                        tot = {"F": 0, "L": 0, "R": 0}
                    else:
                        tot[col] += self._card_h(rows, ttl, wcol[col]) + self.GAP
                h += run + max(tot["L"], tot["R"])
            else:
                h += sum(p["h"] + p["gap"] for p in self._single_plan(secs, self._single_w(t)))
            if t == TAB_LIVE:
                h = self.HEAD + self.live_h + 8
            if t == TAB_SCENES and self.scene_view != "editor":
                h = self.HEAD + self.gal_h + 8
            self.heights.append(h + self.FOOT)

    EDITOR_W = 880                                                       # the widest the accordion of the editor gets: the labels stay near their controls

    def _single_w(self, tab=None):
        """Width of a card in the one-column layout: the editor does not stretch across a wide window."""
        return min(self.W, self.EDITOR_W) if (self.tab if tab is None else tab) == TAB_SCENES else self.W

    def _single_plan(self, cards, wc):
        """The cards of the one-column layout as parts to draw: a run of cards whose title starts with "§" is ONE container (the open layer of the editor: its row, its page
        inset and tinted, the rows after it), and the parts that start with "§§" are the inset ones."""
        plan = []
        for title, rows in cards:
            grp, kid = title.startswith("§"), title.startswith("§§")
            t = title.lstrip("§")
            w = wc - 28 if kid else wc
            plan.append(dict(title=t, rows=rows, grp=grp, kid=kid, w=w, h=self._card_h(rows, t, w) - (8 if grp and not t else 0), gap=self.GAP))
        for i, p in enumerate(plan[:-1]):
            if p["grp"] and plan[i + 1]["grp"]:
                p["gap"] = 4                                                      # inside a container the parts nearly touch
        return plan

    def _card_h(self, rows, title="x", wc=None):
        """A card with a title is 40 high before its rows; one without a title (the bar of the editor) only has a little air. wc is the width of the card: a run of
        `flow` rows (the scenes of the Automático) is laid in lines, so its height depends on it."""
        return (40 if title else 8) + self._rows_h(rows, wc or self.W) + 10

    FLOW_H, FLOW_GAP = 32, 8                                      # a pill of a run of `flow` switches, and the air between two of them

    def _flow_layout(self, rows, wc):
        """Where the pills of a run of `flow` rows go: left to right, in lines, inside a card of width wc. Returns ([(row, x, y, w)], height of the run)."""
        cells, x, y, inner = [], 0, 0, wc - 36
        for row in rows:
            w = max(56, min(200, self.fb.size(row["label"])[0] + 28))             # measured in bold: a pill does not change its size when it is turned on
            if x and x + w > inner:
                x, y = 0, y + self.FLOW_H + self.FLOW_GAP
            cells.append((row, 18 + x, 4 + y, w))
            x += w + self.FLOW_GAP
        return cells, 4 + y + self.FLOW_H + 6

    TILE_GAP = 10

    def _tile_layout(self, rows, wc):
        """A run of `tile` rows (a model of the mandala, a palette): a live thumbnail each, in lines. Returns ([(row, x, y, w, thumb h)], height of the run, height of a tile)."""
        gap, inner = self.TILE_GAP, wc - 36
        ncol = max(2, (inner + gap) // (118 + gap))
        tw = (inner - gap * (ncol - 1)) // ncol
        th = tw * 9 // 16
        rh = th + 32
        cells = [(row, 18 + (k % ncol) * (tw + gap), 4 + (k // ncol) * (rh + gap), tw, th) for k, row in enumerate(rows)]
        lines = (len(rows) + ncol - 1) // ncol
        return cells, 4 + lines * (rh + gap) - gap + 6, rh

    def _tile_scene(self, row):
        """The scene being edited as it would be with this tile chosen: what the thumbnail of the tile draws."""
        key, v = row["tile"]
        sig = json.dumps(self.draft, sort_keys=True) if self.draft is not None else ""
        if sig != self._tile_sig:
            self._tile_cache, self._tile_sig = {}, sig
        sc = self._tile_cache.get((key, v))
        if sc is None:
            sc = copy.deepcopy(self.draft or {})
            if key == "preset":
                SC.apply_preset(sc, v)
                sc["scene_preset"] = v
            else:
                sc["scene_palette"] = v
            self._tile_cache[(key, v)] = sc
        return sc

    def _tile_rows(self, rows, y, wc):
        """A run of choices drawn as thumbnails (the control window paints them over the dark slots). They are radios like the others: same ids, hits and focus."""
        s, c = self.surf, self.cfg
        cells, h, rh = self._tile_layout(rows, wc)
        for row, x, dy, tw, th in cells:
            cid, val = row["id"], row["value"]
            fkey = f"{cid}#{val}"
            sel = c[cid] == val
            r = pygame.Rect(x, y + dy, tw, rh)
            ui.rect(s, (*SURFACE2, 255), r, border_radius=10)
            tr = pygame.Rect(r.x + 4, r.y + 4, tw - 8, th)
            ui.rect(s, (6, 7, 11, 255), tr, border_radius=8)
            self.thumb_slots.append((tr, self._tile_scene(row)))
            ui.rect(s, (*(SEL if sel else BORDER), 255), r, width=3 if sel else 1, border_radius=10)
            self._txt(self.f_s, self._fit(self.f_s, row["label"], tw - 12), (r.x + 8, r.y + th + 11), TEXT if sel else DIM)
            self.frects[fkey] = r
            self.order.append(fkey)
            self.order_val.append(val)
            self.hits.append((r, cid, "radio", val))
        return h

    def _rows_h(self, rows, wc):
        """The height of the rows of a card: one ROW each, and one block for every run of `flow` (or `tile`) rows."""
        h, i = 0, 0
        while i < len(rows):
            if rows[i].get("tile"):
                j = i
                while j < len(rows) and rows[j].get("tile"):
                    j += 1
                h += self._tile_layout(rows[i:j], wc)[1]
                i = j
            elif rows[i].get("flow"):
                j = i
                while j < len(rows) and rows[j].get("flow"):
                    j += 1
                h += self._flow_layout(rows[i:j], wc)[1]
                i = j
            elif rows[i].get("kind") == "ear":
                h += self.EAR_H
                i += 1
            else:
                h += self.ROW + (self.STACK if self._stacked(rows[i], wc) else 0)
                i += 1
        return h

    EAR_H = 492                                                                  # the analysis of the music in Sistema > Áudio (deck's card, open)

    STACK = 40                                                                   # the extra height of a row whose choices go on a line of their own

    def _stacked(self, row, W):
        """A row of choices so wide that its name and help would be cut: the choices go on a second line, under the text."""
        if row.get("kind") != "seg" or not row.get("label"):
            return False
        R = W - 26
        return R - self._ctl_left(row, "seg", R, W) > (W - 20) * 0.5

    def _flow_rows(self, rows, y, wc):
        """A run of switches drawn as pills that wrap (the scenes of the Automático): lit = on. They are switches like the others: same ids, same hits, same focus.
        Returns the height they took."""
        s, c = self.surf, self.cfg
        cells, h = self._flow_layout(rows, wc)
        for row, x, dy, w in cells:
            cid = row["id"]
            en = self.enabled(row)
            on = row["get"](c) if "get" in row else c[cid]
            r = pygame.Rect(x, y + dy, w, self.FLOW_H)
            widgets.button(s, self.fb if on else self.f, r, row["label"], "select" if on else "plain", hover=self.hover == cid and en, enabled=en, radius=self.FLOW_H // 2)
            self.frects[cid] = r
            if en:
                self.order.append(cid)
                self.order_val.append(row.get("value"))
            self.hits.append((r, cid, "toggle", None))
        return h

    # ------------------------------------------------------------ scene presets
    @property
    def wide(self):
        """The window is wide enough for the two columns. (While a column is drawn, self.W is the column's width: the window's own width is kept apart.)"""
        return getattr(self, "W_window", self.W) >= WIDE_MIN

    def set_width(self, w):
        """The panel follows the window: a new width redraws everything, and the editor changes layout at WIDE_MIN."""
        w = max(560, int(w))
        self.W_window = w
        if w == self.W:
            return
        self.W = w
        self.rebuild_scenes()
        self.surf = pygame.Surface((self.W, max(self.heights) + 800), pygame.SRCALPHA)
        self.H = max(self.H, max(self.heights))
        self.dd_open = None
        self.need = True

    SIDE_W = 230                                                                   # the bar of the scenes, on the left of the wide editor (control.py draws it)

    def side_on(self):
        """The wide editor has the list of scenes on its left: a fixed bar, outside the two columns."""
        return self.tab == TAB_SCENES and self.scene_view == "editor" and bool(getattr(self, "wide", False))

    def side_w(self):
        return self.SIDE_W if self.side_on() else 0

    def _col_widths(self):
        gap = 12
        avail = self.W - self.side_w()
        wl = max(300, min(440, int(avail * 0.40)))
        return wl, avail - wl - gap, gap

    @property
    def info(self):
        return self._info

    @info.setter
    def info(self, v):
        if v != self._info:
            self._info, self.need = v, True

    @property
    def upd_label(self):
        return self._upd_label

    @upd_label.setter
    def upd_label(self, v):
        if v != self._upd_label:
            self._upd_label, self.need = v, True

    @property
    def notes(self):
        return self._notes

    @notes.setter
    def notes(self, v):
        if v != self._notes:
            self._notes, self.need = v, True

    def pv_mode(self):
        """The strip with the picture under the tab bar: "draft" (the scene being edited), "live" (the picture on the air, in Sistema > Imagem) or None."""
        if self.tab == TAB_SCENES and self.scene_view == "editor" and self.draft is not None:
            return "draft"
        return None                                          # Sistema > Imagem has no picture strip any more

    def workspace(self):
        """The Estúdio that is only an editor (the scene chosen in a list beside it). Not any more: every width starts on the gallery, and the editor has the
        stack of the scene on its left."""
        return False

    def rebuild_scenes(self, first=False):
        if self.workspace() and self.scene_view not in ("editor", "wizard") and not self._opening and self.cfg["scenes"]:
            self._opening = True                                              # a wide Estúdio never shows the gallery: the scene being edited opens
            try:
                self.open_scene(max(0, min(int(self.cfg["scene_edit"]), len(self.cfg["scenes"]) - 1)))
            finally:
                self._opening = False
            return
        wide = self.W >= WIDE_MIN
        self.cfg["ed_tab"] = settings.ed_tab_of(self.cfg)
        cards, cols = scene_layout(self.cfg, self.scene_view, wide and self.scene_view == "editor")
        TABS[TAB_SCENES] = ("Estúdio", cards)
        self.cols[TAB_SCENES] = cols
        cards, cols = sys_layout(self.cfg, max(0, min(int(self.cfg.get("sys_item", 0)), len(SYS_ITEMS) - 1)), wide, self.audio_devices, self.monitors, self)
        TABS[TAB_SYS] = ("Sistema", cards)
        self.cols[TAB_SYS] = cols
        self._extra = None
        self._compute_heights()
        self.need = True
        if not first:
            self.H = max(self.H, max(self.heights))
            if self.surf.get_height() < max(self.heights):
                self.surf = pygame.Surface((self.W, max(self.heights) + 800), pygame.SRCALPHA)

    def store_scene(self):
        """The working keys go back into the scene being edited: while the editor is open that is the DRAFT (a copy), so nothing reaches the picture until Salvar."""
        scn = self.cfg["scenes"]
        ed = self.cfg["scene_edit"]
        if self.scene_view == "editor" and self.draft is not None:
            SC.store_scene(self.cfg, self.draft)
            if self.cfg.get("live") and 0 <= ed < len(scn):                      # Live: the scene itself follows, so the big picture and the thumbnails do too
                scn[ed].clear()
                scn[ed].update(copy.deepcopy(self.draft))
        elif 0 <= ed < len(scn):
            SC.store_scene(self.cfg, scn[ed])

    def _live_take(self, i):
        """Live: the scene being edited takes the picture (the Auto / fixed choice comes back when Live ends)."""
        if self._live_eff is None:
            self._live_eff = self.cfg["effect"]
        self.cfg["effect"] = i + 1
        self.cfg["scene_now"] = True

    def _live_end(self):
        if self._live_eff is not None:
            self.cfg["effect"] = self._live_eff
            self._live_eff = None

    def set_live_edit(self, on):
        """The Live switch of the Estúdio: on, every change of the scene shows on the big picture at once; off, the editor works on a draft until Salvar."""
        self.cfg["live"] = on
        ed = self.cfg["scene_edit"]
        if on and self.scene_view == "editor" and self.draft is not None and 0 <= ed < len(self.cfg["scenes"]):
            self.store_scene()
            self._live_take(ed)
        elif not on:
            self._live_end()
        self.rebuild_scenes()
        self.touch()
        self.say("Ao vivo ligado: o que você muda aparece na tela grande" if on else "Ao vivo desligado")

    def is_dirty(self):
        """True when the draft differs from the scene as it is saved."""
        scn = self.cfg["scenes"]
        ed = self.cfg["scene_edit"]
        if self.scene_view != "editor" or self.draft is None or not 0 <= ed < len(scn):
            return False
        ref = self.base if (self.cfg.get("live") and self.base is not None) else scn[ed]
        return json.dumps(self.draft, sort_keys=True) != json.dumps(ref, sort_keys=True)

    def save_scene(self):
        """Salvar: the draft becomes the scene (in place, so the picture and the thumbnails that hold it follow at once)."""
        scn = self.cfg["scenes"]
        ed = self.cfg["scene_edit"]
        if self.draft is None or not 0 <= ed < len(scn):
            return
        self.store_scene()
        scn[ed].clear()
        scn[ed].update(copy.deepcopy(self.draft))
        self.base = copy.deepcopy(self.draft)
        self.leave_armed = 0.0
        self.rebuild_scenes()
        self.touch()
        self.say("Cena salva")

    def discard_scene(self):
        """Descartar: the draft goes back to the scene as it is saved."""
        scn = self.cfg["scenes"]
        ed = self.cfg["scene_edit"]
        if self.draft is None or not 0 <= ed < len(scn):
            return
        if self.cfg.get("live") and self.base is not None:                    # Live: the scene itself goes back to how it was when the editor opened
            scn[ed].clear()
            scn[ed].update(copy.deepcopy(self.base))
        self.draft = copy.deepcopy(scn[ed])
        SC.apply_scene(self.cfg, self.draft)
        self.leave_armed = 0.0
        self.rebuild_scenes()
        self.say("Alterações descartadas")

    def select_item(self, k):
        """A click on an item of the stack of the editor: its parameters show below (a layer of the six opens on the top thing it has)."""
        if int(self.cfg.get("ed_item", 0)) == int(k) and not self.wide:      # the open item again: it folds (wide: it stays, the page is on the right)
            self.cfg["ed_item"] = -1
            self.dd_open = None
            self.rebuild_scenes()
            return
        self.open_item(k)

    def open_item(self, k):
        """Open item k of the accordion (it stays open if it already is)."""
        self.cfg["ed_item"] = int(k)
        slot = settings.ITEM_SLOT.get(int(k))
        if slot in ("bg", "lights", "parts", "finish"):
            i = LY.first_of(self.cfg, slot)
            if i >= 0:
                self.cfg["ly_sel"] = i
                LY.load_lp(self.cfg)
        self._reveal = int(k)
        self.cfg["ed_page"] = True                                       # its own page (in a wide window the item shows beside the stack: no page, the view stays where it is)
        self.dd_open = None
        self.rebuild_scenes()

    def reset_scroll(self, inspector=False):
        """Back to the top. In a wide window the two columns scroll on their own: with `inspector` only the right one (the item shown) goes to the top and the list stays."""
        self.scroll2 = 0
        if not (inspector and self.panes()):
            self.scroll = 0

    def ed_back(self):
        """From the page of an item back to the overview of the scene."""
        self.cfg["ed_page"] = False
        self.dd_open = None
        self.scroll = self.scroll2 = 0
        self.rebuild_scenes()

    def _pal(self):
        return self.cfg["palettes"][self.cfg["pal_edit"]]

    def select_palette(self, i):
        self.cfg["pal_edit"] = max(0, min(i, len(self.cfg["palettes"]) - 1))
        self.cfg["pal_item"] = 0
        load_palette_edit(self.cfg)
        self.rebuild_scenes()

    def _shd(self):
        return self.cfg["shaders"][self.cfg["shd_edit"]]

    def select_shader(self, i):
        self.cfg["shd_edit"] = max(0, min(i, len(self.cfg["shaders"]) - 1))
        self.cfg["shd_item"] = 0
        load_shader_edit(self.cfg)
        self.rebuild_scenes()

    def in_gallery(self):
        return self.tab == TAB_SCENES and self.scene_view != "editor"

    def set_gal_h(self, h):
        """The control window tells how tall the gallery (or the picker) is."""
        h = int(h)
        if h != self.gal_h:
            self.gal_h = h
            self._compute_heights()
            if self.surf.get_height() < max(self.heights):
                self.surf = pygame.Surface((self.W, max(self.heights) + 800), pygame.SRCALPHA)
            self.need = True

    def open_scene(self, i):
        """Open the editor of scene i. The picture shows that scene while it is edited."""
        scn = self.cfg["scenes"]
        if not 0 <= i < len(scn):
            return
        if self.scene_view != "editor":
            self._eff_before = self.cfg["effect"]
        self.wizard = None                                  # opening a scene's editor leaves the steps of a new scene
        it = int(self.cfg.get("ed_item", 0))
        self.cfg["ed_item"], self.cfg["ed_sub"], self.cfg["ed_page"] = (it if 0 <= it < 12 else 0), 0, False       # the page you were on stays (never the empty Ligações), the first time it is the Forma
        self.draft = copy.deepcopy(scn[i])                  # the editor works on a copy: the picture keeps the saved scene until Salvar
        self.leave_armed = 0.0
        SC.apply_scene(self.cfg, self.draft)
        self.base = copy.deepcopy(scn[i])
        if self.cfg.get("live"):
            self._live_take(i)
        self.cfg["scene_edit"] = i
        self.scene_view = "editor"
        self.scroll = self.scroll2 = 0
        self.rebuild_scenes()
        self.touch()

    def close_scene(self):
        """Back to the gallery. What was not saved is dropped; the working keys go back to the saved scene."""
        self.store_scene()
        self._live_end()
        self.draft = None
        self.leave_armed = 0.0
        scn = self.cfg["scenes"]
        if 0 <= self.cfg["scene_edit"] < len(scn):
            SC.apply_scene(self.cfg, scn[self.cfg["scene_edit"]])
        self.scene_view = "gallery"
        self.scroll = self.scroll2 = 0
        self.rebuild_scenes()
        self.touch()

    def leave_editor(self):
        """Out of the editor to the gallery. With unsaved changes the first press only warns."""
        now = time.perf_counter()
        if self.is_dirty() and not self.cfg.get("live") and now > self.leave_armed:
            self.leave_armed = now + 4.0
            self.say("Alterações não salvas: Salvar, Descartar, ou toque de novo em Galeria para descartar")
            self.need = True
            return None
        self.close_scene()
        return None

    def back_to_gallery(self):
        if self.scene_view == "wizard":
            return self.wizard_back()                                         # one step back, and out from the first one
        if self.scene_view == "editor":
            if self.workspace():                                              # the wide Estúdio has no gallery: the list of scenes is always there
                return None
            return self.leave_editor()
        else:
            self.scene_view = "gallery"
            self.scroll = self.scroll2 = 0
            self.rebuild_scenes()
            self.touch()
        return None

    def duplicate_scene(self, i):
        """A copy of scene i, right after it in the gallery."""
        self._push()
        scn = self.cfg["scenes"]
        if not 0 <= i < len(scn):
            return
        if i == self.cfg["scene_edit"]:
            self.store_scene()
        new = copy.deepcopy(scn[i])
        new["scene_name"] = (new["scene_name"] + " (cópia)")[:28]
        scn.insert(i + 1, new)
        eff = self.cfg["effect"]
        if eff > i + 1:
            self.cfg["effect"] = eff + 1
        if self.cfg["scene_edit"] > i:
            self.cfg["scene_edit"] += 1
        self.rebuild_scenes()
        self.touch()
        self.say(f"Cena duplicada: {new['scene_name']}")

    def play_scene(self, i, osd=True):
        """Bring scene i to the picture: at once, unless "Ao clicar numa cena" (an advanced choice) asks it to wait for the moment "Quando troca sozinha" says.
        `osd` asks the picture window to write the name of the scene on the screen (a click or a key of the person; never a controller: that one may be
        driving a projection)."""
        scn = self.cfg["scenes"]
        if not 0 <= i < len(scn):
            return False
        now = not self.cfg.get("scene_wait", 0)
        was_auto = self.cfg["effect"] == 0
        self.cfg["effect"] = i + 1
        self.cfg["scene_now"] = now
        self.touch()
        self.tour_mark(1)
        if osd:
            self.osd_name = (scn[i]["scene_name"], time.perf_counter())         # the picture window writes the name on the screen (see osd.py)
        self.say(f"{scn[i]['scene_name']}: entra " + ("agora" if now else ("agora", "no próximo compasso", "na próxima frase", "no próximo evento da música", "na próxima frase")[int(self.cfg.get("scene_when", 2)) % 5])
                 + ("  ·  automático desligado" if was_auto else ""))
        return True

    def tour_mark(self, i):
        """A step of the first-use card is done (kept in the settings: the card remembers where the person stopped)."""
        bit = 1 << i
        if not self.cfg.get("tour_done") and not int(self.cfg.get("tour_marks", 0)) & bit:
            self.cfg["tour_marks"] = int(self.cfg.get("tour_marks", 0)) | bit
            self.touch()

    def set_scene_auto(self, i, on):
        """May the Automático bring scene i to the picture? Kept on the scene, and on the working copy and the draft when it is the one being edited (so the
        draft does not turn "not saved" just because of a switch somewhere else)."""
        scn = self.cfg["scenes"]
        if not 0 <= i < len(scn):
            return
        on = bool(on)
        scn[i]["scene_auto"] = on
        if i == self.cfg.get("scene_edit"):
            self.cfg["scene_auto"] = on
            if self.draft is not None:
                self.draft["scene_auto"] = on
        self.touch()
        self.say(f"{scn[i]['scene_name']}: " + ("entra no Automático" if on else "fora do Automático"))

    def open_sys(self, k):
        """Go to page k of Sistema (the warnings of the Palco lead here, and so does the Opções button next to "Troca automática")."""
        self.cfg["sys_item"] = max(0, min(int(k), len(SYS_ITEMS) - 1))
        self.cfg["search"] = ""                                                   # the page, not an old search
        self.press("tab%d" % TAB_SYS)

    def adv_hidden(self):
        """How many settings of Sistema the Avançado switch would show (cached: it only changes with the graphics preset)."""
        key = self.cfg.get("preset")
        if getattr(self, "_adv_n", (None, 0))[0] != key:
            full = dict(self.cfg, advanced=True)
            n = 0
            for k in range(len(SYS_ITEMS)):
                shown = {r["id"] for _, rs in sys_cards(self.cfg, k) for r in rs}
                n += len({r["id"] for _, rs in sys_cards(full, k) for r in rs if r["kind"] != "note" and r["id"] not in shown})
            self._adv_n = (key, n)
        return self._adv_n[1]

    def goto(self, dest):
        """Jump to a place of the panel: "sys:N" is page N of Sistema, "acab" is the Acabamento layer of the scene being edited, "tab:N" a tab."""
        kind, _, arg = dest.partition(":")
        if kind == "sys":
            self.open_sys(int(arg))
        elif kind in ("acab", "ed"):                                              # a page of the editor of the scene (Acabamento by name)
            item = settings.SLOT_ITEM["finish"] if kind == "acab" else int(arg)
            self.press("tab%d" % TAB_SCENES)
            if self.scene_view != "editor" or self.draft is None:
                self.open_scene(max(0, min(int(self.cfg.get("scene_edit", 0)), len(self.cfg["scenes"]) - 1)))
            self.cfg["ed_item"], self.cfg["ed_sub"] = item, 0
            self.reset_scroll(inspector=True)
            self.rebuild_scenes()
        elif kind == "tab":
            self.press("tab%d" % int(arg))
        self.need = True

    def lower_quality(self):
        """The picture is slow: one step down the graphics shortcut (Ultra, Alto, Médio, Baixo). "Personalizado" goes to the strongest shortcut that asks
        for less than it does, so it never goes up. Returns False when there is nothing left to give up."""
        weight = lambda d: d.get("res", 80) * d.get("steps", 60)
        w = weight(self.cfg)
        lower = [i for i, (_, p) in enumerate(PRESETS) if weight(p) < w]
        if not lower:
            self.say("Já está na qualidade mais baixa. Feche outros programas que usam a placa de vídeo")
            return False
        new = max(lower)
        self.set_value("preset", new, announce=False)
        self.say(f"Qualidade: {PRESETS[new][0]}. Para voltar, use Sistema › Imagem")
        return True

    def fix(self, kind):
        """The button of a warning of the Palco."""
        if kind == "sound":
            self.open_sys(1)                                                  # Tela e áudio: where the sound input is chosen
        elif kind == "quality":
            self.lower_quality()

    def shortcut(self, ch, live_scene=0, osd=True):
        """Keys that work from both windows: 1..9 bring that scene to the picture (at the moment "Quando troca sozinha" says), A turns the automatic
        change of scenes on or off. Returns True when the key was used."""
        if not ch or self.text_focus:
            return False
        if ch in "123456789" and len(ch) == 1:
            self.play_scene(int(ch) - 1, osd=osd)
            return True
        if ch.lower() == "a":
            self.live_scene = live_scene
            self.toggle_auto()
            return True
        if ch.lower() == "l":                                                    # Live: the edits of the Estúdio show on the big picture
            self.set_value("live", not self.cfg.get("live", False))
            return True
        if ch.lower() == "t":                                                    # tap tempo: tap the beat of the music
            self.request_tap()
            return True
        return False

    def request_tap(self):
        """A tap of the tap tempo (the T key of either window, the TAP of the Palco, a controller): the main loop gives it to the analyser (apply_taps)."""
        now = time.perf_counter()
        self.taps.append(now)
        self.tap_t = now

    def apply_taps(self, an):
        """The taps and the "back to automatic" asked for since the last frame go to the analyser (the main loop calls this before it updates it)."""
        for t in self.taps:
            an.tap(t)
        self.taps.clear()
        if self.tap_release:
            an.release_tap()
            self.tap_release = False

    def share_path(self):
        """Where the scenes are exported to and imported from: Documents\\AudioOrganism\\cenas.json."""
        base = os.environ.get("VIS_SHAREDIR") or os.path.join(os.path.expanduser("~"), "Documents", "AudioOrganism")
        return os.path.join(base, "cenas.json")

    def export_scenes(self):
        """Write the scenes with the palettes and shaders they use, to a file that can be shared."""
        self.store_scene()
        path = self.share_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"app": "AudioOrganism", "scenes": self.cfg["scenes"], "palettes": self.cfg["palettes"], "shaders": self.cfg["shaders"]}, f, indent=1, ensure_ascii=False)
            self.say("Cenas exportadas")
            return path
        except Exception as e:
            self.say(f"Não deu para exportar: {e}")
            return None

    def import_scenes(self):
        """Add the scenes of the exported file to the gallery, with their palettes and shaders (the numbers of the palette / shader are remapped)."""
        path = self.share_path()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            scenes = [s for s in data.get("scenes", []) if SC.valid(s)]
            raw_pals, raw_shs = list(data.get("palettes", [])), list(data.get("shaders", []))
        except FileNotFoundError:
            self.say("Não achei o arquivo cenas.json em Documentos\\AudioOrganism")
            return 0
        except Exception as e:
            self.say(f"Arquivo inválido: {e}")
            return 0
        if not scenes:
            self.say("O arquivo não tem cenas")
            return 0
        base = SC.mandala_scene(0, {k: self.cfg[k] for k in SC.EXTRA_KEYS if k in self.cfg})
        p_map, s_map = {}, {}                                           # the file's palette / shader number -> the number it gets here
        for i, pal in enumerate(raw_pals):
            if PAL.valid(pal):
                self.cfg["palettes"].append(pal)
                p_map[i + 1] = len(self.cfg["palettes"])
        for i, sh in enumerate(raw_shs):
            if SP.valid(sh):
                self.cfg["shaders"].append(sh)
                s_map[i + 1] = len(self.cfg["shaders"])
        for sc in scenes:
            LY.migrate(sc)
            for k, v in base.items():
                sc.setdefault(k, v)
            sc["scene_palette"] = p_map.get(int(sc.get("scene_palette", 0)), 0)      # a palette the file does not carry falls back to the character's own
            sc["scene_shader"] = s_map.get(int(sc.get("scene_shader", 0)), 0)
            sc["scene_name"] = (str(sc["scene_name"]) + " (importada)")[:28]
            self.cfg["scenes"].append(sc)
        self.rebuild_scenes()
        self.touch()
        self.say(f"{len(scenes)} cena(s) importada(s)")
        return len(scenes)

    def new_scene(self):
        """"Nova cena": a mandala with no layers, straight in the editor of layers."""
        self._push()
        base = {k: self.cfg[k] for k in SC.EXTRA_KEYS if k in self.cfg}
        names = {s.get("scene_name") for s in self.cfg["scenes"]}
        n = 1
        while ("Nova cena" if n == 1 else f"Nova cena {n}") in names:
            n += 1
        new = SC.blank_scene(base, "Nova cena" if n == 1 else f"Nova cena {n}")
        self.cfg["scenes"].append(new)
        self._eff_before = self.cfg["effect"]
        self.scene_view = "gallery"
        self.open_scene(len(self.cfg["scenes"]) - 1)
        self.cfg["ed_item"], self.cfg["ed_page"] = (4 if self.cfg.get("advanced") else 0), False              # the overview: the list of layers is empty and the add menu is right there
        self.cfg["ly_sel"] = 0
        self.rebuild_scenes()
        self.say("Nova cena: adicione camadas")

    def edit_live_scene(self):
        """The Palco's "Editar esta cena": the Estúdio opens on the scene that is on the air. If that scene (or another one) is already open the unsaved changes stay."""
        scn = self.cfg["scenes"]
        if not scn:
            return
        i = max(0, min(int(self.live_scene), len(scn) - 1))
        self.press("tab%d" % TAB_SCENES)
        if self.scene_view == "editor":
            if i == self.cfg["scene_edit"]:
                return
            if self.is_dirty():
                self.say("Alterações não salvas em " + scn[self.cfg["scene_edit"]]["scene_name"] + ": Salvar ou Descartar antes de abrir outra cena")
                return
        self.open_scene(i)

    def add_preset(self, i):
        """A new Mandala scene with preset i: it joins the scenes and opens in the editor, on the Visual section."""
        self._push()
        if not 0 <= i < len(self.preset_templates):
            return
        new = copy.deepcopy(self.preset_templates[i])
        self.cfg["scenes"].append(new)
        self._eff_before = self.cfg["effect"]
        self.scene_view = "gallery"
        self.open_scene(len(self.cfg["scenes"]) - 1)
        self.cfg["ed_item"], self.cfg["ed_sub"], self.cfg["ed_page"] = 0, 0, False
        self.rebuild_scenes()
        self.say(f"Cena criada: {new['scene_name']}")

    def delete_scene(self, i):
        """Remove scene i from the gallery (there is always at least one)."""
        self._push()
        scn = self.cfg["scenes"]
        if len(scn) <= 1 or not 0 <= i < len(scn):
            return False
        name = scn[i]["scene_name"]
        del scn[i]
        eff = self.cfg["effect"]
        self.cfg["effect"] = 0 if eff == i + 1 else (eff - 1 if eff > i + 1 else eff)
        ed = self.cfg["scene_edit"]
        self.cfg["scene_edit"] = max(0, min(ed - 1 if ed > i else ed, len(scn) - 1))
        if self.scene_view == "editor" and ed == i:                           # the scene that was open is gone: the editor takes the one that is left in its place
            self.draft = copy.deepcopy(scn[self.cfg["scene_edit"]])
            self.leave_armed = 0.0
            SC.apply_scene(self.cfg, self.draft)
        else:
            SC.apply_scene(self.cfg, self.draft if (self.scene_view == "editor" and self.draft is not None) else scn[self.cfg["scene_edit"]])
        self.rebuild_scenes()
        self.touch()
        self.say(f"Cena apagada: {name}")
        return True

    def switch_scene(self, i):
        """In the wide Estúdio: edit scene i. With unsaved changes in the one that is open the first click only warns. The item on the right stays where it was."""
        scn = self.cfg["scenes"]
        if not 0 <= i < len(scn):
            return
        if self.scene_view == "editor" and i == self.cfg["scene_edit"]:
            return
        now = time.perf_counter()
        if self.scene_view == "editor" and self.is_dirty() and now > self.leave_armed:
            self.leave_armed = now + 4.0
            self.say("Alterações não salvas: Salvar, Descartar, ou clique de novo para trocar mesmo assim")
            self.need = True
            return
        item, sub = int(self.cfg.get("ed_item", 0)), int(self.cfg.get("ed_sub", 0))
        keep = self.scroll
        self.open_scene(i)
        self.scroll = keep
        if item == 4 and not self.cfg.get("layers"):
            item = 0
        self.cfg["ed_item"], self.cfg["ed_sub"] = item, sub
        self.cfg["ly_sel"] = max(0, min(int(self.cfg.get("ly_sel", 0)), len(self.cfg.get("layers") or []) - 1))
        LY.load_lp(self.cfg)
        self.rebuild_scenes()

    def scene_action(self, arg):
        """A click on a row of the list of scenes: (what, index)."""
        what, i = arg
        scn = self.cfg["scenes"]
        if not 0 <= i < len(scn):
            return
        now = time.perf_counter()
        if what == "sel":
            self.switch_scene(i)
        elif what == "menu":
            self.dd_open = f"scm:{i}"
            self.dd_hl = 0
            self.need = True
        elif what == "play":
            self.play_scene(i)
        elif what == "dup":
            self.duplicate_scene(i)
        elif what == "del":
            if len(scn) <= 1:
                self.say("Fica pelo menos uma cena")
            elif self.del_armed[0] == i and self.del_armed[1] > now:
                self.del_armed = (-1, 0.0)
                self.delete_scene(i)
            else:
                self.del_armed = (i, now + 3.0)
                self.say(f"Clique de novo para apagar {scn[i]['scene_name']}")
            self.need = True

    def toggle_auto(self, on=None):
        """Troca automática: on = the program chooses the scenes; off = the scene on the air stays."""
        eff = self.cfg["effect"]
        want = (eff != 0) if on is None else bool(on)
        if want == (eff == 0):
            return
        self.cfg["effect"] = 0 if want else min(int(self.live_scene), len(self.cfg["scenes"]) - 1) + 1
        self.touch()
        self.say("Troca automática: " + ("ligada" if want else "desligada (cena fixa)"))

    def add_scene(self, t):
        """A new scene from template t of the picker: it joins the scenes and opens in the editor."""
        self._push()
        if not 0 <= t < len(self.templates):
            return
        new = copy.deepcopy(self.templates[t])
        self.cfg["scenes"].append(new)
        self._eff_before = self.cfg["effect"]
        self.scene_view = "gallery"
        self.open_scene(len(self.cfg["scenes"]) - 1)
        self.say(f"Cena criada: {new['scene_name']}")

    def select_scene(self, i):
        scn = self.cfg["scenes"]
        i = max(0, min(i, len(scn) - 1))
        self.cfg["scene_edit"] = i
        SC.apply_scene(self.cfg, scn[i])
        self.rebuild_scenes()

    # ------------------------------------------------------------ state
    def _push(self):
        """Snapshot of everything the editors change, for Desfazer."""
        self.store_scene()
        c = self.cfg
        self.undo.append(copy.deepcopy((c["scenes"], c["shaders"], c["palettes"], c["scene_edit"], self.draft)))
        del self.undo[:-40]
        self._push_t = time.perf_counter()

    def sys_push(self, label, keys=None, restore=None):
        """Remembers what a Sistema action is about to change, so the toast can offer Desfazer. `keys`: settings to put back
        (None = every setting, lists and dicts restored in place); `restore`: a function that undoes by itself (a file)."""
        c = self.cfg
        if restore is None:
            snap = copy.deepcopy({k: c[k] for k in (keys if keys is not None else list(c)) if k in c})

            def restore():
                for k, v in snap.items():
                    cur = c.get(k)
                    if isinstance(cur, list) and isinstance(v, list):
                        cur[:] = v
                    elif isinstance(cur, dict) and isinstance(v, dict):
                        cur.clear()
                        cur.update(v)
                    else:
                        c[k] = v
                if "scenes" in snap:
                    c["scene_edit"] = max(0, min(int(c["scene_edit"]), len(c["scenes"]) - 1))
                    SC.apply_scene(c, c["scenes"][c["scene_edit"]])
                self.rebuild_scenes()
                self.touch()
        self.sys_undo.append((time.perf_counter(), label, restore))
        del self.sys_undo[:-10]

    def _snap(self, cid):
        """One snapshot per burst of changes of the same control (a slider drag is one step to undo, not fifty)."""
        if not (cid in SC.SCENE_KEYS or cid.startswith(("shd_", "pal_", "bgc_", "lp_"))) or cid in ("scene_sec", "shd_edit", "pal_edit", "shd_item", "pal_item", "bgc_item"):
            return
        now = time.perf_counter()
        last_cid, last_t = self._undo_last
        self._undo_last = (cid, now)
        if cid == last_cid and now - last_t < 1.0:
            return
        self._push()

    def undo_last(self):
        if self.sys_undo and (not self.undo or self.sys_undo[-1][0] >= self._push_t):       # the newest action wins
            _, label, restore = self.sys_undo.pop()
            restore()
            self.toast = None
            self.say(f"Desfeito: {label}")
            return
        if not self.undo:
            self.say("Nada para desfazer")
            return
        sc, sh, pa, ed, dr = self.undo.pop()
        c = self.cfg
        c["scenes"][:], c["shaders"][:], c["palettes"][:] = sc, sh, pa
        c["scene_edit"] = max(0, min(ed, len(sc) - 1))
        c["shd_edit"] = max(0, min(int(c["shd_edit"]), len(sh) - 1))
        c["pal_edit"] = max(0, min(int(c["pal_edit"]), len(pa) - 1))
        if self.scene_view == "editor" and dr is not None:
            self.draft = dr
            SC.apply_scene(c, dr)
        else:
            SC.apply_scene(c, c["scenes"][c["scene_edit"]])
        load_shader_edit(c)
        load_palette_edit(c)
        self._undo_last = (None, 0.0)
        self.rebuild_scenes()
        self.touch()
        self.say("Desfeito")

    def profile_save(self):
        self.store_scene()
        try:
            os.makedirs(settings.PROFILE_DIR, exist_ok=True)
            path = profile_path(self.cfg["profile"])
            old = None
            if os.path.exists(path):
                with open(path, "rb") as f:
                    old = f.read()

            def put_back(path=path, old=old):                                # Desfazer: the profile that was there (or none)
                if old is None:
                    if os.path.exists(path):
                        os.remove(path)
                else:
                    with open(path, "wb") as f:
                        f.write(old)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=1)
            if old is not None:
                self.sys_push(f"perfil {self.cfg['profile']} salvo", restore=put_back)
            self.say(f"Perfil {self.cfg['profile']} salvo", undo=old is not None)
        except Exception as e:
            self.say("Não consegui salvar o perfil")
            self.problem("profile", f"Perfil não salvo: {str(e)[:50]}")
            return
        self.problem("profile")
        self.rebuild_scenes()

    def profile_load(self):
        p = profile_path(self.cfg["profile"])
        if not os.path.exists(p):
            return
        self.store_scene()
        self.sys_push(f"perfil {self.cfg['profile']} carregado")
        keep = {k: self.cfg[k] for k in ("fullscreen", "profile", "safe_flash", "safe_motion")}      # the comfort limits belong to the person, not to the profile
        new = load_cfg(p)
        new.update(keep)
        new["effect"] = 0
        self.cfg.update(new)
        self.cfg["scene_edit"] = max(0, min(self.cfg["scene_edit"], len(self.cfg["scenes"]) - 1))
        SC.apply_scene(self.cfg, self.cfg["scenes"][self.cfg["scene_edit"]])
        self.scene_view = "gallery"
        self.rebuild_scenes()
        self.touch()
        self.say(f"Perfil {self.cfg['profile']} carregado", undo=True)

    # ------------------------------------------------------------ layers
    def _layers(self):
        return self.cfg.setdefault("layers", [])

    def _layers_changed(self, sel=None, open_page=False):
        if sel is not None:
            self.cfg["ly_sel"] = max(0, min(sel, len(self._layers()) - 1))
            self.cfg["ed_item"] = settings.layer_item(self.cfg) if self._layers() else 0
            if open_page:
                self.cfg["ed_page"] = True
                self.reset_scroll(inspector=True)
        LY.load_lp(self.cfg)
        self.store_scene()
        self.rebuild_scenes()
        self.touch()

    def add_layer(self, t):
        layers = self._layers()
        fx, bg = LY.counts(layers)
        info = LY.TYPES.get(t)
        if info is None:
            return
        if info["group"] == "fx" and fx >= LY.MAX_FX:
            self.say(f"No máximo {LY.MAX_FX} efeitos por cena")
            return
        if info["group"] == "bg" and bg >= LY.MAX_BG:
            self.say(f"No máximo {LY.MAX_BG} fundos por cena")
            return
        if t in ("fb", "part") and any(l.get("t") == t for l in layers):
            self.say("Só um " + ("rastro" if t == "fb" else "conjunto de partículas") + " por cena")
            return
        self._push()
        layers.append(LY.new_layer(t))
        self._layers_changed(len(layers) - 1, open_page=True)               # a new layer opens on its own page
        self.say(f"{info['label']} adicionada")

    def apply_stack_template(self, i):
        self._push()
        self.cfg["layers"] = LY.apply_template(self._layers(), i)
        self._layers_changed(0)
        self.say(f"Modelo: {LY.TEMPLATES[max(0, min(len(LY.TEMPLATES) - 1, i))][0]}")

    def layer_action(self, arg):
        """A click on a row of the list of layers: (what, index). The list shows the top layer first."""
        what, i = arg
        layers = self._layers()
        if not 0 <= i < len(layers):
            return
        if what == "sel":
            self.cfg["ly_sel"] = i
            self.cfg["ed_item"] = settings.layer_item(self.cfg)
            self.cfg["ed_page"] = True                                    # the page of the layer
            self.reset_scroll(inspector=True)
            LY.load_lp(self.cfg)
            self.rebuild_scenes()
            return
        self._push()
        if what == "eye":
            layers[i]["on"] = not layers[i].get("on", True)
            self._layers_changed(i)
        elif what in ("up", "down"):
            j = i + 1 if what == "up" else i - 1
            if 0 <= j < len(layers):
                layers[i], layers[j] = layers[j], layers[i]
                self._layers_changed(j)
        elif what == "dup":
            fx, bg = LY.counts(layers)
            t = layers[i].get("t")
            if (LY.TYPES[t]["group"] == "fx" and fx >= LY.MAX_FX) or (LY.TYPES[t]["group"] == "bg" and bg >= LY.MAX_BG) or t in ("fb", "part"):
                self.say("Esta camada não pode ser duplicada")
                self.undo.pop()
                return
            layers.insert(i + 1, copy.deepcopy(layers[i]))
            self._layers_changed(i + 1)
        elif what == "del":
            del layers[i]
            self._layers_changed(min(i, len(layers) - 1))

    def touch(self):
        self.dirty = self.need = True
        self.dirty_t = time.perf_counter()

    def panes(self):
        """True when the tab is drawn as two columns that scroll on their own (the wide Estúdio and Sistema)."""
        cols = self.cols.get(self.tab)
        return bool(cols) and len(cols) == len(TABS[self.tab][1])

    def pane_dims(self):
        """(height of what stays fixed under the tab bar, height of the left column, height of the right one), cards and gaps included."""
        tot = {"F": 0, "L": 0, "R": 0}
        wl, wr, _g = self._col_widths()
        wcol = {"F": self.W, "L": wl, "R": wr}
        for (ttl, rows), col in zip(TABS[self.tab][1], self.cols.get(self.tab) or []):
            tot[col] += self._card_h(rows, ttl, wcol[col]) + self.GAP
        return tot["F"], tot["L"], tot["R"]

    def pane_view_h(self):
        return max(60, self.content_h() - self.pane_dims()[0])

    def max_scroll(self, pane=0):
        """How far the content scrolls. In two columns: pane 0 is the left one and 1 the right one."""
        if self.panes():
            _, hl, hr = self.pane_dims()
            return max(0, (hr if pane else hl) - self.pane_view_h())
        return max(0, self.heights[self.tab] - self.view_h + self.reserved)

    def clamp_scroll(self):
        self.scroll = max(0, min(self.scroll, self.max_scroll(0)))
        self.scroll2 = max(0, min(self.scroll2, self.max_scroll(1))) if self.panes() else 0

    def in_right_pane(self, x):
        return self.panes() and x >= self.side_w() + self._col_widths()[0] + self._col_widths()[2] // 2

    def surf_y_at(self, x, y):
        """The y on the panel's surface of a point at (x, y), y counted from the top of the panel with the preview strip taken out (so the tab bar is HEAD high)."""
        if self.panes():
            fixed = self.HEAD + self.pane_dims()[0]
            if y < fixed:
                return y
            return y + (self.scroll2 if self.in_right_pane(x) else self.scroll)
        return y + self.scroll

    def content_h(self):
        """Height of the scrolling area: the window minus the tab bar and the preview strip (when the tab has one)."""
        return self.view_h - self.HEAD - self.reserved

    def scroll_to_focus(self):
        if not self.order:
            return
        fr = self.frects.get(self.order[self.focus % len(self.order)])
        if fr is None:
            return
        if self.panes():
            fixed = self.HEAD + self.pane_dims()[0]
            if fr.top < fixed:
                return                                                       # the tab bar and the bar of the editor never scroll
            right = self.in_right_pane(fr.x)
            cur = self.scroll2 if right else self.scroll
            vh = self.pane_view_h()
            if fr.top < fixed + cur + 8:
                cur = max(0, fr.top - fixed - 8)
            elif fr.bottom > fixed + cur + vh - 8:
                cur = min(self.max_scroll(1 if right else 0), fr.bottom - fixed - vh + 8)
            if right:
                self.scroll2 = cur
            else:
                self.scroll = cur
            return
        top = self.HEAD + self.scroll
        if fr.top < top + 8:
            self.scroll = max(0, fr.top - self.HEAD - 8)
        elif fr.bottom > top + self.content_h() - 8:
            self.scroll = min(self.max_scroll(), fr.bottom - self.HEAD - self.content_h() + 8)

    def set_live(self, text):
        """Short live status ("96 FPS · 1280×720 · 80%") shown in the header of the Gráficos tab."""
        if text != self.live:
            self.live = text
            if self.pv_mode() == "live":
                self.need = True

    def problem(self, key, text=None):
        """Raise (text) or clear (None) a persistent warning, shown as a red strip over the panel instead of a modal box."""
        if text:
            self.problems[key] = text
        else:
            self.problems.pop(key, None)

    def say(self, text, undo=False):
        """The confirmation toast. With `undo` it stays longer and shows a Desfazer button (it runs undo_last)."""
        self.toast = (text, time.perf_counter() + (7.0 if undo else 2.2), bool(undo))
        self.need = True

    def enabled(self, row):
        fn = row.get("enabled")
        return True if fn is None else bool(fn(self.cfg))

    def _scm_opts(self, i):
        """The ••• menu of a scene of the list: what it can do besides being edited (a click on the row)."""
        scn = self.cfg["scenes"]
        armed = self.del_armed[0] == i and self.del_armed[1] > time.perf_counter()
        return ([("Tocar agora", "play")] if i != self.live_i else []) + [("Duplicar", "dup")] + ([("Apagar mesmo?" if armed else "Apagar", "del")] if len(scn) > 1 else [])

    def find(self, cid):
        if isinstance(cid, str) and cid.startswith("scm:"):
            return dict(id=cid, kind="dd", label="", help="", opts=self._scm_opts(int(cid[4:])))
        if isinstance(cid, str) and cid in SC.LAYER_ON_KEYS:                    # the switch of a layer of the stack of the editor
            return dict(id=cid, kind="toggle", label=next(n for k, n, _ in LY.SLOTS if "ly_" + k == cid), help="")
        for _, secs in TABS:
            for _, rows in secs:
                for r in rows:
                    if r["id"] == cid:
                        return r
        if self._extra is None:                                   # the pages of Sistema that are not open
            self._extra = {}
            for k in range(len(SYS_ITEMS)):
                for _, rows in sys_cards(self.cfg, k, self.audio_devices, self.monitors, self):
                    for r in rows:
                        self._extra.setdefault(r["id"], r)
        return self._extra.get(cid)

    def set_value(self, cid, value, announce=True):
        if cid in ("safe_flash", "safe_motion") and int(value) < int(self.cfg[cid]):      # lowering a comfort limit: done at once, and the toast offers Desfazer
            self.sys_push("limite de conforto", [cid])
            self.cfg[cid] = value
            self.touch()
            self.say("Limite de conforto reduzido", undo=True)
            return None
        if cid == "lang":                                                        # the language of the panel: everything is drawn again in it
            self.cfg["lang"] = value
            i18n.set_lang(value)
            self.touch()
            self.rebuild_scenes()
            self.need = True
            return None
        if cid.startswith("scm:"):                                               # an option of the ••• menu of a scene
            self.dd_open = None
            return self.scene_action((value, int(cid[4:])))
        if cid.startswith("m_sym"):                                              # the preview shows the fold of the symmetry touched last
            self.preview_sym = 8 if cid == "m_symnone" else int(cid[5:])
        if cid == "ly_add":
            return self.add_layer(value)
        if cid == "ly_tpl":
            return self.apply_stack_template(int(value))
        if cid == "lib":                                                         # the menu of the library of scenes: export, import, factory scenes
            self.dd_open = None
            return self.press(("scenes_export", "scenes_import", "scenes_restore")[int(value) % 3])
        if cid == "sc_filter":                                                   # which scenes the list shows
            self.cfg["sc_filter"] = int(value)
            self.rebuild_scenes()
            self.need = True
            return None
        if cid.startswith("sc_auto:"):                                           # a switch of the Automático page: may the program bring this scene?
            return self.set_scene_auto(int(cid[8:]), bool(value))
        if cid in ("scene_sec", "sys_item"):
            announce = False                                     # changing section says nothing (the toast would cover the tab bar)
        if cid == "autoall":
            return self.toggle_auto(bool(value))
        if cid == "live":
            return self.set_live_edit(bool(value))
        if cid == "ed_tab":
            settings.ed_tab_apply(self.cfg, int(value))
            self.dd_open = None
            self.reset_scroll(inspector=True)
            self.rebuild_scenes()
            self.touch()
            return None
        if cid == "preset":
            if value == CUSTOM:                                                  # every value stays as it is; the options of the picture show up to be changed
                self.cfg["preset"] = CUSTOM
                self.rebuild_scenes()
                self.touch()
                if announce:
                    self.say("Qualidade: Personalizado")
                return
            if not (0 <= value < len(PRESETS)):
                return
            self.cfg.update(PRESETS[value][1])
            self.cfg["preset"] = value
            self.rebuild_scenes()                                                # and a shortcut hides them again
            self.touch()
            if announce:
                self.say(f"Qualidade: {PRESETS[value][0]}")
            return
        if cid == "movement":
            if value == MV_MANUAL or not (0 <= value <= MV_AUTO) or self.cfg["movement"] == value:
                return
            if value < len(MV_PRESETS):
                self.cfg.update(MV_PRESETS[value][1])
            self.cfg["movement"] = value
            self.touch()
            if announce:
                self.say(f"Movimento: {MV_OPTS[value][0]}")
            return
        if cid == "camera":
            if value == CAM_MANUAL or not (0 <= value <= CAM_AUTO) or self.cfg["camera"] == value:
                return
            if value < len(CAM_PRESETS):
                self.cfg.update(CAM_PRESETS[value][1])
            self.cfg["camera"] = value
            self.touch()
            if announce:
                self.say(f"Câmera: {CAM_OPTS[value][0]}")
            return
        if self.cfg.get(cid) == value:
            return
        self._snap(cid)
        self.cfg[cid] = value
        if cid == "scene_shader":
            self.store_scene()
            if value >= 1:
                self.select_shader(value - 1)
            self.rebuild_scenes()
        elif cid in ("shd_name", "shd_kind", "shd_p1", "shd_p2", "shd_p3", "shd_auto", "shd_duo"):
            sh = self._shd()
            key = {"shd_name": "name", "shd_kind": "kind", "shd_p1": "p1", "shd_p2": "p2", "shd_p3": "p3", "shd_auto": "auto", "shd_duo": "duo_mode"}[cid]
            sh[key] = str(value)[:28] if cid == "shd_name" else value
            if cid in ("shd_name", "shd_kind", "shd_auto", "shd_duo"):
                self.rebuild_scenes()
        elif cid == "shd_item":
            load_shader_edit(self.cfg)
            self.rebuild_scenes()
        elif cid in ("shd_r", "shd_g", "shd_b"):
            self._shd()["duo_dark" if self.cfg["shd_item"] == 0 else "duo_light"] = [self.cfg["shd_r"], self.cfg["shd_g"], self.cfg["shd_b"]]
            self.rebuild_scenes()
        elif cid == "scene_palette":
            self.store_scene()
            if value >= 1:
                self.select_palette(value - 1)
            self.rebuild_scenes()
        elif cid == "pal_name":
            self._pal()["name"] = str(value)[:28]
            self.rebuild_scenes()
        elif cid == "pal_item":
            load_palette_edit(self.cfg)
            self.rebuild_scenes()
        elif cid in ("pal_r", "pal_g", "pal_b"):
            lst, idx = PAL.item_ref(self._pal(), self.cfg["pal_item"])
            lst[idx] = [self.cfg["pal_r"], self.cfg["pal_g"], self.cfg["pal_b"]]
            self.rebuild_scenes()
        elif cid == "sys_item":
            self.cfg["search"] = ""                                              # a click on a category leaves the search
            self.scroll = self.scroll2 = 0
            self.rebuild_scenes()
        elif cid == "scene_sec":
            self.scroll = self.scroll2 = 0
            self.rebuild_scenes()
        elif cid == "scene_preset":                                              # a mandala preset: its numbers become the scene's
            SC.apply_preset(self.cfg, int(value))
            self.store_scene()
            self.rebuild_scenes()
        elif cid in ("ed_sub", "ed_item"):
            if cid == "ed_sub" and value == 3 and self.preview_sym is None:
                self.preview_sym = next((k for k in range(SC.SYM_COUNT) if self.cfg.get("m_sym%d" % k)), None)
            self.scroll = min(self.scroll, 0) if cid == "ed_item" else self.scroll
            self.rebuild_scenes()
        elif cid == "ly_sel":
            LY.load_lp(self.cfg)
            self.rebuild_scenes()
        elif cid.startswith("lp_"):                                                 # a parameter of the layer being edited: it goes into the layer
            if LY.write_lp(self.cfg, cid, value):
                self.rebuild_scenes()
            self.store_scene()
        elif cid in ("ae_kind", "ae_part"):
            load_ae(self.cfg)
            self.rebuild_scenes()
        elif cid.startswith("ae_"):
            kind, part = ae_current(self.cfg)
            self.cfg["auto_sets"][kind][part][cid[3:]] = value
        elif cid == "search":
            self.rebuild_scenes()
        elif cid == "effect" and value >= 1:                                     # selecting a scene: it becomes the one being edited and shown
            self.cfg["scene_now"] = not self.cfg.get("scene_wait", 0)
            self.select_scene(value - 1)
        elif cid == "bgc_item":
            cols = self.cfg["bgc_cols"]
            self.cfg["bgc_r"], self.cfg["bgc_g"], self.cfg["bgc_b"] = cols[max(0, min(len(cols) - 1, int(value)))]
            self.rebuild_scenes()
        elif cid in ("bgc_r", "bgc_g", "bgc_b"):
            self.cfg["bgc_cols"][int(self.cfg["bgc_item"])] = [self.cfg["bgc_r"], self.cfg["bgc_g"], self.cfg["bgc_b"]]
            self.store_scene()
            self.rebuild_scenes()
        elif cid in SC.SCENE_KEYS:
            self.store_scene()
            if cid in ("scene_name", "scene_genre", "scene_visual", "scene_bg", "bgc_src") or cid.startswith("m_sym") or (cid.startswith("fx_") and cid.endswith("_src")):
                self.rebuild_scenes()
        elif cid == "scene_sec":
            self.scroll = self.scroll2 = 0
            self.rebuild_scenes()
        if cid == "cam_fov_min" and value > self.cfg["cam_fov_max"]:
            self.cfg["cam_fov_max"] = value
        if cid == "cam_fov_max" and value < self.cfg["cam_fov_min"]:
            self.cfg["cam_fov_min"] = value
        if cid in CAM_KEYS and self.cfg["camera"] != CAM_AUTO:
            self.cfg["camera"] = match_camera(self.cfg)
            self.store_scene()
        if cid in MV_KEYS and self.cfg["movement"] != MV_AUTO:
            self.cfg["movement"] = match_movement(self.cfg)
            self.store_scene()
        if cid in GFX_KEYS and (self.cfg.get("advanced") or self.cfg["preset"] != CUSTOM):
            self.cfg["preset"] = match_preset(self.cfg)                         # (in the simple mode Personalizado stays until a shortcut is chosen: the options would hide under the pointer)
        self.touch()
        row = self.find(cid) if announce else None
        if row:
            if row["kind"] == "toggle":
                self.say(f"{NAMES.get(cid, cid)}: {'ligado' if value else 'desligado'}")
            elif row["kind"] == "seg":
                lbl = next((l for l, v in row["opts"] if v == value), str(value))          # a row may share its id with another one that has the other options
                self.say(f"{NAMES.get(cid, cid)}: {lbl}" + ("  ·  reinicie para aplicar" if cid == "backend" else ""))

    def adjust(self, cid, d):
        row = self.find(cid)
        if row is None or not self.enabled(row):
            return
        if row["kind"] == "toggle":
            cur = row["get"](self.cfg) if "get" in row else self.cfg[cid]
            self.set_value(cid, d > 0 if d != 0 else not cur)
        elif row["kind"] == "seg":
            vals = [v for _, v in row["opts"]]
            i = vals.index(self.cfg[cid]) if self.cfg[cid] in vals else 0
            self.set_value(cid, vals[max(0, min(len(vals) - 1, i + d))])
        elif row["kind"] == "slider":
            v = max(row["lo"], min(row["hi"], self.cfg[cid] + d * row["step"]))
            self.set_value(cid, v, announce=False)

    def slider_from_x(self, cid, x):
        row = self.find(cid)
        tl, tw = self.slider_geos.get(cid) or self.slider_geo
        t = max(0.0, min(1.0, (x - tl) / tw))
        v = row["lo"] + t * (row["hi"] - row["lo"])
        m = (self.cfg.get("mods") or {}).get(cid) if self.scene_view == "editor" else None
        if m is not None:                                                 # a range: the handle nearest to the click moves (and keeps moving while dragged)
            v = int(round(v / row["step"]) * row["step"])
            if getattr(self, "mod_end", None) is None:
                self.mod_end = "lo" if abs(v - m["lo"]) <= abs(v - m["hi"]) else "hi"
            m[self.mod_end] = v
            self.store_scene()
            self.need = True
            return
        self.set_value(cid, int(round(v / row["step"]) * row["step"]), announce=False)

    def press(self, cid):
        """Activate a button; returns an action string for the caller."""
        now = time.perf_counter()
        if cid.startswith("tab"):
            if int(cid[3:]) == TAB_SCENES and self.tab == TAB_SCENES and self.scene_view != "gallery":
                return self.back_to_gallery()                         # the Estúdio tab again: back to the gallery (in a narrow window)
            self.tab = self.cfg["ui_tab"] = max(0, min(int(cid[3:]), len(TABS) - 1))
            self.scroll = self.scroll2 = 0
            if self.tab == TAB_SCENES and self.scene_view == "gallery" and self.cfg.get("scenes"):
                # coming to the Estúdio from another tab: straight into the scene being edited (or the one on the air), not the gallery
                self.open_scene(max(0, min(int(self.cfg.get("scene_edit", 0)), len(self.cfg["scenes"]) - 1)))
            self.rebuild_scenes()                                     # the wide Estúdio opens its editor
            self.need = True
            return None
        if cid == "shd_new":
            shs = self.cfg["shaders"]
            new = copy.deepcopy(shs[self.cfg["shd_edit"]])
            new["name"] = (new["name"] + " (cópia)")[:28]
            shs.append(new)
            self.cfg["scene_shader"] = len(shs)
            self.store_scene()
            self.select_shader(len(shs) - 1)
            self.touch()
            self.say("Shader duplicado: mexa à vontade")
            return None
        if cid == "shd_delete":
            shs = self.cfg["shaders"]
            if len(shs) > 1:
                gone = self.cfg["shd_edit"]
                del shs[gone]
                for sc_ in self.cfg["scenes"]:
                    if sc_.get("scene_shader", 0) == gone + 1:
                        sc_["scene_shader"] = 0
                    elif sc_.get("scene_shader", 0) > gone + 1:
                        sc_["scene_shader"] -= 1
                SC.apply_scene(self.cfg, self.cfg["scenes"][self.cfg["scene_edit"]])
                self.select_shader(min(gone, len(shs) - 1))
                self.touch()
                self.say("Shader apagado")
            return None
        if cid == "shd_factory":
            self.cfg["shaders"][:] = SP.factory()
            for sc_ in self.cfg["scenes"]:
                sc_["scene_shader"] = min(sc_.get("scene_shader", 0), len(self.cfg["shaders"]))
            self.select_shader(0)
            self.touch()
            self.say("Shaders de fábrica restaurados")
            return None
        if cid == "pal_new":
            pls = self.cfg["palettes"]
            new = copy.deepcopy(pls[self.cfg["pal_edit"]])
            new["name"] = (new["name"] + " (cópia)")[:28]
            pls.append(new)
            self.cfg["scene_palette"] = len(pls)
            self.store_scene()
            self.select_palette(len(pls) - 1)
            self.touch()
            self.say("Paleta duplicada: mexa à vontade")
            return None
        if cid == "pal_delete":
            pls = self.cfg["palettes"]
            if len(pls) > 1:
                gone = self.cfg["pal_edit"]
                del pls[gone]
                for sc_ in self.cfg["scenes"]:                         # scenes that used it (or a later one) are fixed
                    if sc_.get("scene_palette", 0) == gone + 1:
                        sc_["scene_palette"] = 0
                    elif sc_.get("scene_palette", 0) > gone + 1:
                        sc_["scene_palette"] -= 1
                SC.apply_scene(self.cfg, self.cfg["scenes"][self.cfg["scene_edit"]])
                self.select_palette(min(gone, len(pls) - 1))
                self.touch()
                self.say("Paleta apagada")
            return None
        if cid == "pal_factory":
            self.cfg["palettes"][:] = PAL.factory()
            for sc_ in self.cfg["scenes"]:
                sc_["scene_palette"] = min(sc_.get("scene_palette", 0), len(self.cfg["palettes"]))
            self.select_palette(0)
            self.touch()
            self.say("Paletas de fábrica restauradas")
            return None
        if cid.startswith("layer_on:"):                                           # the button of a layer that is off: turns it on (the switch of its row does the same)
            self.set_value("ly_" + cid[9:], True)
            return None
        if cid.startswith("goto:"):                                               # a link that was only a note: it takes you there
            self.goto(cid[5:])
            return None
        if cid in ("pal_add", "pal_add_bg"):
            pal = self._pal()
            (pal["bgs"] if cid == "pal_add_bg" else pal["colors"]).append([200, 200, 200])
            self.cfg["pal_item"] = len(PAL.items(pal)) - 1 if cid == "pal_add" else len(pal["bgs"]) - 1
            load_palette_edit(self.cfg)
            self.rebuild_scenes()
            self.touch()
            return None
        if cid == "pal_remove":
            pal = self._pal()
            lst, idx = PAL.item_ref(pal, self.cfg["pal_item"])
            if len(lst) > 1:
                del lst[idx]
                self.cfg["pal_item"] = max(0, self.cfg["pal_item"] - 1)
                load_palette_edit(self.cfg)
                self.rebuild_scenes()
                self.touch()
            else:
                self.say("A paleta precisa de pelo menos uma cor e um fundo")
            return None
        if cid == "ed_save":
            self.save_scene()
            return None
        if cid == "ed_discard":
            self.discard_scene()
            return None
        if cid == "lbar_add":                                                    # "+ Ajuste": the list of kinds of effect opens (its row is the last of the list)
            self.dd_open, self.dd_hl = "ly_add", 0
            self.dd_groups, self.dd_q = {"fx"}, ""                             # the first group opens, the others fold; the search starts empty
            self.need = True
            return None
        if cid.startswith("lbar_"):                                              # the toolbar over the list of effects: acts on the one selected
            what = {"lbar_up": "up", "lbar_down": "down", "lbar_dup": "dup", "lbar_del": "del"}[cid]
            self.layer_action((what, int(self.cfg.get("ly_sel", 0))))
            return None
        if cid == "undo":
            self.undo_last()
            return None
        if cid == "live_toggle":
            self.set_live_edit(not self.cfg.get("live"))
            return None
        if cid in ("profile_save", "profile_load"):
            getattr(self, cid)()
            return None
        if cid == "ae_reset":
            kind, part = ae_current(self.cfg)
            self.cfg["auto_sets"][kind][part] = {}
            load_ae(self.cfg)
            self.touch()
            self.say("Valores de fábrica")
            return None
        if cid == "advanced":
            self.cfg["advanced"] = not self.cfg.get("advanced", False)
            if not self.cfg["advanced"]:
                pass
                if int(self.cfg.get("ed_sub", 0)) in (2, 4):
                    self.cfg["ed_sub"] = 0
            self.scroll = self.scroll2 = 0
            self.dd_open = None
            self.rebuild_scenes()
            self.touch()
            self.say("Modo avançado: " + ("ligado" if self.cfg["advanced"] else "desligado"))
            return None
        if cid == "gen_pick":
            self.pick_image()
            return None
        if cid == "gen_clear":
            self.set_value("gen_img", "", announce=False)
            self.say("Imagem retirada: vale o texto")
            return None
        if cid == "scene_add":
            self.start_wizard()
            return None
        if cid == "scenes_export":
            self.export_scenes()
            return None
        if cid == "pal_open":                                                    # the editor of the palette: only when asked for
            self.cfg["pal_open"] = not self.cfg.get("pal_open")
            self.rebuild_scenes()
            self.need = True
            return None
        if cid == "scenes_import":
            self.import_scenes()
            return None
        if cid == "scenes_restore":
            if self.restore_armed > now:
                self.restore_armed = 0.0
                return self.press("scene_factory")
            self.restore_armed = now + 3.0
            self.say("Toque de novo para apagar as suas cenas e voltar às de fábrica")
            self.need = True
            return None
        if cid.startswith(("unmod:", "uncyc:")):                              # the Ligações page: this one stops following the music
            (self.cfg.get("mods" if cid.startswith("unmod:") else "cycles") or {}).pop(cid[6:], None)
            self.store_scene()
            self.rebuild_scenes()
            return None
        if cid == "ed_back":
            self.ed_back()
            return None
        if cid == "scene_back":
            return self.leave_editor()
        if cid == "scene_new":                                       # duplicate the scene being edited
            scn = self.cfg["scenes"]
            self.store_scene()
            new = copy.deepcopy(scn[self.cfg["scene_edit"]])
            new["scene_name"] = (new["scene_name"] + " (cópia)")[:28]
            scn.append(new)
            self.open_scene(len(scn) - 1)
            self.say("Cena duplicada: mexa à vontade")
            return None
        if cid == "scene_delete":
            scn = self.cfg["scenes"]
            if len(scn) > 1:
                gone = self.cfg["scene_edit"]
                del scn[gone]
                b_ = self._eff_before
                self._eff_before = 0 if b_ == gone + 1 else (b_ - 1 if b_ > gone + 1 else b_)
                self.cfg["scene_edit"] = min(gone, len(scn) - 1)
                SC.apply_scene(self.cfg, scn[self.cfg["scene_edit"]])
                self.close_scene()
                self.say("Cena apagada")
            return None
        if cid == "scene_factory":
            extras = {k: self.cfg[k] for k in SC.EXTRA_KEYS if k in self.cfg}
            self.cfg["scenes"][:] = SC.starter_scenes(extras)
            self.cfg["effect"] = 0
            self.cfg["scene_edit"] = 0
            SC.apply_scene(self.cfg, self.cfg["scenes"][0])
            self.scene_view = "gallery"
            self.rebuild_scenes()
            self.touch()
            self.say("Cenas de fábrica restauradas")
            return None
        if cid == "reset" and self.tab != TAB_SYS:
            return None
        if cid == "reset":
            keep = {k: self.cfg[k] for k in ("fullscreen",)}
            ids = {r["id"] for _, rows in TABS[self.tab][1] for r in rows if not r["id"].startswith(("sys_", "reset", "bench"))}
            base = fresh()
            if "camera" in ids:
                ids |= set(CAM_KEYS)
            if "movement" in ids:
                ids |= set(MV_KEYS)
            if "preset" in ids:
                ids |= set(GFX_KEYS) | set(FIN_KEYS)
            ids -= {"safe_flash", "safe_motion"} | set(SC.ACAB_KEYS)                # a reset never lowers the comfort limits, nor touches what each scene owns (Acabamento)
            self.sys_push("restaurar", [k for k in ids | {"preset", "camera", "movement"} if k in self.cfg])
            self.cfg.update({k: base[k] for k in ids if k in base})
            self.cfg["preset"] = match_preset(self.cfg)
            self.cfg["camera"] = match_camera(self.cfg) if self.cfg["camera"] != CAM_AUTO else CAM_AUTO
            self.cfg["movement"] = match_movement(self.cfg) if self.cfg["movement"] != MV_AUTO else MV_AUTO
            self.cfg.update(keep)
            self.rebuild_scenes()
            self.touch()
            self.say(f"Padrões de {SYS_ITEMS[int(self.cfg.get('sys_item', 0)) % len(SYS_ITEMS)][0].lower()} restaurados", undo=True)
            return None
        if cid == "fx_none":                                                       # all the heavy effects together: off if any is on, else back on
            keys = ("fx_glass", "fx_bloom", "fx_trail", "fx_parts")
            on = not any(self.cfg[k] for k in keys)
            self.sys_push("efeitos pesados", keys)
            self.cfg.update({k: on for k in keys})
            self.touch()
            self.say("Efeitos pesados ligados" if on else "Efeitos pesados desligados", undo=True)
            return None
        if cid in ("bench", "update_check", "update_apply"):
            return cid
        if cid == "quit":
            if self.quit_armed > now:
                return "quit"
            self.quit_armed = now + 3.0
            self.need = True
        return None

    def pick_image(self):
        """Opens the window of Windows to choose the logo (in a thread: the panel keeps working); the choice is taken in render()."""
        import threading

        def ask():
            try:
                from tkinter import Tk, filedialog
                root = Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                path = filedialog.askopenfilename(title="Escolha o logo ou a imagem", filetypes=[("Imagens", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("Todos", "*.*")])
                root.destroy()
                if path:
                    self._pending_img = path
            except Exception:
                self._pending_img = ""
                self.say("Não deu para abrir a janela. Ponha o arquivo logo.png em Documentos\\AudioOrganism")
        threading.Thread(target=ask, daemon=True).start()

    def set_macro(self, kind, idx):
        """A button of the Palco: "energy" / "speed" take a step of the tables, "pal" a palette (0 = each scene keeps its own), "reset" puts the three back."""
        c = self.cfg
        if kind == "reset":
            c["macro_energy"], c["macro_speed"], c["macro_pal"] = 100, 100, 0
            self.say("Intensidade, velocidade e cores voltaram ao normal")
        elif kind == "energy":
            c["macro_energy"] = MACRO_ENERGY[max(0, min(len(MACRO_ENERGY) - 1, int(idx)))][1]
        elif kind == "speed":
            c["macro_speed"] = MACRO_SPEED[max(0, min(len(MACRO_SPEED) - 1, int(idx)))][1]
        elif kind == "pal":
            c["macro_pal"] = max(0, min(len(c.get("palettes", [])), int(idx)))
            self.say("Cores: " + ("de cada cena" if c["macro_pal"] == 0 else c["palettes"][c["macro_pal"] - 1]["name"]))
        self.touch()

    def open_search(self):
        """Ctrl+F: the search field of Sistema, with the cursor in it."""
        self.tab = TAB_SYS
        self.scroll = self.scroll2 = 0
        self.rebuild_scenes()
        self.text_focus = "search"
        self.need = True

    # -------------------------------------------------------------- input
    def text_key(self, e):
        """Typing into the text field that has the focus. Returns True when the key was used."""
        if not self.text_focus:
            return False
        cid = self.text_focus
        v = str(self.cfg.get(cid, ""))
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE, pygame.K_TAB):
            self.text_focus = None
            if e.key == pygame.K_ESCAPE and cid == "search" and v:
                self.set_value("search", "", announce=False)                     # Esc in the search field brings the page back
        elif e.key == pygame.K_BACKSPACE:
            self.set_value(cid, v[:-1], announce=False)
        elif getattr(e, "unicode", "") and e.unicode.isprintable() and len(v) < 28:
            self.set_value(cid, v + e.unicode, announce=False)
        self.need = True
        return True

    def key(self, k, mod=0):
        self.kbd = True
        self.need = True
        n = len(self.order)
        if n == 0:
            return None
        if k == pygame.K_DOWN and self.dd_open:
            row_ = self.find(self.dd_open)
            self.dd_hl = min(len(row_["opts"]) - 1, self.dd_hl + 1)
        elif k in (pygame.K_DOWN, pygame.K_TAB):
            step = -1 if (k == pygame.K_TAB and mod & pygame.KMOD_SHIFT) else 1
            self.focus = (self.focus + step) % n
        elif k == pygame.K_UP and self.dd_open:
            self.dd_hl = max(0, self.dd_hl - 1)
        elif k == pygame.K_UP:
            self.focus = (self.focus - 1) % n
        elif k in (pygame.K_LEFT, pygame.K_RIGHT):
            cid = self.order[self.focus].split("#")[0]
            if cid.startswith("tab"):
                self.press(f"tab{max(0, min(len(TABS) - 1, self.tab + (-1 if k == pygame.K_LEFT else 1)))}")
            elif self.find(cid)["kind"] in ("text", "action", "dd", "layer", "note", "item", "scene"):
                pass
            elif self.find(cid)["kind"] == "radio":
                vals = [r["value"] for r in [x for _, rows in TABS[self.tab][1] for x in rows] if r["id"] == cid]
                i = vals.index(self.cfg[cid]) if self.cfg[cid] in vals else 0
                self.set_value(cid, vals[max(0, min(len(vals) - 1, i + (-1 if k == pygame.K_LEFT else 1)))])
            else:
                self.adjust(cid, -1 if k == pygame.K_LEFT else 1)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            fkey = self.order[self.focus]
            cid = fkey.split("#")[0]
            if cid in ("ed_save", "ed_discard", "scene_back", "advanced") or cid.startswith("tab"):
                return self.press(cid)
            row = self.find(cid)
            if row["kind"] == "action":
                return self.press(cid) if self.enabled(row) else None
            if row["kind"] == "dd" and self.enabled(row):
                if self.dd_open == cid:
                    self.dd_open = None
                    self.set_value(cid, row["opts"][self.dd_hl][1])
                else:
                    self.dd_open = cid
                    vals = [v for _, v in row["opts"]]
                    self.dd_hl = vals.index(self.cfg.get(cid)) if self.cfg.get(cid) in vals else 0
                return None
            if row["kind"] == "layer":
                self.layer_action(("sel", row["idx"]))
                return None
            if row["kind"] == "item":
                self.select_item(row["item"])
                return None
            if row["kind"] == "scene":
                self.scene_action(("sel", row["idx"]))
                return None
            if row["kind"] == "text":
                self.text_focus = cid
            elif row["kind"] == "radio":
                self.set_value(cid, self.order_val[self.focus % len(self.order)])
            elif row["kind"] == "toggle":
                self.adjust(cid, 0)
            elif row["kind"] == "seg":
                vals = [v for _, v in row["opts"]]
                i = vals.index(self.cfg[cid]) if self.cfg[cid] in vals else 0
                if self.enabled(row):
                    self.set_value(cid, vals[(i + 1) % len(vals)])
        elif k == pygame.K_ESCAPE:
            if self.dd_open:
                self.dd_open = None
                return None
            if self.tab == TAB_SCENES and self.scene_view != "gallery" and not self.workspace():
                return self.back_to_gallery()
            self.kbd = False
        self.scroll_to_focus()
        return None

    def hit_at(self, pos):
        for rect, cid, kind, arg in reversed(self.hits):
            if rect.collidepoint(pos):
                return rect, cid, kind, arg
        return None

    def mouse(self, ev, ox, oy, scale):
        if ev.type == pygame.MOUSEWHEEL:
            self.dd_open = None
            if self.hover and self.find(self.hover) and self.find(self.hover)["kind"] == "slider":
                self.adjust(self.hover, 1 if ev.y > 0 else -1)
            else:
                x = (ev.pos[0] - ox) if hasattr(ev, "pos") else self.mx                  # a wheel event has no position of its own: the last one of the pointer
                if self.in_right_pane(x):
                    self.scroll2 = max(0, min(self.max_scroll(1), self.scroll2 - ev.y * 48))
                else:
                    self.scroll = max(0, min(self.max_scroll(0), self.scroll - ev.y * 48))
                self.need = True
            return None
        if hasattr(ev, "pos"):
            self.mx = ev.pos[0] - ox
        pos = (ev.pos[0] - ox, ev.pos[1] - oy + self.scroll)
        hit = self.hit_at(pos)
        self.kbd = False
        if ev.type == pygame.MOUSEMOTION:
            hv = hit[1] if hit else None
            if hv != self.hover:
                self.hover = hv
                self.need = True
            if self.drag and ev.buttons[0]:
                self.slider_from_x(self.drag, pos[0])
        elif ev.type == pygame.MOUSEBUTTONUP:
            self.drag = None
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.text_focus and not (hit and hit[1] == self.text_focus):
            self.text_focus = None                                   # a click elsewhere ends the typing
            self.need = True
            return self.mouse(ev, ox, oy, scale)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and hit:
            rect, cid, kind, arg = hit
            fk = f"{cid}#{arg}" if kind == "radio" else cid
            if fk in self.order:
                self.focus = self.order.index(fk)
            self.need = True
            if kind == "btn":
                return self.press(cid)
            if kind == "ddclose":
                self.dd_open = None
                return None
            if kind == "ddgrp":                                                 # a group of the add menu opens or folds (the menu stays)
                self.dd_groups ^= {arg}
                self.need = True
                return None
            if kind == "ddopt":
                self.dd_open = None
                self.set_value(cid, arg)
                return None
            if self.dd_open:
                self.dd_open = None
            row = self.find(cid)
            if row is None or not self.enabled(row):
                return None
            if kind == "text":
                self.text_focus = cid
            elif kind == "dd":
                self.dd_open = cid
                vals = [v for _, v in row["opts"]]
                self.dd_hl = vals.index(self.cfg.get(cid)) if self.cfg.get(cid) in vals else 0
            elif kind == "ly":
                self.layer_action(arg)
            elif kind == "it":
                self.select_item(arg)
            elif kind == "sc":
                self.scene_action(arg)
            elif kind == "toggle":
                self.adjust(cid, 0)
            elif kind == "modbtn":
                self.mod_next(cid)
            elif kind == "cycbtn":
                self.cyc_next(cid)
            elif kind in ("seg", "radio") and (self.cfg.get("cycles") or {}).get(cid) and self.scene_view == "editor":     # alternating: a click picks or drops a value
                opts = self.cfg["cycles"][cid]["opts"]
                if arg in opts and len(opts) > 1:
                    opts.remove(arg)
                elif arg not in opts:
                    opts.append(arg)
                self.store_scene()
                self.need = True
            elif kind in ("seg", "radio"):
                self.set_value(cid, arg)
            elif kind == "slider":
                now = time.perf_counter()
                if self.last_click[0] == cid and now - self.last_click[1] < 0.4:
                    default = DEFAULTS[cid]
                    self.set_value(cid, default, announce=False)
                    self.say(f"{NAMES.get(cid, cid)} restaurado: {default}{self.find(cid).get('unit', '%')}")
                    self.last_click = (None, 0.0)
                else:
                    self.last_click = (cid, now)
                    self.drag = cid
                    self.mod_end = None
                    self.slider_from_x(cid, pos[0])
        return None

    # ------------------------------------------------------------- render
    def _txt(self, font, text, pos, color, anchor="l"):
        img = font.render(text, True, color)
        x, y = pos
        if anchor == "r":
            x -= img.get_width()
        elif anchor == "c":
            x -= img.get_width() // 2
        self.surf.blit(img, (x, y))
        return img.get_width()

    def render(self):
        now = time.perf_counter()
        if self.toast and now > self.toast[1]:
            self.toast = None
            self.need = True
        if self.quit_armed and now > self.quit_armed:
            self.quit_armed = 0.0
            self.need = True
        if self._pending_img is not None:                                             # the logo chosen in the window of Windows
            path, self._pending_img = self._pending_img, None
            if path:
                self.set_value("gen_img", path, announce=False)
                self.say("Imagem escolhida")
        if self.del_armed[0] >= 0 and now > self.del_armed[1]:
            self.del_armed = (-1, 0.0)
            self.need = True
        if self.restore_armed and now > self.restore_armed:
            self.restore_armed = 0.0
            self.need = True
        if not self.need:
            return False
        self.need = False
        s, c = self.surf, self.cfg
        s.fill((0, 0, 0, 0))
        self.hits, self.order, self.frects, self.order_val = [], [], {}, []
        self.dd_rects = {}
        self.slider_geos = {}
        self.thumb_slots, self.popup_rect = [], None
        self.ear_slots = []                                            # where Sistema > Áudio wants the analysis of the music (the control window draws it)
        self.card_marks = []                                           # (x0, top, height, width, title) of every card with a title, on the surface: the control window pins the title of the one being scrolled
        W = self.W
        # tab bar
        x = 0
        hidden_n = 0 if self.cfg.get("advanced", False) else self.adv_hidden()          # how many settings the simple mode keeps out of sight
        adv_w = 172 if hidden_n else 118                               # room for the +N of the hidden options
        adv_r = pygame.Rect(W - adv_w, 0, adv_w, 36)
        for i, (name, _) in enumerate(TABS):
            cid = f"tab{i}"
            tw = min(220, (W - adv_w - 6 - 6 * (len(TABS) - 1)) // len(TABS))          # the tabs do not stretch across a wide window
            r = pygame.Rect(x, 0, tw, 36)
            sel, hov = i == self.tab, self.hover == cid
            if sel:                                                                     # the open tab: bright text and a lime line under it, no box (ScreenMaster)
                ui.rect(s, (*SEL, 255), pygame.Rect(r.x + 10, r.bottom - 3, r.w - 20, 3), border_radius=2)
            elif hov:
                ui.rect(s, (*SURFACE2, 255), r, border_radius=6)   # the chosen tab is blue like every choice: red is for what is on the air and for leaving
            pass
            self._txt(self.ftab, name, (r.centerx, r.y + 9), TEXT if sel else DIM, "c")      # the open tab is bright; the others dim (no box)
            self.hits.append((r, cid, "btn", None))
            self.order.append(cid)
            self.order_val.append(None)
            self.frects[cid] = r
            x += tw + 6
        on = bool(c.get("advanced", False))                                        # the switch of the advanced mode, on the right of the tab bar
        hv = self.hover == "advanced"
        ui.rect(s, (*(SURFACE2 if hv else SURFACE), 255), adv_r, border_radius=10)
        ui.rect(s, (*(ACCENT2 if on else CTRL), 255), adv_r, width=2 if on else 1, border_radius=10)
        pill = pygame.Rect(adv_r.x + 10, adv_r.centery - 8, 28, 16)
        ui.rect(s, (*(OK if on else (74, 80, 108)), 255), pill, border_radius=8)
        ui.circle(s, (255, 255, 255), (pill.right - 8 if on else pill.left + 8, pill.centery), 6)
        self._txt(self.ftab, "Avançado" + (f"  +{hidden_n}" if hidden_n else ""), (pill.right + 8, adv_r.y + 9), TEXT if on else DIM)
        self.hits.append((adv_r, "advanced", "btn", None))
        self.order.append("advanced")
        self.order_val.append(None)
        self.frects["advanced"] = adv_r
        y = self.HEAD
        cards = TABS[self.tab][1]
        cols = self.cols.get(self.tab) or []
        if cols and len(cols) == len(cards):
            wl, wr, gap = self._col_widths()
            yl = yr = y
            for (title, rows), col in zip(cards, cols):
                if col == "F":
                    y = max(yl, yr)
                    y += self._draw_card(title, rows, y, 0, W) + self.GAP
                    yl = yr = y
                elif col == "L":
                    yl += self._draw_card(title, rows, yl, self.side_w(), wl) + self.GAP
                else:
                    yr += self._draw_card(title, rows, yr, self.side_w() + wl + gap, wr) + self.GAP
            y = max(yl, yr)
        else:
            wc = self._single_w()
            x0 = (W - wc) // 2
            plan, i = self._single_plan(cards, wc), 0
            while i < len(plan):
                p = plan[i]
                if not p["grp"]:
                    y += self._draw_card(p["title"], p["rows"], y, x0, wc) + p["gap"]
                    i += 1
                    continue
                j = i                                                             # one container for the whole run
                while j < len(plan) and plan[j]["grp"]:
                    j += 1
                total = sum(q["h"] + q["gap"] for q in plan[i:j]) - plan[j - 1]["gap"]
                ui.rect(self.surf, (*SURFACE, 255), (x0, y, wc, total))                       # flat panels, with a hairline (ScreenMaster)
                ui.rect(self.surf, (*BORDER, 255), (x0, y, wc, total), width=1)
                y0 = y
                for q in plan[i:j]:
                    if q["kid"]:
                        ui.rect(self.surf, (23, 26, 39, 255), (x0 + 12, y, wc - 24, q["h"]), border_radius=10)
                        self._draw_card(q["title"], q["rows"], y, x0 + 14, wc - 28, bg=False)
                    else:
                        self._draw_card(q["title"], q["rows"], y, x0, wc, bg=False)
                    y += q["h"] + q["gap"]
                y = y0 + total + plan[j - 1]["gap"]
                i = j
        if self._reveal is not None:                                               # an item was opened: its row goes to the top, so its page is under it
            k, self._reveal = self._reveal, None
            rid = next((r["id"] for _, rs in TABS[self.tab][1] for r in rs if r.get("item") == k), None)
            fr = self.frects.get(rid)
            if fr is not None:
                self.scroll = max(0, min(self.max_scroll(), fr.y - self.HEAD - 52))
                self.need = True
        if self.dd_open:
            self._dropdown_popup()
            if getattr(self, "dd_q", "") and self.dd_open != "ly_add":
                self.dd_q = ""
        # keyboard focus ring, drawn once the full focus order is known
        if self.kbd and self.order:
            fr = self.frects.get(self.order[self.focus % len(self.order)])
            if fr is not None:
                ui.rect(s, (*FOCUS, 255), fr.inflate(-4, -4), width=2, border_radius=max(4, min(12, fr.h // 2 - 4)))
        return True

    TAG_COLORS = {"fx": (24, 95, 165), "bg": (15, 110, 86), "part": (153, 60, 29), "vis": (83, 74, 183), "beh": (80, 86, 110), "sc": (80, 86, 110)}

    def ed_status(self):
        """(colour, text) of the state of the scene being edited: saved / changing on the big picture / only in the preview."""
        if self.is_dirty():
            return (ACCENT, "Mudando ao vivo") if self.cfg.get("live") else (ACCENT2, "Só na prévia")
        return OK, "Tudo salvo"

    def _lbar_row(self, row, y):
        """The toolbar over the list of effects (ScreenMaster's): move up, move down, duplicate and delete the selected effect, and the main action "+ Ajuste"."""
        s, c = self.surf, self.cfg
        W = self.W
        cy = y + (self.ROW - 4) // 2
        sel = int(c.get("ly_sel", 0))
        n = len(c.get("layers") or [])
        # the column's header (ScreenMaster's): a small caption, the big name of the layer, and the toolbar on the right
        self._txt(self.f_s, row.get("help", ""), (22, y + 2), DIM)
        self._txt(widgets.font("label", True), self._fit(widgets.font("label", True), row.get("label", ""), W // 2), (22, y + 16), TEXT)
        x = W - 22
        add_lbl = "+ Ajuste"
        aw = max(96, self.fb.size(add_lbl)[0] + 26)
        br = pygame.Rect(x - aw, cy - 15, aw, 30)
        widgets.button(s, self.fb, br, add_lbl, "primary", hover=self.hover == "lbar_add", radius=9, dy=1)
        self.hits.append((br, "lbar_add", "btn", None))
        self.order.append("lbar_add")
        self.order_val.append(None)
        self.frects["lbar_add"] = br
        x = br.x - 12
        icons = (("lbar_del", "del", n > 0), ("lbar_dup", "dup", n > 0), ("lbar_down", "down", n > 0 and sel > 0), ("lbar_up", "up", n > 0 and sel < n - 1))
        for cid, kind, on in icons:
            x -= 30
            r = pygame.Rect(x, cy - 13, 26, 26)
            col = TEXT if on else widgets.FAINT
            hov = on and self.hover == cid
            if hov:
                ui.rect(s, widgets.HOVER_FILL, r, border_radius=6)
            cx, cyy = r.center
            if kind == "up":
                pygame.draw.polygon(s, col, [(cx, cyy - 5), (cx - 6, cyy + 4), (cx + 6, cyy + 4)])
            elif kind == "down":
                pygame.draw.polygon(s, col, [(cx, cyy + 5), (cx - 6, cyy - 4), (cx + 6, cyy - 4)])
            elif kind == "dup":
                pygame.draw.rect(s, col, (cx - 6, cyy - 3, 9, 10), 1, border_radius=2)
                pygame.draw.rect(s, col, (cx - 3, cyy - 6, 9, 10), 1, border_radius=2)
            elif kind == "del":
                pygame.draw.rect(s, col, (cx - 6, cyy - 4, 12, 11), 1, border_radius=2)
                pygame.draw.line(s, col, (cx - 8, cyy - 5), (cx + 8, cyy - 5), 1)
                pygame.draw.line(s, col, (cx - 3, cyy - 7), (cx + 3, cyy - 7), 1)
            if on:
                self.hits.append((r, cid, "btn", None))
                self.order.append(cid)
                self.order_val.append(None)
                self.frects[cid] = r
            x -= 4

    def _item_row(self, row, y):
        """An item of the stack of the editor (the mandala, the camera ...): its tag, its name and how it is set; the selected one is lit."""
        s, c = self.surf, self.cfg
        cid, k = row["id"], row["item"]
        W = self.W
        rowr = pygame.Rect(10, y, W - 20, self.ROW - 4)
        sel = int(c.get("ed_item", 0)) == k
        hov = self.hover == cid
        ui.rect(s, (*((0x2E, 0x33, 0x24) if sel else (SURFACE2 if hov else (22, 25, 38))), 255), rowr, border_radius=10)
        ui.rect(s, (*(ACCENT2 if sel else BORDER), 255), rowr, width=1, border_radius=10)
        self.frects[cid] = rowr
        self.order.append(cid)
        self.order_val.append(None)
        self.hits.append((rowr, cid, "it", k))
        cy = y + (self.ROW - 4) // 2
        tag = row["tag"]
        tw = self.f_sb.size(tag)[0] + 14
        tr = pygame.Rect(18, cy - 10, tw, 20)
        ui.rect(s, (*self.TAG_COLORS.get(row.get("group"), (60, 60, 90)), 255), tr, border_radius=6)
        self._txt(self.f_sb, tag, (tr.centerx, tr.y + 2), (255, 255, 255), "c")
        nx = tr.right + 12
        tw_ = rowr.right - (44 + 58 if row.get("sw") else 44) - nx
        on_ = bool(c.get(row["sw"], True)) if row.get("sw") else True
        self._txt(self.f, self._fit(self.f, row["label"], tw_), (nx, cy - 17), TEXT if on_ else DIM)
        self._txt(self.f_s, self._fit(self.f_s, row["help"], tw_), (nx, cy + 3), DIM)
        kx, ky = rowr.right - 20, cy
        pygame.draw.polygon(s, ACCENT2 if sel else DIM, [(kx - 5, ky - 3), (kx + 5, ky - 3), (kx, ky + 3)] if sel else [(kx - 3, ky - 5), (kx - 3, ky + 5), (kx + 3, ky)])
        if row.get("sw"):                                                       # a layer of the stack: its switch, on the right of the row
            on = bool(c.get(row["sw"], True))
            pill = pygame.Rect(rowr.right - 36 - 46, cy - 13, 46, 26)
            ui.rect(s, (*(OK if on else (74, 80, 108)), 255), pill, border_radius=13)
            ui.circle(s, (255, 255, 255), (pill.right - 13 if on else pill.left + 13, pill.centery), 9)
            self.hits.append((pill.inflate(8, 8), row["sw"], "toggle", None))

    def _fit(self, font, text, w):
        return widgets.fit(font, text, w)

    def scene_state(self, i):
        """What scene i is doing: (text, fill, text colour) or None."""
        c = self.cfg
        if i == self.live_i:
            return ("NO AR" + ("  ·  FIXA" if c["effect"] == i + 1 else ""), ACCENT, ON_ACCENT)
        if i == self.pend_i:
            return (("ENTRANDO", "NO COMPASSO", "NA FRASE", "NA MÚSICA", "NA FRASE")[int(c.get("scene_when", 2)) % 5], ACCENT2, ON_LIGHT)
        if c["effect"] == i + 1:
            return ("FIXA", ACCENT2, ON_LIGHT)
        scn = c.get("scenes") or []
        if 0 <= i < len(scn) and not scn[i].get("scene_auto", True):
            return ("FORA DO AUTOMÁTICO", (46, 50, 72), DIM)
        return None

    def _scene_row(self, row, y):
        """A scene of the list: its live thumbnail (the control window paints it), name, what it is made of, what it is doing, and play / duplicate / delete."""
        s, c = self.surf, self.cfg
        cid, i = row["id"], row["idx"]
        W = self.W
        rowr = pygame.Rect(10, y, W - 20, self.ROW - 4)
        sel = i == c.get("scene_edit", 0) and self.scene_view == "editor"
        hov = self.hover == cid
        ui.rect(s, (*((0x2E, 0x33, 0x24) if sel else (SURFACE2 if hov else (22, 25, 38))), 255), rowr, border_radius=10)
        ui.rect(s, (*(ACCENT2 if sel else BORDER), 255), rowr, width=1, border_radius=10)
        self.frects[cid] = rowr
        self.order.append(cid)
        self.order_val.append(None)
        self.hits.append((rowr, cid, "sc", ("sel", i)))
        cy = y + (self.ROW - 4) // 2
        th = pygame.Rect(16, cy - 18, 64, 36)
        ui.rect(s, (*(6, 7, 11), 255), th, border_radius=6)
        self.thumb_slots.append((th, i))
        nx = th.right + 12
        right = W - 26 - 28 - 6
        st = self.scene_state(i)
        name = self._fit(self.fb if sel else self.f, row["label"], right - nx - (self.f_sb.size(st[0])[0] + 22 if st else 4))
        nw = self._txt(self.fb if sel else self.f, name, (nx, cy - 17), TEXT)
        if st:
            cr = pygame.Rect(nx + nw + 8, cy - 14, self.f_sb.size(st[0])[0] + 14, 17)
            ui.rect(s, (*st[1], 255), cr, border_radius=8)
            self._txt(self.f_sb, st[0], (cr.centerx, cr.y + 1), st[2], "c")
        self._txt(self.f_s, self._fit(self.f_s, row["help"], right - nx - 4), (nx, cy + 3), DIM)
        armed = self.del_armed[0] == i and self.del_armed[1] > time.perf_counter()
        br = pygame.Rect(right, cy - 13, 28, 26)
        scm = f"scm:{i}"
        opn = self.dd_open == scm
        ui.rect(s, (*(DANGER if armed else (HOVER_FILL if opn else CTRL_FILL)), 255), br, border_radius=7)
        ui.rect(s, (*(DANGER if armed else CTRL), 255), br, width=1, border_radius=7)
        for dx in (-6, 0, 6):
            ui.circle(s, ON_LIGHT if armed else TEXT, (br.centerx + dx, br.centery), 2)
        self.dd_rects[scm] = br
        self.hits.append((br, cid, "sc", ("menu", i)))

    def _layer_row(self, row, y):
        """One layer of the list: the eye, its type, its name and detail, how it is blended, and the buttons to move, duplicate and delete it."""
        s, c = self.surf, self.cfg
        cid, i = row["id"], row["idx"]
        layers = c.get("layers") or []
        if not 0 <= i < len(layers):
            return
        L = layers[i]
        info = LY.TYPES.get(L.get("t"), LY.TYPES["fb"])
        on = L.get("on", True)
        sel = i == c.get("ly_sel", 0) and int(c.get("ed_item", 4)) in (4, 7, 8, 9, 10)
        W = self.W
        rowr = pygame.Rect(10, y, W - 20, self.ROW - 4)
        hov = self.hover == cid
        ui.rect(s, (*((0x2E, 0x33, 0x24) if sel else (SURFACE2 if hov else (22, 25, 38))), 255), rowr, border_radius=10)
        ui.rect(s, (*(ACCENT2 if sel else BORDER), 255), rowr, width=1, border_radius=10)
        ui.rect(s, (*self.TAG_COLORS.get(info.get("group"), (60, 60, 90)), 255), pygame.Rect(rowr.x + 3, rowr.y + 8, 3, rowr.h - 16), border_radius=2)
        self.frects[cid] = rowr
        self.order.append(cid)
        self.order_val.append(None)
        self.hits.append((rowr, cid, "ly", ("sel", i)))
        cy = y + (self.ROW - 4) // 2
        eye = pygame.Rect(18, cy - 13, 26, 26)
        ec, col = eye.center, (widgets.TEXT if on else widgets.FAINT)           # an eye: open when the effect plays, closed when it is off
        if on:
            pygame.draw.ellipse(s, col, (ec[0] - 9, ec[1] - 5, 18, 10), 2)
            pygame.draw.circle(s, col, ec, 3)
        else:
            pygame.draw.arc(s, col, (ec[0] - 9, ec[1] - 6, 18, 12), math.pi * 0.1, math.pi * 0.9, 2)
            pygame.draw.line(s, col, (ec[0] - 8, ec[1] + 2), (ec[0] + 8, ec[1] + 2), 1)
        self.hits.append((eye, cid, "ly", ("eye", i)))
        tag = info["tag"]
        tw = self.f_sb.size(tag)[0] + 14
        tr = pygame.Rect(56, cy - 10, tw, 20)
        ui.rect(s, (*(self.TAG_COLORS.get(info["group"], (60, 60, 90)) if on else (46, 50, 72)), 255), tr, border_radius=6)
        self._txt(self.f_sb, tag, (tr.centerx, tr.y + 2), (255, 255, 255) if on else DIM, "c")
        nx = tr.right + 10
        detail = LY.detail_of(L)
        bm = LY.BLEND[int(L.get("bm", 0)) % 4][0] if info["group"] in ("fx", "bg") and L.get("t") != "tone" else ""
        right = W - 26 - (60 if self.wide else 4 * 34 + 8)                 # wide: no per-row buttons (the toolbar has them), so the names get the room
        self._txt(self.f, self._fit(self.f, info["label"], right - nx - 8), (nx, cy - 17), TEXT if on else DIM)
        sub = "  ·  ".join(t for t in (detail, bm if bm and bm != "Normal" else "", f"{int(L.get('op', 100))}%" if int(L.get("op", 100)) != 100 else "") if t)
        self._txt(self.f_s, self._fit(self.f_s, sub, right - nx - 8), (nx, cy + 3), DIM)
        bx = right
        for what in (() if self.wide else ("up", "down", "dup", "del")):          # wide: the toolbar of the list has them
            br = pygame.Rect(bx, cy - 13, 26, 26)
            ui.rect(s, (*CTRL_FILL, 255), br, border_radius=7)
            ui.rect(s, (*CTRL, 255), br, width=1, border_radius=7)
            gc = DIM
            cx_, cy_ = br.center
            if what == "up":
                pygame.draw.polygon(s, gc, [(cx_ - 5, cy_ + 3), (cx_ + 5, cy_ + 3), (cx_, cy_ - 4)])
            elif what == "down":
                pygame.draw.polygon(s, gc, [(cx_ - 5, cy_ - 3), (cx_ + 5, cy_ - 3), (cx_, cy_ + 4)])
            elif what == "dup":
                pygame.draw.rect(s, gc, (cx_ - 6, cy_ - 6, 9, 9), 1)
                pygame.draw.rect(s, gc, (cx_ - 2, cy_ - 2, 9, 9), 1)
            else:
                pygame.draw.line(s, gc, (cx_ - 5, cy_ - 5), (cx_ + 5, cy_ + 5), 2)
                pygame.draw.line(s, gc, (cx_ - 5, cy_ + 5), (cx_ + 5, cy_ - 5), 2)
            self.hits.append((br, cid, "ly", (what, i)))
            bx += 34

    def _dropdown_popup(self):
        """The list of the dropdown that is open, over everything (drawn last, its hits win)."""
        cid = self.dd_open
        row = self.find(cid) if cid else None
        box = self.dd_rects.get(cid) if cid else None
        if row is None or box is None:
            self.dd_open = None
            return
        s, c = self.surf, self.cfg
        if cid == "ly_add":                                                     # the add menu of the effects: grouped, as ScreenMaster's
            return self._group_popup(row, box)
        opts = row["opts"]
        ih = 34
        h = len(opts) * ih + 8
        below = (self.scroll2 if self.in_right_pane(box.x) else self.scroll) + max(300, min(self.view_h, 900)) - self.HEAD - self.reserved - box.bottom
        y0 = box.bottom + 4 if (below > h or box.y - h < 0) else box.y - h - 4
        pw = max(box.w, 150) if cid.startswith("scm:") else box.w                  # the ••• button is small: its menu is wider and hangs from its right edge
        pr = pygame.Rect(box.right - pw if cid.startswith("scm:") else box.x, y0, pw, h)
        self.popup_rect = pr.inflate(8, 8)
        self.hits.append((pygame.Rect(0, 0, self.W, self.surf.get_height()), "ddclose", "ddclose", None))
        ui.rect(s, (14, 16, 26, 255), pr.inflate(4, 4), border_radius=11)
        ui.rect(s, (*ACCENT2, 255), pr.inflate(4, 4), width=1, border_radius=11)
        cur = c.get(cid)
        for k, (lbl, val) in enumerate(opts):
            r = pygame.Rect(pr.x + 4, pr.y + 4 + k * ih, pr.w - 8, ih - 2)
            hl = k == self.dd_hl or (self.hover == cid and False)
            if hl:
                ui.rect(s, (*HOVER_FILL, 255), r, border_radius=8)
            if cur == val and cid not in ("ly_add", "ly_tpl"):
                ui.rect(s, (*SEL, 255), pygame.Rect(r.x, r.y + 6, 3, r.h - 12), border_radius=2)
            self._txt(self.fb if cur == val and cid not in ("ly_add", "ly_tpl") else self.f, lbl, (r.x + 12, r.y + 6), TEXT)
            self.hits.append((r, cid, "ddopt", val))

    GROUP_INFO = {"fx": ("Efeitos de lente e tom", "na imagem, depois do desenho"), "bg": ("Fundos", "a cor e o gradiente por trás"),
                  "part": ("Partículas", "pontos que se movem com a música")}

    def _group_popup(self, row, box):
        """The add menu of the effects: the kinds grouped (fold/open), each with its count, what it is for, and what it runs on."""
        from layers import TYPES
        s = self.surf
        groups = {}
        for lbl, val in row["opts"]:
            groups.setdefault(TYPES.get(val, {}).get("group", "fx"), []).append((lbl, val))
        if not hasattr(self, "dd_groups"):
            self.dd_groups = {"fx"}
        if not hasattr(self, "dd_q"):
            self.dd_q = ""
        q = self.dd_q.lower().strip()
        if q:                                                                  # searching: the groups that have a match open, the others fold
            groups = {g: [o for o in items if q in o[0].lower()] for g, items in groups.items()}
            groups = {g: items for g, items in groups.items() if items}
            self.dd_groups = set(groups) if groups else set()
        pw = max(box.w, 340)
        if self.panes():                                                       # the menu stays inside the column it was opened from (the page clips at its edges)
            wl = self._col_widths()[0]
            colL = self.side_w() if self.in_right_pane(box.x) is False else self.side_w() + wl + self._col_widths()[2]
            colR = colL + (self._col_widths()[1] if self.in_right_pane(box.x) else wl)
            pw = min(pw, colR - colL - 8)
            box = pygame.Rect(max(colL + 4, min(box.x, colR - pw - 4)), box.y, box.w, box.h)
        ui_h = 44                                                              # the search field on the top line
        for g in groups:
            ui_h += 40 + (len(groups[g]) * 30 if g in self.dd_groups else 0)
        below = (self.scroll2 if self.in_right_pane(box.x) else self.scroll) + max(300, min(self.view_h, 900)) - self.HEAD - self.reserved - box.bottom
        y = box.bottom + 4 if below > ui_h + 12 else box.y - ui_h - 16                # no room under the box: the menu opens above it
        pr = pygame.Rect(box.x, y, pw, ui_h + 12)
        self.popup_rect = pr.inflate(8, 8)
        self.hits.append((pygame.Rect(0, 0, self.W, self.surf.get_height()), "ddclose", "ddclose", None))
        ui.rect(s, (*widgets.SURFACE2, 255), pr.inflate(4, 4), border_radius=10)
        ui.rect(s, (*widgets.CTRL, 255), pr.inflate(4, 4), width=1, border_radius=10)
        sf = pygame.Rect(pr.x + 6, pr.y + 6, pr.w - 12, 32)                   # the search field
        ui.rect(s, (*widgets.BG, 255), sf, border_radius=7)
        ui.rect(s, (*widgets.CTRL, 255), sf, width=1, border_radius=7)
        self._txt(self.f, self.dd_q if self.dd_q else "Buscar ajuste…", (sf.x + 10, sf.y + 7), widgets.TEXT if self.dd_q else widgets.DIM)
        yy = pr.y + 44
        for g, items in groups.items():
            name, desc = self.GROUP_INFO.get(g, (g, ""))
            open_ = g in self.dd_groups
            hr = pygame.Rect(pr.x + 4, yy, pr.w - 8, 36)
            if self.hover == "ddgrp:" + g:
                ui.rect(s, (*widgets.HOVER_FILL, 255), hr, border_radius=7)
            cx, cy = hr.x + 12, hr.centery
            pygame.draw.polygon(s, widgets.DIM, [(cx, cy - 4), (cx + 8, cy - 4), (cx + 4, cy + 3)] if open_ else [(cx, cy - 4), (cx, cy + 4), (cx + 6, cy)])
            self._txt(self.fb, name, (hr.x + 26, hr.y + 6), widgets.TEXT)
            self._txt(self.f_s, desc, (hr.x + 26, hr.y + 22), widgets.DIM)
            self._txt(self.f_s, f"{len(items)}", (hr.right - 12, hr.y + 8), widgets.DIM, "r")
            self.hits.append((hr, "ly_add", "ddgrp", g))
            yy += 40
            if open_:
                for lbl, val in items:
                    r = pygame.Rect(pr.x + 4, yy, pr.w - 8, 30)
                    cur = self.cfg.get("ly_add") == val
                    if self.hover == "ddopt:" + str(val):
                        ui.rect(s, (*widgets.HOVER_FILL, 255), r, border_radius=7)
                    self._txt(self.f, lbl, (r.x + 30, r.y + 6), widgets.TEXT)
                    chip = self.f_s.size("GPU")[0] + 12
                    ui.rect(s, (*widgets.SURFACE2, 255), pygame.Rect(r.right - chip - 8, r.y + 6, chip, 18), border_radius=5)
                    self._txt(self.f_s, "GPU", (r.right - chip / 2 - 8, r.y + 7), widgets.DIM, "c")
                    self.hits.append((r, "ly_add", "ddopt", val))
                    yy += 30
        self.dd_rects_popup = pr

    def _draw_card(self, title, rows, y, x0, wc, bg=True):
        """One card at (x0, y) of width wc. In a column the rows are drawn on a piece of the surface (so they all think the panel is wc wide) and the hits, the
        focus rectangles, the sliders and the dropdown boxes they leave are moved back to the surface. Returns the height of the card."""
        full, wfull = self.surf, self.W
        n_hits, k_fr, k_dd, k_sl, n_th = len(self.hits), set(self.frects), set(self.dd_rects), set(self.slider_geos), len(self.thumb_slots)
        n_ear = len(self.ear_slots)
        if x0 or wc != wfull:
            self.surf = full.subsurface(pygame.Rect(x0, 0, wc, full.get_height()))
            self.W = wc
        s = self.surf
        ch = self._card_h(rows, title, wc)
        if bg:
            ui.rect(s, (*SURFACE, 255), (0, y, wc, ch))
            ui.rect(s, (*BORDER, 255), (0, y, wc, ch), width=1)
        if title:
            self._txt(self.f_sb, title, (18, y + 14), TITLE)
            self.card_marks.append((x0, y, ch, wc, title))
        ry = y + (40 if title else 8)
        i = 0
        while i < len(rows):
            if rows[i].get("tile"):                                                  # a run of choices drawn as live thumbnails
                j = i
                while j < len(rows) and rows[j].get("tile"):
                    j += 1
                ry += self._tile_rows(rows[i:j], ry, wc)
                i = j
            elif rows[i].get("flow"):                                                  # a run of switches drawn as pills that wrap
                j = i
                while j < len(rows) and rows[j].get("flow"):
                    j += 1
                ry += self._flow_rows(rows[i:j], ry, wc)
                i = j
            elif rows[i].get("kind") == "ear":                                         # a dark slot: the control window paints the live analysis over it
                r = pygame.Rect(12, ry, wc - 24, self.EAR_H - 8)
                ui.rect(s, (*widgets.BG, 255), r, border_radius=10)
                self.ear_slots.append(r)
                ry += self.EAR_H
                i += 1
            else:
                self._row(rows[i], ry)
                ry += self.ROW + (self.STACK if self._stacked(rows[i], wc) else 0)
                i += 1
        self.surf, self.W = full, wfull
        if x0:
            self.hits[n_hits:] = [(r.move(x0, 0), cid, kind, arg) for r, cid, kind, arg in self.hits[n_hits:]]
            self.thumb_slots[n_th:] = [(r.move(x0, 0), i) for r, i in self.thumb_slots[n_th:]]
            self.ear_slots[n_ear:] = [r.move(x0, 0) for r in self.ear_slots[n_ear:]]
            for k in set(self.frects) - k_fr:
                self.frects[k] = self.frects[k].move(x0, 0)
            for k in set(self.dd_rects) - k_dd:
                self.dd_rects[k] = self.dd_rects[k].move(x0, 0)
            for k in set(self.slider_geos) - k_sl:
                tl, tw = self.slider_geos[k]
                self.slider_geos[k] = (tl + x0, tw)
        return ch

    def _ctl_left(self, row, kind, R, W):
        """Where the control of a row starts (its left edge): the text of the row has to end before it."""
        if kind == "seg":
            return R - sum(max(56, self.f.size(l)[0] + 26) for l, _ in row["opts"]) - (self.MODW + 12 if self._cyclable(row) else 0)
        if kind == "dd":
            return R - 220
        if kind == "text":
            return R - 250
        if kind == "slider":
            tlen = max(110, min(420, int(W * 0.27)))
            if self._modable(row):
                tlen = max(90, int(tlen * 0.6))                         # a number that can follow the music: a shorter track, the ♪ button beside it
            return R - 56 - 14 - tlen - 12 - (self.MODW + 8 if self._modable(row) else 0)
        if kind == "toggle":
            return R - 46 - self.f_s.size("Desligado")[0] - 20
        if kind == "action":
            btn = row["btn"](self.cfg) if callable(row["btn"]) else row["btn"]
            return R - max(120, self.fb.size(btn)[0] + 32) - 6
        if kind == "swatches":
            return R - len(row["items"]) * 32 - 4
        if kind == "radio":
            return R - 34
        return R

    MODW = 80                                                                      # the ♪ button of a number that can follow the music

    def _modable(self, row):
        """A number of the scene being edited that can follow the music (see mods.py)."""
        return self.tab == TAB_SCENES and self.scene_view == "editor" and row.get("kind") == "slider" and row["id"] in MOD.MOD_KEYS

    def _cyclable(self, row):
        return self.tab == TAB_SCENES and self.scene_view == "editor" and row.get("kind") in ("seg", "radio") and row["id"] in MOD.CYCLE_KEYS

    def mod_next(self, cid):
        """The ♪ button: Fixo -> each source of the music in turn -> Fixo. The range starts around the value it had."""
        mods = self.cfg.setdefault("mods", {})
        m = mods.get(cid)
        if m is None:
            row = self.find(cid)
            if row is None:
                return
            v = self.cfg[cid]
            span = (row["hi"] - row["lo"]) * 0.25
            mods[cid] = dict(src=0, lo=max(row["lo"], int(v - span)), hi=min(row["hi"], int(v + span)))
        elif int(m["src"]) + 1 < len(MOD.SOURCES):
            m["src"] = int(m["src"]) + 1
        else:
            mods.pop(cid)
        self.store_scene()
        self.need = True

    def cyc_next(self, cid):
        """The ⇄ button of a choice: one value -> alternate at every beat, bar, phrase, drop -> one value. The choice in use is the first one picked."""
        cyc = self.cfg.setdefault("cycles", {})
        c_ = cyc.get(cid)
        if c_ is None:
            cyc[cid] = dict(opts=[self.cfg[cid]], when=0)
        elif int(c_["when"]) + 1 < len(MOD.WHEN):
            c_["when"] = int(c_["when"]) + 1
        else:
            cyc.pop(cid)
        self.store_scene()
        self.need = True

    def _music_pill(self, r, text, on, cid, kind):
        s = self.surf
        hov = self.hover == cid
        ui.rect(s, (*((90, 20, 50) if on else (HOVER_FILL if hov else CTRL_FILL)), 255), r, border_radius=r.h // 2)
        ui.rect(s, (*(ACCENT if on else CTRL), 255), r, width=1, border_radius=r.h // 2)
        self._txt(self.f_s, self._fit(self.f_s, text, r.w - 10), (r.centerx, r.y + 5), (255, 200, 215) if on else TEXT, "c")
        self.hits.append((r, cid, kind, None))

    def _row(self, row, y):
        s, c = self.surf, self.cfg
        cid, kind = row["id"], row["kind"]
        if kind == "layer":
            return self._layer_row(row, y)
        if kind == "lbar":
            return self._lbar_row(row, y)
        if kind == "item":
            return self._item_row(row, y)
        if kind == "scene":
            return self._scene_row(row, y)
        if kind == "phead":                                                      # the title of the page: the effect's name big, what it is under it
            self._txt(widgets.font("lead", True), row["label"], (22, y + 4), TEXT)
            x = 22
            if row.get("tag"):                                                   # "Tons · placa de vídeo": the category as a colour square, then the words, then the chip GPU
                ui.rect(s, (*self.TAG_COLORS.get(row.get("group"), (60, 60, 90)), 255), (x, y + 33, 9, 9), border_radius=2)
                x += 16
                x += self._txt(self.f_s, row["tag"], (x, y + 30), DIM) + 14
            self._txt(self.f_s, row["help"], (x, y + 30), DIM)
            return
        if kind == "note":
            lab = row["label"](c) if callable(row["label"]) else row["label"]
            hp = row["help"](c) if callable(row["help"]) else row["help"]
            self._txt(self.f, lab, (22, y + (7 if hp else 14)), DIM)
            if hp:
                self._txt(self.f_s, hp, (22, y + 29), DIM)
            return
        en = self.enabled(row)
        W = self.W
        fkey = cid if kind != "radio" else f"{cid}#{row['value']}"
        stk = self._stacked(row, W)
        rowr = pygame.Rect(10, y, W - 20, self.ROW - 4 + (self.STACK if stk else 0))
        if kind == "radio" and cid == "sys_item" and c[cid] == row["value"]:      # a list of pages, not a choice of a setting: the page you are on is lit, with no circle
            ui.rect(s, (*HOVER_FILL, 255), rowr, border_radius=10)
            ui.rect(s, (*SEL, 255), pygame.Rect(rowr.x + 2, rowr.y + 8, 4, rowr.h - 16), border_radius=2)
        elif self.hover == cid and en:
            ui.rect(s, (*SURFACE2, 255), rowr, border_radius=10)
        tc, dc = (TEXT, DIM) if en else (dimmed(TEXT, 0.62), dimmed(DIM, 0.74))
        ic = icons.has(cid)
        lx = 62 if ic else 22                                       # a row with an icon starts its text after it
        if ic:
            if kind == "slider":
                tv = (c[cid] - row["lo"]) / max(1, row["hi"] - row["lo"])
            elif kind == "seg":
                tv = c[cid] / max(1, max(v for _, v in row["opts"]))
            else:
                tv = None
            icol = ACCENT2 if en else dimmed(ACCENT2, 0.5)
            icons.draw(s, cid, pygame.Rect(20, y + 6, 32, 32), icol, tv, bool(c[cid]) if kind == "toggle" else True)
        R = W - 26
        avail = max(60, (R if stk else self._ctl_left(row, kind, R, W)) - lx - 12)
        lw = self._txt(self.f, self._fit(self.f, row["label"], avail - (28 if row.get("chip") else 0)), (lx, y + 7), tc)
        if row.get("chip"):
            cr = pygame.Rect(lx + lw + 10, y + 8, 20, 20)
            ui.rect(s, (*BORDER, 255), cr, width=1, border_radius=5)
            self._txt(self.f_sb, row["chip"], (cr.centerx, cr.y + 2), dc, "c")
        h = row["help"](c) if callable(row["help"]) else row["help"]
        self._txt(self.f_s, self._fit(self.f_s, h, avail), (lx, y + 29), dc)
        cy = y + (self.ROW - 4) // 2
        self.frects[fkey] = rowr
        if en:
            self.order.append(fkey)
            self.order_val.append(row.get("value"))

        if kind == "radio" and cid == "sys_item":                                 # (its highlight was drawn under the text, above)
            self.hits.append((rowr, cid, "radio", row["value"]))
        elif kind == "radio":
            sel = c[cid] == row["value"]
            rc = (R - 12, cy)
            ui.circle(s, (*(SEL if sel else CTRL), 255), rc, 11, 0 if sel else 2)
            if sel:
                ui.circle(s, (*ON_SEL, 255), rc, 4)
            self.hits.append((rowr, cid, "radio", row["value"]))
        elif kind == "toggle":
            on = row["get"](c) if "get" in row else c[cid]
            pill = pygame.Rect(R - 46, cy - 13, 46, 26)
            col = OK if on else (74, 80, 108)
            ui.rect(s, (*(col if en else dimmed(col)), 255), pill, border_radius=13)
            kx = pill.right - 13 if on else pill.left + 13
            ui.circle(s, (255, 255, 255) if en else dimmed((255, 255, 255)), (kx, pill.centery), 9)
            self._txt(self.f_s, "Ligado" if on else "Desligado", (pill.left - 10, cy - 8), (OK if (on and en) else dc), "r")
            self.hits.append((rowr, cid, "toggle", None))
        elif kind == "seg":
            widths = [max(56, self.f.size(l)[0] + 26) for l, _ in row["opts"]]
            x = R - sum(widths)
            if stk:
                cy = y + self.ROW - 4 + self.STACK // 2 - 2
            n = len(widths)
            cyc = (c.get("cycles") or {}).get(cid) if self._cyclable(row) else None
            if self._cyclable(row):
                self._music_pill(pygame.Rect(x - 12 - self.MODW, cy - 13, self.MODW, 26), MOD.WHEN[int(cyc["when"]) % len(MOD.WHEN)][0] if cyc else "Uma só", cyc is not None, cid, "cycbtn")
            for i, ((lbl, val), w) in enumerate(zip(row["opts"], widths)):
                r = pygame.Rect(x, cy - 17, w, 34)
                sel = (val in cyc["opts"]) if cyc else c[cid] == val
                hov = self.hover == cid and en
                fill = SEL if sel else (HOVER_FILL if hov else CTRL_FILL)
                if not en:
                    fill = dimmed(fill, 0.6)
                radii = dict(border_top_left_radius=9 if i == 0 else 0, border_bottom_left_radius=9 if i == 0 else 0,
                             border_top_right_radius=9 if i == n - 1 else 0, border_bottom_right_radius=9 if i == n - 1 else 0)
                ui.rect(s, (*fill, 255), r, **radii)
                ui.rect(s, (*CTRL, 255), r, width=1, **radii)
                tcol = ON_SEL if sel else (tc if en else dc)
                self._txt(self.fb if sel else self.f, lbl, (r.centerx, r.y + 7), tcol, "c")
                self.hits.append((r, cid, "seg", val))
                x += w
        elif kind == "swatches":
            sw = 28
            n_ = len(row["items"])
            x0 = R - n_ * (sw + 4) + 4
            for i, col in enumerate(row["items"]):
                r_ = pygame.Rect(x0 + i * (sw + 4), cy - sw // 2, sw, sw)
                ui.rect(s, (*col, 255), r_, border_radius=6)
                sel = c[cid] == i
                ui.rect(s, (*(SEL if sel else CTRL), 255), r_.inflate(4, 4) if sel else r_, width=2 if sel else 1, border_radius=7)
                self.hits.append((r_, cid, "seg", i))
        elif kind == "action":
            btn = row["btn"](c) if callable(row["btn"]) else row["btn"]
            bw = max(120, self.fb.size(btn)[0] + 32)
            br = pygame.Rect(R - bw, cy - 15, bw, 30)
            hov = self.hover == cid and en
            armed = (cid == "quit" and self.quit_armed > time.perf_counter()) or (cid == "scenes_restore" and self.restore_armed > time.perf_counter())
            widgets.button(s, self.fb, br, btn, "primary" if (row.get("primary") and en) else "tone", hover=hov, armed=armed, enabled=en,
                           tone=DANGER if row.get("danger") else SEL, radius=9, dy=1, tone_edge=bool(row.get("danger")))
            self.hits.append((br, cid, "btn", None))
        elif kind == "dd":
            box = pygame.Rect(R - 220, cy - 17, 220, 34)
            hov = self.hover == cid and en
            opn = self.dd_open == cid
            ui.rect(s, (*(HOVER_FILL if (hov or opn) else CTRL_FILL), 255), box, border_radius=9)
            ui.rect(s, (*(SEL if opn else (HOVER_EDGE if hov else CTRL)), 255), box, width=2 if opn else 1, border_radius=9)
            cur = c.get(cid)
            lbl = next((l for l, v in row["opts"] if v == cur), row.get("placeholder", ""))
            self._txt(self.fb if cur in [v for _, v in row["opts"]] else self.f, lbl, (box.x + 14, box.y + 7), tc if en else dc)
            kx, ky = box.right - 18, box.centery
            pygame.draw.polygon(s, ACCENT2 if en else dc, [(kx - 5, ky + 3), (kx + 5, ky + 3), (kx, ky - 3)] if opn else [(kx - 5, ky - 3), (kx + 5, ky - 3), (kx, ky + 3)])
            self.dd_rects[cid] = box
            self.hits.append((box, cid, "dd", None))
        elif kind == "text":
            fr = pygame.Rect(R - 250, cy - 16, 250, 32)
            foc = self.text_focus == cid
            ui.rect(s, (34, 32, 66, 255), fr, border_radius=8)
            ui.rect(s, (*(FOCUS if foc else CTRL), 255), fr, width=2 if foc else 1, border_radius=8)
            txt = str(c[cid]) + ("|" if foc and int(time.perf_counter() * 2) % 2 == 0 else "")
            if not c[cid] and not foc and row.get("placeholder"):                  # an empty field says what it is for
                self._txt(self.f, row["placeholder"], (fr.x + 10, fr.y + 5), dc)
            else:
                self._txt(self.f, txt, (fr.x + 10, fr.y + 5), tc)
            self.hits.append((rowr, cid, "text", None))
        else:
            lo, hi = row["lo"], row["hi"]
            pw = 56
            tr = R - pw - 14
            tlen = max(110, min(420, int(W * 0.27)))                    # the track grows with the width of the panel (or of its column)
            if self._modable(row):
                tlen = max(90, int(tlen * 0.6))
            tl = tr - tlen
            self.slider_geo = (tl, tlen)
            self.slider_geos[cid] = (tl, tlen)
            m = (c.get("mods") or {}).get(cid) if self._modable(row) else None
            if self._modable(row):
                self._music_pill(pygame.Rect(tl - 12 - self.MODW, cy - 13, self.MODW, 26), MOD.SOURCES[int(m["src"]) % len(MOD.SOURCES)][0] if m else "Fixo", m is not None, cid, "modbtn")
            if m is not None:                                           # with the music: the range it moves in, two handles
                f0, f1 = sorted(((m["lo"] - lo) / (hi - lo), (m["hi"] - lo) / (hi - lo)))
                ui.rect(s, (66, 72, 100, 255), (tl, cy - 3, tlen, 6), border_radius=3)
                ui.rect(s, (*ACCENT, 255), (tl + int(tlen * f0), cy - 3, max(4, int(tlen * (f1 - f0))), 6), border_radius=3)
                for fr_ in (f0, f1):
                    kc = (tl + int(tlen * fr_), cy)
                    ui.circle(s, (255, 255, 255), kc, 9)
                    ui.circle(s, (*ACCENT, 255), kc, 9, 2)
                vr = pygame.Rect(R - pw, cy - 14, pw, 28)
                ui.rect(s, (34, 32, 66, 255), vr, border_radius=8)
                self._txt(self.f_s, f"{min(m['lo'], m['hi'])}–{max(m['lo'], m['hi'])}", (vr.centerx, vr.y + 6), tc, "c")
                self.hits.append((pygame.Rect(tl - 12, cy - 20, tlen + 24, 40), cid, "slider", None))
                return
            frac = (c[cid] - lo) / (hi - lo)
            hov = (self.hover == cid or self.drag == cid) and en
            # ScreenMaster's slider: a hairline track, a white fill up to the value, a small round knob, and the value written on the right
            ui.rect(s, (*(dimmed(BORDER, 0.8) if not en else widgets.LINE_STRONG), 255), (tl, cy - 1, tlen, 2))
            dfrac = (DEFAULTS[cid] - lo) / (hi - lo)
            pygame.draw.line(s, (*DIM, 255), (tl + int(tlen * dfrac), cy - 4), (tl + int(tlen * dfrac), cy + 4))
            ui.rect(s, (*(TEXT if en else dimmed(TEXT)), 255), (tl, cy - 1, max(2, int(tlen * frac)), 2))
            kc = (tl + int(tlen * frac), cy)
            ui.circle(s, (*(TEXT if en else dimmed(TEXT)), 255), kc, 6 if hov else 5)
            shown = row["top"][1] if row.get("top") and c[cid] == row["top"][0] else f"{c[cid]}{row.get('unit', '%')}"
            self._txt(self.fb, shown, (R, cy - 9), tc, "r")
            self.hits.append((pygame.Rect(tl - 12, cy - 20, tlen + 24, 40), cid, "slider", None))
