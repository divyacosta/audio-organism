"""Settings panel (mouse + keyboard) and persistent settings.

Design: two tabs. "Cenas" picks what is drawn; "Ajustes" holds screen, image and render options (grouped cards). Every option has a label, a one-line explanation and a
clearly stateful control: toggle, segmented choice or slider. Disabled controls say why. Keyboard focus is
always visible. Changes apply instantly and show a short confirmation.
"""
import json
import os
import time

import pygame

APPDIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AudioOrganism")
PATH = os.path.join(APPDIR, "settings.json")

DEFAULTS = {"vsync": False, "fps_cap": 0, "fullscreen": False, "strobe": 2, "bursts": True, "bloom": 60, "react": 100,
            "effect": 0, "backend": 0, "style": 1, "funnel": True,
            # graphics (see PRESETS): render scale %, ray steps, ray-traced shadow / reflection / occlusion quality, lighting mode,
            # bloom levels, edge AA, panel density %, dynamic resolution and its FPS target
            "preset": 2, "res": 100, "steps": 72, "shadows": 2, "reflect": 2, "ao": 2, "rt": 1, "bloomq": 3, "aa": True, "detail": 100,
            "dynres": True, "fps_target": 60, "mblur": 180, "mblur_fps": 24, "auto_update": True}

# graphics presets; any manual change of one of these options switches the preset to "Personalizado"
GFX_KEYS = ("res", "steps", "shadows", "reflect", "ao", "bloomq", "aa", "detail", "rt", "mblur", "mblur_fps")
PRESETS = [
    ("Baixo",  dict(res=60,  steps=48,  shadows=0, reflect=0, ao=0, bloomq=1, aa=False, detail=55,  rt=0, mblur=0, mblur_fps=24)),
    ("Médio",  dict(res=80,  steps=60,  shadows=1, reflect=1, ao=1, bloomq=2, aa=True,  detail=75,  rt=0, mblur=90, mblur_fps=24)),
    ("Alto",   dict(res=100, steps=72,  shadows=2, reflect=2, ao=2, bloomq=3, aa=True,  detail=100, rt=1, mblur=180, mblur_fps=24)),
    ("Ultra",  dict(res=100, steps=110, shadows=3, reflect=3, ao=3, bloomq=4, aa=True,  detail=100, rt=1, mblur=270, mblur_fps=24)),
]
CUSTOM = len(PRESETS)


def match_preset(cfg):
    for i, (_, vals) in enumerate(PRESETS):
        if all(cfg.get(k) == v for k, v in vals.items()):
            return i
    return CUSTOM


def fresh():
    return dict(DEFAULTS)


def load_cfg():
    cfg = fresh()
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if k in cfg and type(v) is type(cfg[k]):
                cfg[k] = v
    except Exception:
        pass
    if cfg["effect"] > 2:
        cfg["effect"] = 0
    cfg["fullscreen"] = False        # never start full screen: the control window would be hidden behind it
    cfg["preset"] = match_preset(cfg)
    return cfg


def save_cfg(cfg):
    try:
        os.makedirs(APPDIR, exist_ok=True)
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
    except Exception:
        pass


# ------------------------------------------------------------------ design tokens
BG = (10, 9, 22)
SURFACE = (20, 18, 42)
SURFACE2 = (32, 30, 62)
BORDER = (52, 48, 96)
TEXT = (238, 240, 255)
DIM = (160, 168, 208)          # >= 4.5:1 on SURFACE
ACCENT = (255, 90, 210)
ACCENT2 = (80, 220, 255)
OK = (110, 235, 170)
DANGER = (255, 120, 150)
ON_ACCENT = (24, 8, 32)


def dimmed(c, f=0.45):
    return tuple(int(BG[i] + (c[i] - BG[i]) * f) for i in range(3))


FPS_OPTS = [("Livre", 0), ("60", 60), ("120", 120), ("144", 144), ("240", 240)]
TARGET_OPTS = [("30", 30), ("60", 60), ("90", 90), ("120", 120), ("144", 144)]
STROBE_OPTS = [("Desligado", 0), ("Suave", 1), ("Completo", 2)]
QUAL4_OPTS = [("Desligado", 0), ("Baixa", 1), ("Média", 2), ("Alta", 3)]
STYLE_OPTS = [("Normal", 0), ("Anime", 1)]
LIGHT_OPTS = [("Rápida", 0), ("Ray tracing", 1)]
BLOOM_OPTS = [("Desligado", 0), ("Mínimo", 1), ("Baixo", 2), ("Médio", 3), ("Alto", 4)]
PRESET_OPTS = [(n, i) for i, (n, _) in enumerate(PRESETS)] + [("Personalizado", CUSTOM)]
BACKEND_OPTS = [("Auto", 0), ("Vulkan", 1), ("Direct3D 12", 2)]

SCENES = [
    ("CENA", [
        dict(id="effect", kind="radio", value=0, label="Automático",
             help="O programa escolhe e muda de visual pela música"),
        dict(id="effect", kind="radio", value=1, label="Facetas",
             help="Painéis espelhados em 3 universos de cor, com cortes de caleidoscópio próprios"),
        dict(id="effect", kind="radio", value=2, label="Estrela",
             help="Barras de neon 3D caleidoscópicas, como sabres de luz"),
    ]),
]
GRAPHICS = [
    ("PREDEFINIÇÃO", [
        dict(id="preset", kind="seg", label="Qualidade gráfica", opts=PRESET_OPTS,
             help=lambda c: "Ajusta tudo de uma vez" if c["preset"] != CUSTOM else "Opções alteradas por você"),
    ]),
    ("TELA", [
        dict(id="fullscreen", kind="toggle", label="Tela cheia", chip="F",
             help="Duplo clique na imagem também alterna"),
        dict(id="vsync", kind="toggle", label="Sincronia vertical (VSync)", chip="V",
             help="Ligado: imagem sem rasgos, limitada ao monitor"),
        dict(id="fps_cap", kind="seg", label="Limite de FPS", opts=FPS_OPTS,
             help=lambda c: "Desativado enquanto o VSync está ligado" if c["vsync"] else "Máximo de quadros por segundo",
             enabled=lambda c: not c["vsync"]),
    ]),
    ("DESEMPENHO", [
        dict(id="res", kind="slider", label="Escala de resolução", lo=25, hi=100, step=5, unit="%",
             help="Menor = muito mais FPS, imagem mais suave  ·  duplo clique restaura"),
        dict(id="dynres", kind="toggle", label="Resolução dinâmica",
             help="Baixa a resolução sozinha quando o FPS cai do alvo"),
        dict(id="fps_target", kind="seg", label="FPS alvo", opts=TARGET_OPTS,
             help=lambda c: "A resolução dinâmica tenta manter este FPS" if c["dynres"] else "Ligue a resolução dinâmica para usar",
             enabled=lambda c: c["dynres"]),
        dict(id="detail", kind="slider", label="Densidade de painéis", lo=30, hi=100, step=5, unit="%",
             help="Menos camadas na cena: mais FPS  ·  duplo clique restaura"),
        dict(id="steps", kind="slider", label="Passos do raio", lo=24, hi=160, step=8, unit="",
             help="Mais passos = bordas mais corretas, mais peso"),
    ]),
    ("ILUMINAÇÃO", [
        dict(id="rt", kind="seg", label="Modo de iluminação", opts=LIGHT_OPTS,
             help=lambda c: "Reflexo de ambiente e brilho, sem raios: muito mais leve" if not c["rt"] else "Raios de verdade: sombras e reflexos entre painéis"),
        dict(id="shadows", kind="seg", label="Sombras", opts=QUAL4_OPTS,
             help=lambda c: "Raio de sombra entre painéis" if c["rt"] else "Só no modo Ray tracing",
             enabled=lambda c: c["rt"] == 1),
        dict(id="reflect", kind="seg", label="Reflexos", opts=QUAL4_OPTS,
             help=lambda c: "Painéis refletem as cores dos vizinhos" if c["rt"] else "Só no modo Ray tracing",
             enabled=lambda c: c["rt"] == 1),
        dict(id="ao", kind="seg", label="Oclusão ambiente", opts=QUAL4_OPTS,
             help=lambda c: "Escurece os cantos onde painéis se encontram" if c["rt"] else "Só no modo Ray tracing",
             enabled=lambda c: c["rt"] == 1),
    ]),
    ("IMAGEM", [
        dict(id="bloomq", kind="seg", label="Qualidade do brilho", opts=BLOOM_OPTS,
             help="Camadas do halo de luz: mais camadas, halo mais suave"),
        dict(id="bloom", kind="slider", label="Intensidade do brilho", lo=0, hi=200, step=10, unit="%",
             help="Força do halo  ·  duplo clique restaura"),
        dict(id="style", kind="seg", label="Estilo de imagem", opts=STYLE_OPTS,
             help="Anime: tons chapados com corte seco, contorno de tinta e fundo em faixas"),
        dict(id="mblur", kind="slider", label="Motion blur: ângulo do obturador", lo=0, hi=720, step=15, unit="°",
             help="Como no cinema: 0° desligado, 180° padrão de cinema, 360° obturador aberto, acima disso estilizado"),
        dict(id="mblur_fps", kind="seg", label="Quadros de referência do blur", opts=[("24", 24), ("30", 30), ("48", 48), ("60", 60)],
             help=lambda c: f"Obturador aberto por {c['mblur'] / 360.0 / c['mblur_fps'] * 1000:.0f} ms ({c['mblur']}° a {c['mblur_fps']} quadros)" if c["mblur"] else "Ligue o blur para usar",
             enabled=lambda c: c["mblur"] > 0),
        dict(id="funnel", kind="toggle", label="Efeito funil",
             help="Em build-ups e drops a câmera entra na pilha de camadas, como num funil"),
        dict(id="aa", kind="toggle", label="Suavizar bordas",
             help="Antialiasing das bordas dos painéis"),
    ]),
]
SETTINGS = [
    ("MÚSICA E LUZ", [
        dict(id="strobe", kind="seg", label="Flashes e strobe", chip="S", opts=STROBE_OPTS,
             help="Completo pisca rápido: cuidado com a luz"),
        dict(id="bursts", kind="toggle", label="Rajadas de 1/4 de tempo",
             help=lambda c: "Piscadas rápidas ocasionais no ritmo" if c["strobe"] == 2 else "Disponível só em Flashes: Completo",
             enabled=lambda c: c["strobe"] == 2),
        dict(id="react", kind="slider", label="Reatividade ao som", lo=25, hi=200, step=25, unit="%",
             help="Quanto a imagem reage à música  ·  duplo clique restaura"),
    ]),
    ("SISTEMA", [
        dict(id="backend", kind="seg", label="Backend gráfico", opts=BACKEND_OPTS,
             help="Vulkan ou Direct3D 12  ·  vale após reiniciar"),
        dict(id="auto_update", kind="toggle", label="Verificar atualizações ao abrir",
             help="Consulta o GitHub em segundo plano; só baixa se você clicar em Atualizar"),
    ]),
]
TABS = [("Cenas", SCENES), ("Gráficos", GRAPHICS), ("Ajustes", SETTINGS)]
NAMES = {"fullscreen": "Tela cheia", "vsync": "VSync", "fps_cap": "Limite de FPS", "strobe": "Flashes",
         "bursts": "Rajadas", "bloom": "Intensidade do brilho", "react": "Reatividade", "effect": "Cena", "res": "Resolução",
         "backend": "Backend", "preset": "Qualidade", "steps": "Passos do raio", "shadows": "Sombras", "reflect": "Reflexos",
         "ao": "Oclusão", "bloomq": "Brilho", "aa": "Suavizar bordas", "detail": "Densidade", "rt": "Iluminação",
         "style": "Estilo", "funnel": "Funil", "mblur": "Obturador", "auto_update": "Verificação de atualização", "mblur_fps": "Quadros de referência", "dynres": "Resolução dinâmica", "fps_target": "FPS alvo"}


class Menu:
    W = 560
    HEAD = 44
    ROW = 52
    GAP = 12
    FOOT = 64

    def __init__(self, cfg):
        self.cfg = cfg
        self.dirty = False
        self.dirty_t = 0.0
        self.need = True
        self.f = pygame.font.SysFont("segoeui", 15)
        self.fb = pygame.font.SysFont("segoeui", 15, bold=True)
        self.f_s = pygame.font.SysFont("segoeui", 12)
        self.f_sb = pygame.font.SysFont("segoeui", 12, bold=True)
        self.title = pygame.font.SysFont("segoeui", 22, bold=True)
        self.hits = []
        self.order = []
        self.order_val = []
        self.focus = 0
        self.kbd = False
        self.hover = None
        self.drag = None
        self.toast = None
        self.quit_armed = 0.0
        self.last_click = (None, 0.0)
        self.frects = {}
        self.scroll = 0
        self.view_h = 10 ** 6
        self.tab = int(os.environ.get("VIS_TAB", "0"))        # test hook
        self.live = ""
        self.info = ""                 # version / update status, shown in the header of the Ajustes tab
        self.upd_label = ""            # text of the "update to vX" button (empty = no update to offer)
        self.heights = []
        for _, secs in TABS:
            h = self.HEAD
            for _, rows in secs:
                h += 40 + len(rows) * self.ROW + 10 + self.GAP
            self.heights.append(h + self.FOOT + (52 if _ is TABS[2][0] else 0))      # the Ajustes tab has a second row of buttons (updates)
        self.H = max(self.heights)                  # the surface fits the tallest tab
        self.surf = pygame.Surface((self.W, self.H), pygame.SRCALPHA)

    # ------------------------------------------------------------ state
    def touch(self):
        self.dirty = self.need = True
        self.dirty_t = time.perf_counter()

    def max_scroll(self):
        return max(0, self.heights[self.tab] - self.view_h)

    def scroll_to_focus(self):
        if not self.order:
            return
        fr = self.frects.get(self.order[self.focus % len(self.order)])
        if fr is None:
            return
        if fr.top < self.scroll + 8:
            self.scroll = max(0, fr.top - 8)
        elif fr.bottom > self.scroll + self.view_h - 8:
            self.scroll = min(self.max_scroll(), fr.bottom - self.view_h + 8)

    def set_live(self, text):
        """Short live status ("96 FPS · 1280×720 · 80%") shown in the header of the Gráficos tab."""
        if text != self.live:
            self.live = text
            if self.tab == 1:
                self.need = True

    def say(self, text):
        self.toast = (text, time.perf_counter() + 2.2)
        self.need = True

    def enabled(self, row):
        fn = row.get("enabled")
        return True if fn is None else bool(fn(self.cfg))

    def find(self, cid):
        for _, secs in TABS:
            for _, rows in secs:
                for r in rows:
                    if r["id"] == cid:
                        return r
        return None

    def set_value(self, cid, value, announce=True):
        if cid == "preset":
            if value == CUSTOM or not (0 <= value < len(PRESETS)):
                return
            self.cfg.update(PRESETS[value][1])
            self.cfg["preset"] = value
            self.touch()
            if announce:
                self.say(f"Qualidade: {PRESETS[value][0]}")
            return
        if self.cfg.get(cid) == value:
            return
        self.cfg[cid] = value
        if cid in GFX_KEYS:
            self.cfg["preset"] = match_preset(self.cfg)
        self.touch()
        if announce:
            row = self.find(cid)
            if row["kind"] == "toggle":
                self.say(f"{NAMES[cid]}: {'ligado' if value else 'desligado'}")
            elif row["kind"] == "seg":
                lbl = [l for l, v in row["opts"] if v == value][0]
                self.say(f"{NAMES[cid]}: {lbl}" + ("  ·  reinicie para aplicar" if cid == "backend" else ""))

    def adjust(self, cid, d):
        row = self.find(cid)
        if row is None or not self.enabled(row):
            return
        if row["kind"] == "toggle":
            self.set_value(cid, d > 0 if d != 0 else not self.cfg[cid])
        elif row["kind"] == "seg":
            vals = [v for _, v in row["opts"]]
            i = vals.index(self.cfg[cid]) if self.cfg[cid] in vals else 0
            self.set_value(cid, vals[max(0, min(len(vals) - 1, i + d))])
        elif row["kind"] == "slider":
            v = max(row["lo"], min(row["hi"], self.cfg[cid] + d * row["step"]))
            self.set_value(cid, v, announce=False)

    def slider_from_x(self, cid, x):
        row = self.find(cid)
        tl, tw = self.slider_geo
        t = max(0.0, min(1.0, (x - tl) / tw))
        v = row["lo"] + t * (row["hi"] - row["lo"])
        self.set_value(cid, int(round(v / row["step"]) * row["step"]), announce=False)

    def press(self, cid):
        """Activate a button; returns an action string for the caller."""
        now = time.perf_counter()
        if cid.startswith("tab"):
            self.tab = int(cid[3:])
            self.scroll = 0
            self.need = True
            return None
        if cid == "reset":
            self.cfg.update(fresh())
            self.cfg["preset"] = match_preset(self.cfg)
            self.touch()
            self.say("Padrões restaurados")
            return None
        if cid in ("bench", "update_check", "update_apply"):
            return cid
        if cid == "quit":
            if self.quit_armed > now:
                return "quit"
            self.quit_armed = now + 3.0
            self.need = True
        return None

    # -------------------------------------------------------------- input
    def key(self, k, mod=0):
        self.kbd = True
        self.need = True
        n = len(self.order)
        if n == 0:
            return None
        if k in (pygame.K_DOWN, pygame.K_TAB):
            step = -1 if (k == pygame.K_TAB and mod & pygame.KMOD_SHIFT) else 1
            self.focus = (self.focus + step) % n
        elif k == pygame.K_UP:
            self.focus = (self.focus - 1) % n
        elif k in (pygame.K_LEFT, pygame.K_RIGHT):
            cid = self.order[self.focus].split("#")[0]
            if cid.startswith("tab"):
                self.press(f"tab{max(0, min(len(TABS) - 1, self.tab + (-1 if k == pygame.K_LEFT else 1)))}")
            elif self.find(cid)["kind"] == "radio":
                vals = [r["value"] for r in [x for _, rows in TABS[self.tab][1] for x in rows] if r["id"] == cid]
                i = vals.index(self.cfg[cid]) if self.cfg[cid] in vals else 0
                self.set_value(cid, vals[max(0, min(len(vals) - 1, i + (-1 if k == pygame.K_LEFT else 1)))])
            else:
                self.adjust(cid, -1 if k == pygame.K_LEFT else 1)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            fkey = self.order[self.focus]
            cid = fkey.split("#")[0]
            if cid in ("reset", "quit") or cid.startswith("tab"):
                return self.press(cid)
            row = self.find(cid)
            if row["kind"] == "radio":
                self.set_value(cid, self.order_val[self.focus % len(self.order)])
            elif row["kind"] == "toggle":
                self.adjust(cid, 0)
            elif row["kind"] == "seg":
                vals = [v for _, v in row["opts"]]
                i = vals.index(self.cfg[cid]) if self.cfg[cid] in vals else 0
                if self.enabled(row):
                    self.set_value(cid, vals[(i + 1) % len(vals)])
        elif k == pygame.K_ESCAPE:
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
            if self.hover and self.find(self.hover) and self.find(self.hover)["kind"] == "slider":
                self.adjust(self.hover, 1 if ev.y > 0 else -1)
            else:
                self.scroll = max(0, min(self.max_scroll(), self.scroll - ev.y * 48))
                self.need = True
            return None
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
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and hit:
            rect, cid, kind, arg = hit
            fk = f"{cid}#{arg}" if kind == "radio" else cid
            if fk in self.order:
                self.focus = self.order.index(fk)
            self.need = True
            if kind == "btn":
                return self.press(cid)
            row = self.find(cid)
            if row is None or not self.enabled(row):
                return None
            if kind == "toggle":
                self.adjust(cid, 0)
            elif kind in ("seg", "radio"):
                self.set_value(cid, arg)
            elif kind == "slider":
                now = time.perf_counter()
                if self.last_click[0] == cid and now - self.last_click[1] < 0.4:
                    default = DEFAULTS[cid]
                    self.set_value(cid, default, announce=False)
                    self.say(f"{NAMES[cid]} restaurado: {default}{self.find(cid).get('unit', '%')}")
                    self.last_click = (None, 0.0)
                else:
                    self.last_click = (cid, now)
                    self.drag = cid
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
        if not self.need:
            return False
        self.need = False
        s, c = self.surf, self.cfg
        s.fill((0, 0, 0, 0))
        self.hits, self.order, self.frects, self.order_val = [], [], {}, []
        W = self.W
        # tab bar
        x = 0
        for i, (name, _) in enumerate(TABS):
            cid = f"tab{i}"
            tw = max(110, self.fb.size(name)[0] + 40)
            r = pygame.Rect(x, 0, tw, 36)
            sel, hov = i == self.tab, self.hover == cid
            pygame.draw.rect(s, (*(ACCENT if sel else (SURFACE2 if hov else SURFACE)), 255), r, border_radius=10)
            if not sel:
                pygame.draw.rect(s, (*BORDER, 255), r, width=1, border_radius=10)
            self._txt(self.fb, name, (r.centerx, r.y + 8), ON_ACCENT if sel else TEXT, "c")
            self.hits.append((r, cid, "btn", None))
            self.order.append(cid)
            self.order_val.append(None)
            self.frects[cid] = r
            x += tw + 8
        if self.tab == 1 and self.live:
            self._txt(self.f_sb, self.live, (W - 4, 10), OK, "r")
        elif self.tab == 2 and self.info:
            self._txt(self.f_sb, self.info, (W - 4, 10), OK if self.upd_label else DIM, "r")
        else:
            self._txt(self.f_s, "salvo automaticamente", (W - 4, 11), DIM, "r")

        y = self.HEAD
        for title, rows in TABS[self.tab][1]:
            ch = 40 + len(rows) * self.ROW + 10
            pygame.draw.rect(s, (*SURFACE, 255), (0, y, W, ch), border_radius=14)
            pygame.draw.rect(s, (*BORDER, 255), (0, y, W, ch), width=1, border_radius=14)
            self._txt(self.f_sb, "  ".join(title), (18, y + 14), ACCENT)
            ry = y + 40
            for row in rows:
                self._row(row, ry)
                ry += self.ROW
            y += ch + self.GAP

        # footer buttons
        fy = y + 4
        armed = self.quit_armed > now
        if self.tab >= 1:
            self._button("reset", pygame.Rect(0, fy, 200, 42), "Restaurar padrões", False)
        if self.tab == 1:
            self._button("bench", pygame.Rect(212, fy, 250, 42), "Medir desempenho (10 s)", False)
        if self.tab == 2:
            self._button("update_check", pygame.Rect(0, fy + 52, 250, 42), "Verificar atualização", False)
            if self.upd_label:
                self._button("update_apply", pygame.Rect(262, fy + 52, 298, 42), self.upd_label, False, True)
        self._button("quit", pygame.Rect(W - 230, fy, 230, 42), "Clique de novo para sair" if armed else "Sair do programa", True, armed)

        # keyboard focus ring, drawn once the full focus order is known
        if self.kbd and self.order:
            fr = self.frects.get(self.order[self.focus % len(self.order)])
            if fr is not None:
                pygame.draw.rect(s, (*ACCENT2, 255), fr.inflate(6, 6), width=2, border_radius=12)
        return True

    def _button(self, cid, rect, label, danger, armed=False):
        self.hits.append((rect, cid, "btn", None))
        self.order.append(cid)
        self.order_val.append(None)
        self.frects[cid] = rect
        hov = self.hover == cid
        col = DANGER if danger else ACCENT2
        fill = col if armed else (SURFACE2 if hov else SURFACE)
        pygame.draw.rect(self.surf, (*fill, 255), rect, border_radius=10)
        pygame.draw.rect(self.surf, (*col, 255), rect, width=2 if (hov or armed) else 1, border_radius=10)
        tcol = ON_ACCENT if armed else (TEXT if hov else col)
        self._txt(self.fb, label, (rect.centerx, rect.y + 11), tcol, "c")

    def _row(self, row, y):
        s, c = self.surf, self.cfg
        cid, kind = row["id"], row["kind"]
        en = self.enabled(row)
        W = self.W
        fkey = cid if kind != "radio" else f"{cid}#{row['value']}"
        rowr = pygame.Rect(10, y, W - 20, self.ROW - 4)
        if self.hover == cid and en:
            pygame.draw.rect(s, (*SURFACE2, 255), rowr, border_radius=10)
        tc, dc = (TEXT, DIM) if en else (dimmed(TEXT, 0.5), dimmed(DIM, 0.55))
        lw = self._txt(self.f, row["label"], (22, y + 7), tc)
        if row.get("chip"):
            cr = pygame.Rect(22 + lw + 10, y + 8, 20, 20)
            pygame.draw.rect(s, (*BORDER, 255), cr, width=1, border_radius=5)
            self._txt(self.f_sb, row["chip"], (cr.centerx, cr.y + 2), dc, "c")
        h = row["help"](c) if callable(row["help"]) else row["help"]
        self._txt(self.f_s, h, (22, y + 29), dc)
        cy = y + (self.ROW - 4) // 2
        R = W - 26
        self.frects[fkey] = rowr
        if en:
            self.order.append(fkey)
            self.order_val.append(row.get("value"))

        if kind == "radio":
            sel = c[cid] == row["value"]
            rc = (R - 12, cy)
            pygame.draw.circle(s, (*(ACCENT if sel else BORDER), 255), rc, 11, 0 if sel else 2)
            if sel:
                pygame.draw.circle(s, (*ON_ACCENT, 255), rc, 4)
            self.hits.append((rowr, cid, "radio", row["value"]))
        elif kind == "toggle":
            on = c[cid]
            pill = pygame.Rect(R - 46, cy - 13, 46, 26)
            col = OK if on else (66, 64, 112)
            pygame.draw.rect(s, (*(col if en else dimmed(col)), 255), pill, border_radius=13)
            kx = pill.right - 13 if on else pill.left + 13
            pygame.draw.circle(s, (255, 255, 255) if en else dimmed((255, 255, 255)), (kx, pill.centery), 9)
            self._txt(self.f_s, "Ligado" if on else "Desligado", (pill.left - 10, cy - 8), (OK if (on and en) else dc), "r")
            self.hits.append((rowr, cid, "toggle", None))
        elif kind == "seg":
            widths = [max(56, self.f.size(l)[0] + 26) for l, _ in row["opts"]]
            x = R - sum(widths)
            n = len(widths)
            for i, ((lbl, val), w) in enumerate(zip(row["opts"], widths)):
                r = pygame.Rect(x, cy - 17, w, 34)
                sel = c[cid] == val
                hov = self.hover == cid and en
                fill = ACCENT if sel else ((44, 42, 84) if hov else (34, 32, 66))
                if not en:
                    fill = dimmed(fill, 0.6)
                radii = dict(border_top_left_radius=9 if i == 0 else 0, border_bottom_left_radius=9 if i == 0 else 0,
                             border_top_right_radius=9 if i == n - 1 else 0, border_bottom_right_radius=9 if i == n - 1 else 0)
                pygame.draw.rect(s, (*fill, 255), r, **radii)
                pygame.draw.rect(s, (*BORDER, 255), r, width=1, **radii)
                tcol = ON_ACCENT if sel else (tc if en else dc)
                self._txt(self.fb if sel else self.f, lbl, (r.centerx, r.y + 7), tcol, "c")
                self.hits.append((r, cid, "seg", val))
                x += w
        else:
            lo, hi = row["lo"], row["hi"]
            pw = 56
            tr = R - pw - 14
            tl = tr - 170
            self.slider_geo = (tl, 170)
            frac = (c[cid] - lo) / (hi - lo)
            hov = (self.hover == cid or self.drag == cid) and en
            pygame.draw.rect(s, (*(dimmed((54, 52, 96), 0.8) if not en else (54, 52, 96)), 255), (tl, cy - 3, 170, 6), border_radius=3)
            dfrac = (DEFAULTS[cid] - lo) / (hi - lo)
            pygame.draw.line(s, (*DIM, 255), (tl + int(170 * dfrac), cy + 7), (tl + int(170 * dfrac), cy + 11))
            pygame.draw.rect(s, (*(ACCENT if en else dimmed(ACCENT)), 255), (tl, cy - 3, max(4, int(170 * frac)), 6), border_radius=3)
            kc = (tl + int(170 * frac), cy)
            pygame.draw.circle(s, (255, 255, 255) if en else dimmed((255, 255, 255)), kc, 10 if hov else 9)
            pygame.draw.circle(s, (*(ACCENT if en else dimmed(ACCENT)), 255), kc, 10 if hov else 9, 2)
            vr = pygame.Rect(R - pw, cy - 14, pw, 28)
            pygame.draw.rect(s, (34, 32, 66, 255), vr, border_radius=8)
            self._txt(self.fb, f"{c[cid]}{row.get('unit', '%')}", (vr.centerx, vr.y + 4), tc, "c")
            self.hits.append((pygame.Rect(tl - 12, cy - 20, 170 + 24, 40), cid, "slider", None))
