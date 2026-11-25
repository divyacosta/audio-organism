"""The three steps of "+ Nova cena": what to see, colours, name. The state is `self.wizard` (None when the steps are closed) and this is what every key and every click
does to it. It is a part of the panel (class Menu inherits it): through `self` it reads and changes the settings, the tab, the scene lists and the toast of the
panel, and the steps are drawn by the control window (control.py, `_draw_wizard`). Kept apart so the steps can be read, and changed, without reading the panel.

What it needs from the panel: cfg, tab, scene_view, scroll, scroll2, dd_open, need, say(), touch(), rebuild_scenes(), is_dirty(), new_scene(), play_scene() and _push().
"""
import copy

import pygame

import scenes as SC
from settings import TAB_LIVE, TAB_SCENES


class WizardMixin:
    def in_wizard(self):
        return self.scene_view == "wizard" and self.wizard is not None

    def _wizard_name(self):
        names = {s.get("scene_name") for s in self.cfg["scenes"]}
        n = 1
        while ("Minha cena" if n == 1 else f"Minha cena {n}") in names:
            n += 1
        return "Minha cena" if n == 1 else f"Minha cena {n}"

    def start_wizard(self):
        """"+ Nova cena": three steps (what to see, colours, name) in the Estúdio instead of an empty editor of layers. Cancelar goes back to where it began; Criar cena
        puts the new scene on the air and goes to the Palco. With unsaved changes in the scene that is open it does not start (they would be lost)."""
        if self.scene_view == "editor" and self.is_dirty():
            self.tab = TAB_SCENES
            self.say("Alterações não salvas nesta cena: Salvar ou Descartar antes de criar outra")
            self.rebuild_scenes()
            return
        bases = SC.wizard_bases()
        self.wizard = dict(step=0, bases=bases, pick=0, pal=0, draft=copy.deepcopy(bases[0]), from_tab=self.tab, name=self._wizard_name(), fresh=True)       # fresh: the name was not touched yet, the first key replaces it all
        self.tab = TAB_SCENES
        self.scene_view = "wizard"
        self.scroll = self.scroll2 = 0
        self.dd_open = None
        self.rebuild_scenes()
        self.touch()

    def wizard_pick(self, i):
        """Step 1: a look. The picture of the scene being built changes at once (it keeps the colours already chosen)."""
        w = self.wizard
        if w is None or not 0 <= i < len(w["bases"]):
            return
        w["pick"] = i
        w["draft"] = copy.deepcopy(w["bases"][i])
        w["draft"]["scene_palette"] = w["pal"]
        self.need = True

    def wizard_palette(self, k):
        """Step 2: the colours (0 = the ones of the look itself, k = palette k)."""
        w = self.wizard
        if w is None:
            return
        w["pal"] = max(0, min(int(k), len(self.cfg.get("palettes") or [])))
        w["draft"]["scene_palette"] = w["pal"]
        self.need = True

    def wizard_next(self):
        w = self.wizard
        if w is None:
            return
        if w["step"] < 2:
            w["step"] += 1
            self.scroll = 0
            self.need = True
        else:
            self.finish_wizard()

    def wizard_back(self):
        w = self.wizard
        if w is None:
            return None
        if w["step"] > 0:
            w["step"] -= 1
            self.scroll = 0
            self.need = True
        else:
            self.cancel_wizard()
        return None

    def wizard_goto(self, k):
        """Back to a step that is already done (a click on its pill); the scene being built stays as it is. Steps to come are only reached with Continuar."""
        w = self.wizard
        if w is not None and 0 <= k < w["step"]:
            w["step"] = k
            self.scroll = 0
            self.need = True

    def cancel_wizard(self):
        """Out of the three steps without a new scene, to the tab they were opened from."""
        w, self.wizard = self.wizard, None
        self.scene_view = "gallery"
        self.tab = w["from_tab"] if w else TAB_SCENES
        self.scroll = self.scroll2 = 0
        self.rebuild_scenes()
        self.touch()

    def finish_wizard(self):
        """Criar cena: the scene is made from the look, the colours and the name, goes on the air at once and the Palco shows it. (In the Logo the name is also the
        text on the screen.)"""
        w = self.wizard
        if w is None:
            return
        name = (w["name"].strip() or self._wizard_name())[:28]
        sc = copy.deepcopy(w["draft"])
        sc.update(scene_name=name, scene_auto=True, scene_palette=w["pal"])
        if int(sc.get("scene_visual", 1)) == 9:
            sc["gen_text"] = name
        self._push()
        self.cfg["scenes"].append(sc)
        i = len(self.cfg["scenes"]) - 1
        self.wizard = None
        self.scene_view = "gallery"
        self.tab = TAB_LIVE
        self.scroll = self.scroll2 = 0
        self.rebuild_scenes()
        self.play_scene(i)
        self.say(f"{name}: criada e no ar")

    def wizard_blank(self):
        """Advanced: instead of a look, an empty scene to build layer by layer (what "Nova cena" used to be)."""
        if not self.cfg.get("advanced"):
            return
        self.cancel_wizard()
        self.tab = TAB_SCENES
        self.new_scene()

    def wizard_key(self, e):
        """Keys while the three steps are open: Enter goes on (and creates, on the last step), Esc goes back, on the last step the letters write the name. The other
        keys do nothing (the digits would play scenes behind the steps); Ctrl combinations are left to the others."""
        w = self.wizard
        if w is None or self.scene_view != "wizard" or getattr(e, "mod", 0) & pygame.KMOD_CTRL:
            return False
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.wizard_next()
        elif e.key == pygame.K_ESCAPE:
            self.wizard_back()
        elif w["step"] == 2 and e.key == pygame.K_BACKSPACE:
            w["name"] = "" if w.get("fresh") else w["name"][:-1]                  # the name that comes ready is all selected: Backspace clears it, a letter replaces it
            w["fresh"] = False
        elif w["step"] == 2 and getattr(e, "unicode", "") and e.unicode.isprintable() and (w.get("fresh") or len(w["name"]) < 28):
            w["name"] = e.unicode if w.get("fresh") else w["name"] + e.unicode
            w["fresh"] = False
        self.need = True
        return True
