"""Deck window: a DJ-player style screen for whatever is playing (in the spirit of a Pioneer CDJ display).

  header        what is playing (state, genre guess), time, BPM, key, and chips for energy / beat / phrase
  bars strip    the current phrase (orange) and the current bar (blue), with a marker at the position
  waveform      scrolling three-band waveform: low = blue, mid = orange, high = white; beat grid with the bars numbered; cue markers
  info row      BPM, elapsed time, confidence, key, energy
  overview      the whole track so far, with the cue points (drops, breakdowns, build-ups), and a time ruler

Everything is drawn from what the Analyzer knows (analysis.py); nothing here listens to the audio itself.
"""
import math
import os
import time

os.environ.setdefault("SDL_RENDER_DRIVER", "software")

import numpy as np
import pygame

NOTE_IDX = {n: i for i, n in enumerate(('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'))}


def mmss_(sec):
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"

import ui
import widgets as wg

W, H = 1180, 600
LOW = wg.SEL                      # graves: the blue 004FEC (outer layer of the wave)
MID = wg.ACCENT                      # médios: the red EB0838
HIGH = wg.TEXT                  # agudos: the light EBEBEB (the core)
BLUE, ORANGE, WHITE_W = LOW, MID, HIGH  # names used by the wide Deck window
RED = wg.ACCENT
YELLOW = (255, 110, 130)                # build-up: a lighter red
CUE_COLORS = [(232, 48, 48), (60, 160, 255), wg.OK, (140, 70, 240), wg.OK, (240, 110, 30), (50, 80, 235), (240, 210, 30)]
KIND_COLOR = {"DROP": RED, "BREAK": (150, 156, 176), "BUILD": YELLOW}
KIND_LABEL = {"DROP": "Drop", "BREAK": "Breakdown", "BUILD": "Build-up"}
# the sections of the timeline: state -> (colour, name, tint of the band over the wave)
def _ink(c):
    """Text colour for a bar filled with c: dark on light fills, light on dark ones."""
    return wg.BG if (0.30 * c[0] + 0.59 * c[1] + 0.11 * c[2]) > 120 else wg.TEXT


STATE_SHORT = {"HIGH ENERGY": "Alta", "BREAKDOWN": "Break", "SILENCE": "Mudo", "GROOVE": "Gr."}
STATE_STYLE = {"CALM": (wg.SEL, "Calmo", 22), "GROOVE": (wg.SEL, "Groove", 16), "HIGH ENERGY": (wg.TEXT, "Energia alta", 16),
               "BREAKDOWN": (KIND_COLOR["BREAK"], "Breakdown", 26), "DROP": (RED, "Drop", 30), "SILENCE": (wg.BORDER, "Silêncio", 40)}
PX_PER_SEC = 93.75                       # one pixel per analysis hop (512 samples at 48 kHz)
HEAD_H = 66
ZOOM_Y, ZOOM_H = 150, 260
PLAYHEAD_X = int(W * 0.70)


def _dim(c, k):
    return (int(c[0] * k), int(c[1] * k), int(c[2] * k))


class DeckWindow:
    def __init__(self, pos=None, headless=False):
        self.surf = pygame.Surface((W, H))
        self.fonts = {}
        for name, role, bold in (("xs", "cap", False), ("s", "label", False), ("sb", "label", True), ("m", "lead", True), ("l", "h1", True), ("xl", "h2", True), ("big", "display", True)):
            self.fonts[name] = wg.font(role, bold)
        self.win = self.ren = self.tex = None
        self.id = None
        self.last = -1.0
        self.interval = 1.0 / 30.0
        self.ov_cache = (0.0, None)
        self.mouse = None                                        # pointer position over the live content, for hover
        self.live_hits = []
        self.zoom_idx = 1                                        # 0: 4 s, 1: 8 s, 2: 16 s of history
        self.frozen, self.frozen_t = None, 0.0                   # a frozen waveform stops scrolling (hop index it stopped at)
        self.strip_cb = None                                     # draws the strip of scenes (the control window owns the thumbnails)
        self.blend = 0                                           # 0 = blended layers (screen), 1 = solid layers
        self.live_end = 0
        self.cfg = {}                                         # the settings (the control window hands them over): the Palco shows the three big controls from them
        self.preview_cb = None                                # draws the live picture into a rect (the control window owns it)
        self.next_cb = None                                   # draws the picture of the scene that comes next into a rect (surf, rect, scene index)
        self.detail_open = False                              # the details of the music and of the program are closed until asked
        self.tour_open = False                                # the first-use card (the control window sets it from the settings)
        self.tap_t = 0.0                                      # when the last tap of the tap tempo was asked for (the control window copies it from the menu): the BPM flashes
        self.tour_cb = None                                   # tour_cb(i): step i of the first-use card was done (the control window keeps it in the settings)
        self.tour_close = None                                # closes the card for good (the control window keeps that in the settings too)
        self._heard_since = self._quiet_since = self._slow_since = None      # since when the sound is heard / missing / the picture is slow: a warning needs a few seconds of it
        self._tour_all_t = None
        self.ear_open = True                                 # the card "O que estou ouvindo" is open (a click on its title closes it; the control window keeps the choice)
        self._n_now = self._t_now = 0
        self.zoom = pygame.Surface((PLAYHEAD_X, ZOOM_H))        # the scrolling waveform is kept and shifted, only the new columns are drawn
        self.zoom_n, self.zoom_i0 = -1, -1
        self.ov_surf, self.ov_key = None, None
        if not headless:
            from pygame._sdl2 import video
            self.win = video.Window("Audio Organism - Deck", (W, H), position=pos)
            self.ren = video.Renderer(self.win)
            self.tex = video.Texture(self.ren, (W, H), streaming=True)
            self.id = self.win.id

    # ------------------------------------------------------------------ helpers
    def _t(self, font, text, pos, color, anchor="l"):
        img = self.fonts[font].render(text, True, color)
        x, y = pos
        if anchor == "r":
            x -= img.get_width()
        elif anchor == "c":
            x -= img.get_width() // 2
        self.surf.blit(img, (x, y))
        return img.get_width()

    @staticmethod
    def _fmt(sec, ms=False):
        sec = max(0.0, sec)
        m, s = int(sec // 60), sec - 60 * int(sec // 60)
        return f"{m:02d}:{int(s):02d}" + (f".{int((s - int(s)) * 1000):03d}" if ms else "")

    def _columns(self, d, i0, i1, x0, mid_y, half, dim_before=None):
        """Draw waveform columns for hops i0..i1-1 starting at x0, one pixel each."""
        s = self.surf
        for k in range(i1 - i0):
            i = i0 + k
            x = x0 + k
            pk, lo, mi, hi = d[0, i], d[1, i], d[2, i], d[3, i]
            f = 1.0 if (dim_before is None or i >= dim_before) else 0.45
            hl = max(1, int(lo ** 1.5 * half))
            hm = max(1, int(mi ** 1.5 * half * 0.85))
            hh = max(1, int(hi ** 1.5 * half * 0.60))
            pygame.draw.line(s, _dim(BLUE, f), (x, mid_y - hl), (x, mid_y + hl))
            pygame.draw.line(s, _dim(ORANGE, f), (x, mid_y - hm), (x, mid_y + hm))
            pygame.draw.line(s, _dim(WHITE_W, f), (x, mid_y - hh), (x, mid_y + hh))

    # --------------------------------------------------------------------- draw
    def draw(self, an, genre="?", now_t=0.0):
        s = self.surf
        s.fill((0, 0, 0))
        silent = an.silence > 0.6
        # ---- header
        ui.rect(s, (22, 22, 24), (0, 0, W, HEAD_H))
        ui.rect(s, (112, 126, 160), (0, 0, 96, HEAD_H))
        self._t("l", "AO", (48, 8), wg.BG, "c")
        self._t("xs", "AO VIVO", (48, 42), wg.BG, "c")
        title = "SEM ÁUDIO" if silent else an.state + (f"  ·  {genre}" if genre not in ("?", None, "") else "")
        self._t("l", title, (112, 4), wg.TEXT)
        bpm = f"{an.bpm:5.1f}" if an.bpm > 0 else " --"
        self._t("l", f"{self._fmt(an.track_time)}    {bpm}    {an.key_name}", (136, 34), wg.TEXT)
        chips = (("ENERGIA", f"{an.level10}/10"), ("BATIDA", f"{an.beat_in_bar + 1} / {an.bpb}" if an.bpm > 0 else "--"),
                 ("FRASE", f"{an.phrase_pos + 1} / {an.phrase_len}" if an.bpm > 0 else "--"))
        for i, (a, b) in enumerate(chips):
            r = pygame.Rect(W - 3 * 128 + i * 128 + 6, 6, 118, HEAD_H - 12)
            ui.rect(s, wg.BORDER, r, border_radius=4)
            self._t("sb", a, (r.centerx, r.y + 6), (200, 200, 208), "c")
            self._t("m", b, (r.centerx, r.y + 26), wg.TEXT, "c")

        # ---- bars strip: phrase (orange) and bar (blue)
        x_a, x_b = 380, 1130
        for row, (label, col) in enumerate((("Frase", ORANGE), ("Compasso", (40, 130, 240)))):
            y = 92 + row * 30
            self._t("xs", label, (x_a - 14, y - 9), col, "r")
            pygame.draw.line(s, col, (x_a, y), (x_b, y), 3)
        n_bars = an.phrase_len
        for k in range(n_bars + 1):
            x = x_a + (x_b - x_a) * k // n_bars
            red = k in (0, n_bars)
            pygame.draw.line(s, RED if red else (225, 225, 230), (x, 86), (x, 98 if not red else 102), 2)
        for k in range(an.bpb + 1):
            x = x_a + (x_b - x_a) * k // an.bpb
            red = k in (0, an.bpb)
            pygame.draw.line(s, RED if red else (225, 225, 230), (x, 116), (x, 128 if not red else 132), 2)
        if an.bpm > 0 and not silent:
            xp = x_a + int((x_b - x_a) * an.phrase_phase)
            pygame.draw.line(s, (255, 255, 255), (xp, 80), (xp, 108), 3)
            xb = x_a + int((x_b - x_a) * an.bar_phase)
            pygame.draw.line(s, (255, 255, 255), (xb, 110), (xb, 138), 3)
        learned = "aprendida" if an.phrase_learned else "padrão"
        self._t("xs", f"{an.phrase_len} compassos ({learned})", (x_b, 66 + 2), (130, 130, 140), "r")

        # ---- scrolling waveform
        mid_y = ZOOM_Y + ZOOM_H // 2
        half = ZOOM_H // 2 - 14
        pygame.draw.line(s, (36, 36, 40), (0, mid_y), (W, mid_y))
        n = an.deck_n
        span = min(PLAYHEAD_X, n)
        d = n - self.zoom_n
        zs = self.surf
        self.surf = self.zoom                                   # _columns draws on self.surf: aim it at the cache for a moment
        if self.zoom_n < 0 or an.trk_i0 != self.zoom_i0 or d <= 0 or d >= PLAYHEAD_X:
            self.zoom.fill((0, 0, 0))
            if span > 0:
                self._columns(an.deck, n - span, n, PLAYHEAD_X - span, mid_y - ZOOM_Y, half, dim_before=an.trk_i0)
        else:
            self.zoom.scroll(-d, 0)
            ui.rect(self.zoom, (0, 0, 0), (PLAYHEAD_X - d, 0, d, ZOOM_H))
            self._columns(an.deck, n - d, n, PLAYHEAD_X - d, mid_y - ZOOM_Y, half, dim_before=an.trk_i0)
        self.surf = zs
        self.zoom_n, self.zoom_i0 = n, an.trk_i0
        self.surf.blit(self.zoom, (0, ZOOM_Y))
        # beat grid (past) and predicted grid (future)
        top_t, bot_t = ZOOM_Y + 2, ZOOM_Y + ZOOM_H - 2
        for (t, bib, barn) in an.beat_log:
            x = PLAYHEAD_X - int((an.now_t - t) * PX_PER_SEC)
            if x < 0 or x > PLAYHEAD_X:
                continue
            L = 16 if bib == 0 else 9
            c = RED if bib == 0 else (220, 220, 225)
            pygame.draw.line(s, c, (x, top_t), (x, top_t + L))
            pygame.draw.line(s, c, (x, bot_t), (x, bot_t - L))
            if bib == 0 and (barn + 1) % 4 == 0 and barn >= 0:
                self._t("sb", str(barn + 1), (x + 2, bot_t + 2), (235, 235, 240), "c")
        if an.bpm > 0 and not silent:
            period = 60.0 / an.bpm
            d0 = (1.0 - an.phase) * period
            k = 0
            while True:
                x = PLAYHEAD_X + int((d0 + k * period) * PX_PER_SEC)
                if x > W - 2:
                    break
                bib = (an.beat_in_bar + 1 + k) % an.bpb
                L = 16 if bib == 0 else 9
                c = (150, 40, 40) if bib == 0 else (90, 90, 96)
                pygame.draw.line(s, c, (x, top_t), (x, top_t + L))
                pygame.draw.line(s, c, (x, bot_t), (x, bot_t - L))
                k += 1
        # cue markers inside the window
        for j, (i, kind) in enumerate(an.marks):
            x = PLAYHEAD_X - (n - i)
            if 0 <= x <= PLAYHEAD_X:
                c = KIND_COLOR.get(kind, (200, 200, 200))
                pygame.draw.line(s, c, (x, ZOOM_Y + 20), (x, ZOOM_Y + ZOOM_H - 20), 2)
                ui.rect(s, c, (x - 7, ZOOM_Y + 4, 14, 14), border_radius=2)
                self._t("xs", kind[0], (x, ZOOM_Y + 3), (0, 0, 0), "c")
        # playhead
        pygame.draw.line(s, (255, 255, 255), (PLAYHEAD_X, ZOOM_Y - 4), (PLAYHEAD_X, ZOOM_Y + ZOOM_H + 6), 3)
        pygame.draw.polygon(s, wg.TEXT, [(PLAYHEAD_X - 9, ZOOM_Y + ZOOM_H + 16), (PLAYHEAD_X + 9, ZOOM_Y + ZOOM_H + 16), (PLAYHEAD_X, ZOOM_Y + ZOOM_H + 4)])
        if silent:
            self._t("l", "Toque uma música no computador", (W // 2, mid_y - 16), wg.TEXT, "c")

        # ---- info row
        iy = 430
        r = pygame.Rect(24, iy, 190, 78)
        ui.rect(s, wg.TEXT, r, width=2)
        self._t("s", "BPM", (r.x + 8, r.y + 4), (255, 150, 60))
        ui.rect(s, wg.TEXT, (r.right - 62, r.y, 62, 20))
        self._t("xs", "AUTO", (r.right - 31, r.y + 2), (10, 10, 10), "c")
        self._t("big", f"{an.bpm:5.1f}" if an.bpm > 0 else "--", (r.centerx, r.y + 14), (255, 130, 40), "c")
        self._t("big", self._fmt(an.track_time, True), (300, iy - 4), wg.TEXT)
        self._t("s", f"CONFIANÇA {an.conf * 100:3.0f}%", (305, iy + 66), wg.DIM)
        self._t("s", f"DROPS {sum(1 for _, k in an.marks if k == 'DROP')}", (470, iy + 66), wg.DIM)
        self._t("s", f"VOLUME {an.lf:4.0f} dB", (580, iy + 66), wg.DIM)
        kx = 820
        self._t("s", "ENERGIA", (kx, iy + 2), wg.DIM)
        for i in range(10):
            on = i < an.level10
            ui.rect(s, (60, 200, 90) if on and i < 6 else ((240, 190, 40) if on and i < 8 else ((235, 60, 60) if on else wg.BORDER)), (kx + i * 16, iy + 24, 12, 22))
        self._t("s", "KEY", (W - 90, iy + 2), wg.DIM, "c")
        self._t("xl", an.key_name, (W - 90, iy + 22), wg.TEXT, "c")

        # ---- overview of the whole track
        oy, oh = 522, 52
        ox, ow = 24, W - 48
        T = an.track_time
        view = max(T, 120.0)
        pps = ow / view
        cols = int(T * pps)
        pygame.draw.line(s, (50, 50, 54), (ox, oy + oh // 2), (ox + ow, oy + oh // 2))
        if cols > 2 and an.deck_n - an.trk_i0 > 4:
            key = (cols, an.trk_i0)
            if now_t - self.ov_cache[0] > 0.5 or self.ov_surf is None or key != self.ov_key:
                self.ov_cache = (now_t, None)
                seg = an.deck[1:4, an.trk_i0:an.deck_n]
                idx = (np.arange(seg.shape[1]) * cols // seg.shape[1])
                starts = np.searchsorted(idx, np.arange(cols))
                red = np.maximum.reduceat(seg, starts, axis=1)
                surf = pygame.Surface((max(cols, 1), oh))
                surf.fill((0, 0, 0))
                half = oh // 2 - 4
                mid = oh // 2 + 2
                for x in range(min(cols, red.shape[1])):
                    lo, mi, hi = red[0, x] ** 1.5, red[1, x] ** 1.5, red[2, x] ** 1.5
                    pygame.draw.line(surf, BLUE, (x, mid - int(lo * half)), (x, mid + int(lo * half)))
                    pygame.draw.line(surf, ORANGE, (x, mid - int(mi * half * 0.85)), (x, mid + int(mi * half * 0.85)))
                    pygame.draw.line(surf, WHITE_W, (x, mid - int(hi * half * 0.6)), (x, mid + int(hi * half * 0.6)))
                surf.set_colorkey((0, 0, 0))
                self.ov_surf, self.ov_key = surf, key
            s.blit(self.ov_surf, (ox, oy))
        for j, (i, kind) in enumerate(an.marks[:16]):
            x = ox + int((i - an.trk_i0) * an.hop_dt * pps)
            if x < ox or x > ox + ow:
                continue
            c = KIND_COLOR.get(kind, CUE_COLORS[j % 8])
            ui.rect(s, c, (x - 7, oy - 16, 14, 14))
            self._t("xs", chr(ord("A") + j % 26), (x, oy - 17), (0, 0, 0), "c")
            pygame.draw.line(s, c, (x, oy - 2), (x, oy + oh), 1)
        xe = ox + cols
        pygame.draw.line(s, (255, 255, 255), (xe, oy - 2), (xe, oy + oh))
        pygame.draw.polygon(s, wg.TEXT, [(xe - 7, oy + oh + 12), (xe + 7, oy + oh + 12), (xe, oy + oh + 2)])
        step = 30 if view <= 360 else 60
        for sec in range(0, int(view) + 1, step):
            x = ox + int(sec * pps)
            pygame.draw.line(s, (120, 120, 128), (x, oy + oh + 2), (x, oy + oh + (9 if sec % 60 == 0 else 5)))
            if sec % 60 == 0:
                self._t("xs", f"{sec // 60}:00", (x, oy + oh + 6), (190, 190, 198), "c")


    # ------------------------------------------------------------ the "Ao vivo" tab (timeline layout)
    def _chip(self, x, y, text, color=None, border=None, font="s", pad=10, h=22):
        """A rounded pill; returns its width."""
        return wg.chip(self.surf, self.fonts[font], x, y, text, color, border, pad, h)

    def _button(self, rect, label, bid, color=None):
        hov = self.mouse is not None and rect.collidepoint(self.mouse)
        wg.button(self.surf, self.fonts["sb"], rect, label, "tone", hover=hov, tone=color or wg.SEL, radius=10)
        self.live_hits.append((rect, bid))

    BLEND_ALPHA = (0.80, 0.62, 0.75)         # opacity of the low / mid / high layers when they are transparent

    def _wave_surface(self, lo, mi, hi, hpx, half, dim):
        """The three-band waveform as an image: three solid layers (graves, médios, agudos) drawn one over the other at full opacity.
        lo / mi / hi are 0..1 per column, dim is the brightness per column (dimmer before the track started)."""
        cols = len(lo)
        rows = np.abs(np.arange(hpx) - hpx // 2)[:, None]
        bg = np.array(wg.BG, float) / 255.0
        img = np.broadcast_to(bg, (hpx, cols, 3)).copy()
        for h, col, al in zip((lo * half, mi * half * 0.85, hi * half * 0.6), (LOW, MID, HIGH), self.BLEND_ALPHA):
            m = (rows <= h[None, :])[..., None].astype(float)
            c = np.array(col, float) / 255.0
            img = np.where(m > 0, c, img)                              # solid layers, one over the other: no transparency, no blend mode
        img = img * dim[None, :, None]
        arr = np.clip(img * 255.0, 0, 255).astype(np.uint8)
        return pygame.surfarray.make_surface(arr.transpose(1, 0, 2))

    def _card(self, rect):
        ui.rect(self.surf, wg.SURFACE, rect, border_radius=14)
        ui.rect(self.surf, wg.BORDER, rect, width=1, border_radius=14)

    def predict(self, an):
        """What the analysis expects next: seconds to the end of the phrase, and a sentence about it."""
        if an.bpm <= 0:
            return None, "Aprendendo o ritmo…", False
        period = 60.0 / an.bpm
        beats_left = (an.bpb - an.beat_in_bar - an.phase) + an.bpb * max(0, an.phrase_len - an.phrase_pos - 1)
        t_end = beats_left * period
        bars = max(1, int(round(beats_left / an.bpb)))
        if an.tension > 0.55:
            return t_end, f"Drop em ~{bars} compassos", True
        return t_end, f"Mudança em ~{bars} compassos", False

    TOUR = (("Toque uma música", "No YouTube, Spotify…", "Som detectado"),
            ("Escolha uma cena", "Clique numa cena", "Cena escolhida"),
            ("Tela cheia", "Botão ao lado ou tecla F", "Esc volta ao painel"))

    def _wrap(self, font, text, w):
        lines, cur = [], ""
        for word in text.split():
            t = (cur + " " + word).strip()
            if self.fonts[font].size(t)[0] <= w or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = word
        return lines + [cur] if cur else lines

    TOUR_BTN = 82

    def _tour_card(self, Wc):
        """The first-use card: three steps that tick themselves as they are done (sound heard, scene chosen, full screen), one short line each.
        Returns its height (drawn at the top of the surface)."""
        s = self.surf
        marks = int((self.cfg or {}).get("tour_marks", 0))
        n_done = sum(1 for i in range(3) if marks >> i & 1)
        cur = next((i for i in range(3) if not marks >> i & 1), -1)
        all_done = n_done == 3
        h = 82
        s.fill(wg.BG, pygame.Rect(0, 0, Wc, h + 12))
        self._card(pygame.Rect(0, 0, Wc, h))
        self._t("xs", "PRONTO  ·  você já sabe o essencial" if all_done else "COMECE POR AQUI", (14, 9), wg.OK if all_done else wg.TITLE)
        br = pygame.Rect(Wc - 14 - self.TOUR_BTN, 6, self.TOUR_BTN, 26)
        self._button(br, "Fechar" if all_done else "Pular", "tour:close")
        if not all_done:
            self._t("xs", f"{n_done} de 3", (br.x - 10, 10), wg.DIM, "r")
        colw = (Wc - 28 - 2 * 14) // 3
        cy = 53
        for i, (title, todo, done) in enumerate(self.TOUR):
            x = 14 + i * (colw + 14)
            is_done = bool(marks >> i & 1)
            c = (x + 11, cy)
            if is_done:
                ui.circle(s, wg.SEL, c, 11)
                pygame.draw.lines(s, wg.ON_SEL, False, [(x + 5, cy), (x + 9, cy + 4), (x + 17, cy - 4)], 2)
            elif i == cur:
                ui.circle(s, wg.SEL, c, 11)
                pygame.draw.circle(s, wg.SEL, c, 14, 1)
                self._t("sb", str(i + 1), (c[0], cy - 9), wg.ON_SEL, "c")
            else:
                pygame.draw.circle(s, wg.CTRL, c, 11, 1)
                self._t("sb", str(i + 1), (c[0], cy - 9), wg.DIM, "c")
            self._t("sb", title, (x + 32, 37), wg.TEXT if i == cur else wg.DIM)
            self._t("s", self._fit_text("s", done if is_done else todo, colw - 36), (x + 32, 56), wg.OK if is_done else wg.DIM)
        return h + 12

    def _slow_fps(self):
        """Below what rate the picture counts as slow: 25, or 80% of what the person asked for when they asked for less (an output cap, or one frame out of
        two): a picture that runs at the rate it was told to is not "Travando"."""
        cfg = self.cfg or {}
        target = float(cfg.get("fps_out", 60) or 60)
        if int(cfg.get("rrate", 0) or 0) > 0:
            target /= int(cfg["rrate"]) + 1
        return min(25.0, 0.8 * target)

    def _tick(self, an, fps, status):
        """What the Palco keeps an eye on over time: for how long the sound has been heard or missing and the picture slow (a warning needs a few seconds of
        it, or it would flicker at the start), and the steps of the first-use card."""
        now = time.perf_counter()
        silent = an.silence > 0.6
        self._heard_since = None if silent else (self._heard_since or now)
        self._quiet_since = (self._quiet_since or now) if silent else None
        self._slow_since = (self._slow_since or now) if (fps < self._slow_fps() and not silent) else None
        if not self.tour_open:
            return
        if self.tour_cb is not None:
            if self._heard_since is not None and now - self._heard_since > 2.0:
                self.tour_cb(0)
            if ((status or {}).get("keys") or {}).get("fullscreen"):
                self.tour_cb(2)
        if int((self.cfg or {}).get("tour_marks", 0)) == 7:                      # all three done: the card says so for a few seconds and goes away by itself
            self._tour_all_t = self._tour_all_t or now
            if now - self._tour_all_t > 4.0 and self.tour_close is not None:
                self.tour_close()

    def draw_live(self, an, fps, lat, vsync, status, genre, now_t):
        self._tick(an, fps, status)
        if not self.tour_open:
            return self._draw_live_body(an, fps, lat, vsync, status, genre, now_t)
        full = self.surf
        Wc = full.get_width()
        th = self._tour_card(Wc)
        n, mouse = len(self.live_hits), self.mouse
        hits0 = []
        self.surf = full.subsurface(pygame.Rect(0, th, Wc, full.get_height() - th))
        if mouse is not None:
            self.mouse = (mouse[0], mouse[1] - th)
        try:
            end = self._draw_live_body(an, fps, lat, vsync, status, genre, now_t)
        finally:
            self.surf, self.mouse = full, mouse
        self.live_hits[:] = [(r.move(0, th), b) for r, b in self.live_hits]
        # the button of the card was added before the body cleared the list: add it again at its place
        self.live_hits.append((pygame.Rect(Wc - 14 - self.TOUR_BTN, 6, self.TOUR_BTN, 26), "tour:close"))
        self.live_end = end + th
        return self.live_end

    SECTION = {"CALM": 0, "BREAKDOWN": 0, "BREAK": 0, "SILENCE": 0, "GROOVE": 1, "BUILD": 2, "DROP": 2, "HIGH ENERGY": 2}
    RIGHT_W = 330

    def _draw_live_body(self, an, fps, lat, vsync, status, genre, now_t):
        """The Palco. It changes with the state of things: no sound (a guide to get the sound in), a problem (a warning with the button that solves it, above),
        playing (what is on the air, what comes next, the scenes; the music now and the buttons on the right). What the program hears in detail is in
        Sistema > Áudio."""
        s = self.surf
        Wc = s.get_width()
        s.fill(wg.BG)
        self.live_hits = []
        self._n_now = an.deck_n
        self._t_now = an.now_t
        now = time.perf_counter()
        y = 0
        warn = self._warning(an, fps, status, now)
        if warn is not None:
            y = self._banner(Wc, *warn) + 12
        quiet = an.silence > 0.6 and self._quiet_since is not None and now - self._quiet_since > 2.5         # no sound for a while: the guide takes the place of the air and the next
        two = Wc >= 900
        rw = self.RIGHT_W if two else Wc
        lw = Wc - rw - 16 if two else Wc
        a = self._sub_x(0, y, lw, lambda: self._left(an, status, lw, quiet))
        b = self._sub_x(lw + 16 if two else 0, y if two else a + 14, rw, lambda: self._right(an, status, rw))
        self.live_end = max(a, b) + 6
        return self.live_end

    def _sub_x(self, x0, y0, w, fn):
        """Draw fn() on the box of the surface at (x0, y0), w wide: hits and the pointer are moved to match. Returns where it ends (in the whole surface)."""
        full = self.surf
        n, mouse = len(self.live_hits), self.mouse
        self.surf = full.subsurface(pygame.Rect(x0, y0, w, full.get_height() - y0))
        if mouse is not None:
            self.mouse = (mouse[0] - x0, mouse[1] - y0)
        try:
            end = fn()
        finally:
            self.surf, self.mouse = full, mouse
        self.live_hits[n:] = [(r.move(x0, y0), b) for r, b in self.live_hits[n:]]
        return y0 + end

    def _warning(self, an, fps, status, now):
        """(text, colour, (button label, hit id) or None) when something is wrong; None when all is well (the Palco then shows no numbers about itself)."""
        if status is not None and not status.get("shader_ok", True):
            return "Erro no efeito visual: a imagem voltou ao efeito anterior", wg.DANGER, None
        if self._slow_since is not None and now - self._slow_since > 3.0:
            return f"Imagem travando ({fps:.0f} FPS): a tela grande não está aguentando", wg.TEXT, ("Melhorar sozinho", "fix:quality")
        return None

    def _banner(self, Wc, text, color, fix):
        s = self.surf
        r = pygame.Rect(0, 0, Wc, 44)
        ui.rect(s, (40, 33, 20), r, border_radius=12)
        ui.rect(s, color, r, width=1, border_radius=12)
        tx = Wc - 12
        if fix is not None:
            lab, bid = fix
            fw = self.fonts["sb"].size(lab)[0] + 28
            fr = pygame.Rect(Wc - 8 - fw, 7, fw, 30)
            wg.button(s, self.fonts["sb"], fr, lab, "tone", hover=self.mouse is not None and fr.collidepoint(self.mouse), tone=color, radius=8)
            self.live_hits.append((fr, bid))
            tx = fr.x - 10
        self._t("s", self._fit_text("s", text, tx - 16), (16, 12), color)
        return r.bottom

    def _silent_card(self, an, Wc, y0):
        """No sound for a while: say so, show where the program listens and how much comes in, and lead to where the sound is chosen."""
        s = self.surf
        cfg = self.cfg or {}
        w = min(Wc, 620)
        r = pygame.Rect((Wc - w) // 2, y0, w, 210)
        ui.rect(s, wg.SURFACE, r, border_radius=14)
        ui.rect(s, wg.BORDER, r, width=1, border_radius=14)
        x = r.x + 24
        self._t("l", "Não estou ouvindo nada", (x, r.y + 20), wg.TEXT)
        self._t("s", self._fit_text("s", "Toque uma música no computador: a imagem começa sozinha quando o som chegar.", w - 48), (x, r.y + 58), wg.DIM)
        src = str(cfg.get("adev_name") or "") or "O que toca no computador"
        self._t("xs", "OUVINDO", (x, r.y + 94), wg.TITLE)
        self._t("s", self._fit_text("s", src, w - 140), (x + 80, r.y + 91), wg.TEXT)
        self._t("xs", "ENTRADA", (x, r.y + 120), wg.TITLE)
        mr = pygame.Rect(x + 80, r.y + 122, w - 140, 8)
        ui.rect(s, wg.SURFACE2, mr, border_radius=4)
        lv = max(0.0, min(1.0, float(getattr(an, "level", 0.0)) * 4.0))
        if lv > 0.01:
            ui.rect(s, wg.DIM, pygame.Rect(mr.x, mr.y, max(6, int(mr.w * lv)), mr.h), border_radius=4)
        br = pygame.Rect(x, r.y + 150, self.fonts["sb"].size("Escolher o som")[0] + 32, 38)
        wg.button(s, self.fonts["sb"], br, "Escolher o som", "primary", hover=self.mouse is not None and br.collidepoint(self.mouse), radius=10)
        self.live_hits.append((br, "fix:sound"))
        return r.bottom

    def _left(self, an, status, W, quiet=False):
        """On the air, what comes next and the scenes (no sound for a while: the guide to get the sound in, then the scenes)."""
        s = self.surf
        info = (status or {}).get("image") or {}
        if quiet:
            y = self._silent_card(an, W, 0) + 18
            if self.strip_cb is not None:
                y += self.strip_cb(s, y, W, self.live_hits)
            return y
        # ---- on the air
        r = pygame.Rect(0, 0, W, 64)
        ui.rect(s, wg.SURFACE, r, border_radius=12)
        ui.rect(s, wg.BORDER, r, width=1, border_radius=12)
        pw = self.fonts["xs"].size("NO AR")[0] + 14
        wg.pill(s, self.fonts["xs"], pygame.Rect(14, 21, pw, 22), "NO AR", wg.ACCENT, wg.ON_ACCENT)
        ew = self.fonts["xs"].size("Editar esta cena")[0] + 22
        er = pygame.Rect(W - 12 - ew, 18, ew, 28)
        wg.button(s, self.fonts["xs"], er, "Editar esta cena", "plain", hover=self.mouse is not None and er.collidepoint(self.mouse), radius=er.h // 2)
        self.live_hits.append((er, "edit:live"))
        tx = 14 + pw + 12
        self._t("sb", self._fit_text("sb", info.get("scene", "--"), er.x - tx - 12), (tx, 11), wg.TEXT)
        sub = "  ·  ".join(b for b in (info.get("style"), "Câmera " + str(info.get("camera") or "--"), "Ritmo " + str(info.get("movement") or "--")) if b)
        self._t("xs", self._fit_text("xs", sub, er.x - tx - 12), (tx, 36), wg.DIM)
        y = r.bottom + 12
        y = self._next_card(an, status, W, y) + 12
        y = self._phrase_bar(an, info, W, y) + 18
        if self.strip_cb is not None:
            y += self.strip_cb(s, y, W, self.live_hits)
        return y

    def _next_card(self, an, status, W, y):
        """What comes next. A scene waiting for its moment shows its picture, when it comes in and a button to bring it at once; otherwise a sentence of
        what the automatic change will do (it picks the scene only at the moment of the change)."""
        s = self.surf
        info = (status or {}).get("image") or {}
        keys = (status or {}).get("keys") or {}
        pend = int(info.get("pending_scene", -1))
        scn = (self.cfg or {}).get("scenes") or []
        if 0 <= pend < len(scn):
            th = 126
            r = pygame.Rect(0, y, W, th + 24)
            ui.rect(s, wg.SURFACE, r, border_radius=12)
            ui.rect(s, wg.TEXT, r, width=2, border_radius=12)
            tr = pygame.Rect(12, y + 12, th * 16 // 9, th)
            ui.rect(s, wg.BG, tr, border_radius=8)
            if self.next_cb is not None:
                self.next_cb(s, tr, pend)
            x = tr.right + 16
            self._t("xs", "A SEGUIR", (x, y + 14), wg.TITLE)
            self._t("m", self._fit_text("m", scn[pend]["scene_name"], W - x - 12), (x, y + 32), wg.TEXT)
            eta = info.get("pending_eta")
            when = ("entra agora", "entra no próximo compasso", "entra na próxima frase", "entra no próximo evento da música", "entra na próxima frase")[int(info.get("scene_when", 2)) % 5]
            self._t("s", self._fit_text("s", when + (f"  ·  em ~{eta:.0f} s" if eta is not None and eta >= 0.5 else ""), W - x - 12), (x, y + 64), wg.DIM)
            lab = "Trocar agora"
            br = pygame.Rect(x, y + th + 24 - 12 - 36, self.fonts["sb"].size(lab)[0] + 32, 36)
            wg.button(s, self.fonts["sb"], br, lab, "primary", hover=self.mouse is not None and br.collidepoint(self.mouse), radius=10)
            self.live_hits.append((br, "next:now"))
            return r.bottom
        r = pygame.Rect(0, y, W, 58)
        ui.rect(s, wg.SURFACE, r, border_radius=12)
        ui.rect(s, wg.BORDER, r, width=1, border_radius=12)
        self._t("xs", "A SEGUIR", (14, y + 10), wg.TITLE)
        if keys.get("auto"):
            when = ("a cada momento forte", "no próximo compasso", "na próxima frase", "no próximo evento da música", "no tempo marcado")[int(info.get("scene_when", 2)) % 5]
            txt = f"O Automático escolhe e troca {when}"
        else:
            txt = "Automático desligado: clique numa cena para tocar"
        self._t("s", self._fit_text("s", txt, W - 28), (14, y + 28), wg.TEXT)
        return r.bottom

    def _phrase_bar(self, an, info, W, y):
        """Where the music is in its phrase, and what the analysis expects at its end (the scenes change at the end of a phrase)."""
        s = self.surf
        t_end, txt, drop = self.predict(an)
        self._t("xs", "A MÚSICA  ·  FRASE", (0, y), wg.TITLE)
        self._t("xs", txt, (W, y), wg.TEXT if drop else wg.DIM, "r")
        y += 20
        n = max(1, int(an.phrase_len))
        gap = 4
        bw = (W - gap * (n - 1)) / n
        cur = int(an.phrase_pos) if an.bpm > 0 else -1
        for i in range(n):
            r = pygame.Rect(int(i * (bw + gap)), y, max(2, int(bw)), 10)
            col = wg.SEL if i < cur else (wg.TEXT if i == cur else wg.SURFACE2)
            if i == cur:
                frac = max(0.0, min(1.0, (an.beat_in_bar + an.phase) / max(1, an.bpb)))
                ui.rect(s, wg.SURFACE2, r, border_radius=3)
                col_r = pygame.Rect(r.x, r.y, max(2, int(r.w * frac)), r.h)
                ui.rect(s, wg.TEXT, col_r, border_radius=3)
                continue
            ui.rect(s, col, r, border_radius=3)
        return y + 10

    def _right(self, an, status, W):
        """The music now (in the words of the rest of the program), the big buttons and the three controls of every scene."""
        s = self.surf
        keys = (status or {}).get("keys") or {}
        silent = an.silence > 0.6
        y = 0
        # ---- the big buttons (each one says its key in the picture window)
        fs_on = bool(keys.get("fullscreen"))
        self._big_button(pygame.Rect(0, y, W, 50), "Sair da tela cheia" if fs_on else "Tela cheia", "key:f", primary=True, hint="tecla F")
        y += 58
        self._auto_pair(pygame.Rect(0, y, W, 50), bool(keys.get("auto")))
        y += 58
        y += 4
        y = self._macros(0, y, W) + 20
        # ---- the music now
        cardy = y
        y = cardy + 14
        self._t("xs", "A MÚSICA AGORA", (14, y), wg.TITLE)
        y += 22
        bpm_txt = f"{an.bpm:.0f}" if an.bpm > 0 and not silent else "--"
        flash = max(0.0, 1.0 - (time.perf_counter() - self.tap_t) / 0.25)
        manual = an.manual_bpm > 0
        self._t("xl", bpm_txt, (14, y - 6), wg.ACCENT if flash > 0 else (wg.ACCENT2 if manual else wg.TEXT))
        bx = 14 + self.fonts["xl"].size(bpm_txt)[0] + 10
        self._t("xs", "BPM", (bx, y + 4), wg.DIM)
        self._t("s", an.key_name if an.key_name != "--" and not silent else "", (bx, y + 22), wg.DIM)
        tw = 64
        tr = pygame.Rect(W - 14 - tw, y + 2, tw, 30)
        wg.button(s, self.fonts["xs"], tr, "TAP  T", "plain", hover=self.mouse is not None and tr.collidepoint(self.mouse), radius=8)
        self.live_hits.append((tr, "bpm:tap"))
        if manual:
            ar = pygame.Rect(tr.x - 6 - 54, y + 2, 54, 30)
            wg.button(s, self.fonts["xs"], ar, "Auto", "plain", hover=self.mouse is not None and ar.collidepoint(self.mouse), radius=8)
            self.live_hits.append((ar, "bpm:auto"))
        y += 52
        sec = -1 if silent else self.SECTION.get(an.state, 1)
        sw = (W - 28 - 8) // 3
        for i, name in enumerate(("Calmo", "Normal", "Intenso")):
            sr = pygame.Rect(14 + i * (sw + 4), y, sw, 28)
            on = i == sec
            ui.rect(s, wg.ACCENT if on else wg.CTRL_FILL, sr, border_radius=8)
            self._t("xs", name, (sr.centerx, sr.y + 6), wg.ON_ACCENT if on else wg.DIM, "c")
        y += 40
        nb = len(an.bands)
        third = lambda a, b: float(sum(float(an.bands[k]) for k in range(a, b))) / max(1, b - a)
        vals = (("Graves", third(0, nb // 3)), ("Médios", third(nb // 3, 2 * nb // 3)), ("Agudos", third(2 * nb // 3, nb)),
                ("Batida", float(an.kick)), ("Energia", (an.level10 - 1) / 9.0))
        for name, v in vals:
            self._t("xs", name, (14, y), wg.TEXT)
            br = pygame.Rect(84, y + 5, W - 84 - 14, 6)
            ui.rect(s, wg.SURFACE2, br, border_radius=3)
            v = 0.0 if silent else max(0.0, min(1.0, v))
            if v > 0.01:
                ui.rect(s, wg.ACCENT, pygame.Rect(br.x, br.y, max(3, int(br.w * v)), br.h), border_radius=3)
            y += 22
        lab = "Ver o que o programa ouve  ›"
        lr = pygame.Rect(14, y + 2, self.fonts["xs"].size(lab)[0] + 4, 24)
        self._t("xs", lab, (lr.x, lr.y + 4), wg.SEL if (self.mouse is not None and lr.collidepoint(self.mouse)) else wg.ACCENT2)
        self.live_hits.append((lr, "ear:open"))
        y += 32
        card = pygame.Rect(0, cardy, W, y - cardy)
        ui.rect(s, wg.BORDER, card, width=1, border_radius=12)
        y += 12
        self._keys(status, y, 0)                                              # every key of the picture window, as buttons (lit = on)
        return y + 22 + ((len(self.KEYS) + 3) // 4) * 54 - 8

    def _macros(self, mx, cy, mw_):
        """Intensidade, Velocidade and Cores: the three controls that change every scene at once."""
        import menu as M
        s = self.surf
        cfg = self.cfg or {}
        changed = (cfg.get("macro_energy", 100), cfg.get("macro_speed", 100), cfg.get("macro_pal", 0)) != (100, 100, 0)
        self._t("xs", "PARA TODAS AS CENAS", (mx, cy), wg.TITLE)
        if changed:
            rr = pygame.Rect(mx + mw_ - 132, cy - 6, 132, 24)
            wg.button(s, self.fonts["xs"], rr, "Voltar ao normal", "plain", hover=self.mouse is not None and rr.collidepoint(self.mouse), radius=8)
            self.live_hits.append((rr, "macro:reset:0"))
        cy += 22
        self._t("sb", "Intensidade", (mx, cy), wg.TEXT)
        cy += 22
        self._steps(mx, cy, mw_, 38, M.MACRO_ENERGY, M.macro_index(M.MACRO_ENERGY, cfg.get("macro_energy", 100)), "energy")
        cy += 48
        self._t("sb", "Velocidade", (mx, cy), wg.TEXT)
        cy += 22
        self._steps(mx, cy, mw_, 38, M.MACRO_SPEED, M.macro_index(M.MACRO_SPEED, cfg.get("macro_speed", 100)), "speed")
        cy += 48
        self._t("sb", "Cores", (mx, cy), wg.TEXT)
        cy += 22
        pals = (cfg.get("palettes") or [])[:5]
        n = 1 + len(pals)
        per = 3 if mw_ < 520 else n
        cg = 6
        cw = (mw_ - cg * (per - 1)) // per
        cur = int(cfg.get("macro_pal", 0))
        for i in range(n):
            r = pygame.Rect(mx + (i % per) * (cw + cg), cy + (i // per) * 54, cw, 48)
            sel = i == cur
            hov = self.mouse is not None and r.collidepoint(self.mouse)
            ui.rect(s, wg.SURFACE2 if not hov else wg.HOVER_FILL, r, border_radius=10)
            if i == 0:
                self._t("s", "Da cena", (r.centerx, r.centery - 9), wg.TEXT, "c")
            else:
                cols = [tuple(c) for c in pals[i - 1]["colors"][:4]] or [(128, 128, 128)]
                sw = (r.w - 12) // len(cols)
                for k, col in enumerate(cols):
                    ui.rect(s, col, pygame.Rect(r.x + 6 + k * sw, r.y + 6, sw - 2 if k < len(cols) - 1 else sw, 22), border_radius=4)
                self._t("xs", self._fit_text("xs", pals[i - 1]["name"], r.w - 8), (r.centerx, r.y + 31), wg.TEXT if sel else wg.DIM, "c")
            ui.rect(s, wg.SEL if sel else (wg.HOVER_EDGE if hov else wg.CTRL), r, width=3 if sel else 1, border_radius=10)
            self.live_hits.append((r, f"macro:pal:{i}"))
        return cy + ((n + per - 1) // per) * 54

    def _sub(self, y0, fn):
        """Draw fn() on the part of the surface from y0 down: it sees a surface that starts at y0, the hits and the pointer are moved to match."""
        full = self.surf
        n, mouse = len(self.live_hits), self.mouse
        self.surf = full.subsurface(pygame.Rect(0, y0, full.get_width(), full.get_height() - y0))
        if mouse is not None:
            self.mouse = (mouse[0], mouse[1] - y0)
        try:
            end = fn()
        finally:
            self.surf, self.mouse = full, mouse
        self.live_hits[n:] = [(r.move(0, y0), b) for r, b in self.live_hits[n:]]
        return y0 + end

    def _big_button(self, rect, label, bid, primary=False, on=False, hint=None):
        hov = self.mouse is not None and rect.collidepoint(self.mouse)
        font = "m" if self.fonts["m"].size(label)[0] <= rect.w - 14 else "sb"                  # a narrow button writes smaller instead of overflowing
        wg.button(self.surf, self.fonts[font], rect, label, "primary" if primary else ("select" if on else "plain"), hover=hov, hint=hint, hint_font=self.fonts["xs"], radius=12)
        self.live_hits.append((rect, bid))

    AUTO_OPT_W = 96

    def _auto_pair(self, rect, on):
        """Troca automática (the big switch) and, at its right, Opções: which scenes the automatic change may bring, and when (Sistema > Automático)."""
        ow = self.AUTO_OPT_W
        bw = rect.w - ow - 6
        name = "Troca automática" if self.fonts["sb"].size("Troca automática")[0] <= bw - 14 else "Troca auto."          # a narrow window gets the short name, not a cut word
        self._big_button(pygame.Rect(rect.x, rect.y, bw, rect.h), name, "auto:toggle", on=on, hint="ligada" if on else "desligada")
        self._big_button(pygame.Rect(rect.right - ow, rect.y, ow, rect.h), "Opções", "auto:settings", hint="do automático")

    def _steps(self, x, y, w, h, table, cur_idx, kind):
        """A row of big choices (Intensidade, Velocidade): one button per step, the one in use lit."""
        s = self.surf
        n = len(table)
        gap = 6
        bw = (w - gap * (n - 1)) // n
        for i, (name, _) in enumerate(table):
            r = pygame.Rect(x + i * (bw + gap), y, bw, h)
            sel = i == cur_idx
            hov = self.mouse is not None and r.collidepoint(self.mouse)
            fk = "sb" if sel else "s"
            if self.fonts[fk].size(name)[0] > r.w - 8:                     # a narrow column writes smaller instead of cutting the word
                fk = "xs"
            wg.button(s, self.fonts[fk], r, name, "select" if sel else "plain", hover=hov, radius=10)
            self.live_hits.append((r, f"macro:{kind}:{i}"))

    def _palco_top(self, an, fps, status, genre, Wc):
        """The picture of the air with who is on, the two big buttons, and the three big controls. Returns where it ends."""
        import menu as M
        s = self.surf
        cfg = self.cfg or {}
        info = (status or {}).get("image") or {}
        keys = (status or {}).get("keys") or {}
        wide = Wc >= 900
        gap = 14
        pw = int(min(Wc * (0.50 if wide else 0.60), 760 if wide else 400))
        ph = pw * 9 // 16
        pr = pygame.Rect(0, 0, pw, ph)
        ui.rect(s, wg.BG, pr, border_radius=12)
        if self.preview_cb is not None:
            self.preview_cb(s, pr)
        else:
            self._t("s", "a imagem aparece aqui", (pr.centerx, pr.centery - 8), wg.DIM, "c")
        ui.rect(s, wg.BORDER, pr, width=1, border_radius=12)
        x0 = pw + gap
        rw = Wc - x0
        # ---- who is on, how it is going
        silent = an.silence > 0.6
        learning = an.bpm <= 0 or an.conf < 0.5 or an.active_t < 8.0
        ok = status is None or status.get("shader_ok", True)
        now = time.perf_counter()
        fix = None                                                             # (label, hit id) of the button that solves the warning
        if not ok:
            ht, hc = "Erro no efeito visual", wg.DANGER
        elif silent:
            ht, hc = "Sem som: toque uma música", wg.TEXT
            if self._quiet_since is not None and now - self._quiet_since > 2.5:           # the music may be playing somewhere the program is not listening to
                ht, fix = "Sem som", ("Escolher o som", "fix:sound")
        elif self._slow_since is not None and now - self._slow_since > 3.0:
            ht, hc, fix = "Travando", wg.TEXT, ("Melhorar sozinho", "fix:quality")
        elif learning:
            ht, hc = "Entendendo o ritmo da música…", wg.ACCENT2
        else:
            ht, hc = "Tudo certo", wg.OK
        self._t("xs", "AO VIVO", (x0, 2), wg.TITLE)
        ew = self.fonts["xs"].size("Editar esta cena")[0] + 20                  # the way into the editor of the scene that is on the air
        er = pygame.Rect(x0 + rw - ew, 0, ew, wg.MIN_H)
        wg.button(s, self.fonts["xs"], er, "Editar esta cena", "plain", hover=self.mouse is not None and er.collidepoint(self.mouse), radius=er.h // 2)
        self.live_hits.append((er, "edit:live"))
        self._t("m", self._fit_text("m", info.get("scene", "--"), rw - 4), (x0, 20), wg.TEXT)
        bits = []
        if not silent:
            if an.bpm > 0:
                bits.append(f"{an.bpm:.0f} BPM")
            if an.key_name != "--":
                bits.append(an.key_name)
            if genre not in ("?", None, ""):
                bits.append(str(genre))
        self._t("s", self._fit_text("s", "  ·  ".join(bits) if bits else ("" if silent else "ouvindo…"), rw - 4), (x0, 44), wg.DIM)
        ui.circle(s, hc, (x0 + 5, 76), 5)
        tx = x0 + rw
        if fix is not None:                                                    # a warning comes with the button that solves it
            lab, bid = fix
            fw = self.fonts["s"].size(lab)[0] + 24
            fr = pygame.Rect(x0 + rw - fw, 64, fw, 24)
            hov = self.mouse is not None and fr.collidepoint(self.mouse)
            ui.rect(s, (74, 60, 30) if hov else (50, 41, 22), fr, border_radius=8)
            ui.rect(s, hc, fr, width=1, border_radius=8)
            self._t("s", lab, (fr.centerx, fr.y + 2), hc, "c")
            self.live_hits.append((fr, bid))
            tx = fr.x - 8
            if ht == "Sem som" and self.fonts["s"].size("Sem som: toque uma música")[0] <= tx - (x0 + 16):          # what most people need to hear stays when it fits
                ht = "Sem som: toque uma música"
        self._t("s", self._fit_text("s", ht, tx - (x0 + 16)), (x0 + 16, 67), hc)
        # ---- the two big buttons
        fs_on = bool(keys.get("fullscreen"))
        au_on = bool(keys.get("auto"))
        if wide:
            bw = (rw - gap) // 2
            by = 96
            self._big_button(pygame.Rect(x0, by, bw, 50), "Sair da tela cheia" if fs_on else "Tela cheia", "key:f", primary=True, hint="tecla F na imagem")
            self._auto_pair(pygame.Rect(x0 + bw + gap, by, bw, 50), au_on)
            cy = by + 50 + 16
        else:
            by = ph - 50 - 8 - 50
            self._big_button(pygame.Rect(x0, by, rw, 50), "Sair da tela cheia" if fs_on else "Tela cheia", "key:f", primary=True, hint="tecla F na imagem")
            self._auto_pair(pygame.Rect(x0, by + 58, rw, 50), au_on)
            cy = ph + 16
        # ---- the three big controls
        mx, mw_ = (x0, rw) if wide else (0, Wc)
        changed = (cfg.get("macro_energy", 100), cfg.get("macro_speed", 100), cfg.get("macro_pal", 0)) != (100, 100, 0)
        self._t("xs", "CONTROLES  ·  valem para todas as cenas", (mx, cy), wg.TITLE)
        if changed:
            rr = pygame.Rect(mx + mw_ - 132, cy - 6, 132, 24)
            hov = self.mouse is not None and rr.collidepoint(self.mouse)
            wg.button(s, self.fonts["xs"], rr, "Voltar ao normal", "plain", hover=hov, radius=8)
            self.live_hits.append((rr, "macro:reset:0"))
        cy += 22
        lab_w = 124
        rh = 54
        ctl_x, ctl_w = mx + lab_w, mw_ - lab_w
        self._t("sb", "Intensidade", (mx, cy + 5), wg.TEXT)
        self._t("xs", "reage ao som", (mx, cy + 24), wg.DIM)
        self._steps(ctl_x, cy, ctl_w, 42, M.MACRO_ENERGY, M.macro_index(M.MACRO_ENERGY, cfg.get("macro_energy", 100)), "energy")
        cy += rh
        self._t("sb", "Velocidade", (mx, cy + 5), wg.TEXT)
        self._t("xs", "se move mais", (mx, cy + 24), wg.DIM)
        self._steps(ctl_x, cy, ctl_w, 42, M.MACRO_SPEED, M.macro_index(M.MACRO_SPEED, cfg.get("macro_speed", 100)), "speed")
        cy += rh
        self._t("sb", "Cores", (mx, cy + 5), wg.TEXT)
        self._t("xs", "cores de todas", (mx, cy + 24), wg.DIM)
        pals = (cfg.get("palettes") or [])[:7]
        n = 1 + len(pals)
        cg = 6
        cw = (ctl_w - cg * (n - 1)) // n
        cur = int(cfg.get("macro_pal", 0))
        for i in range(n):
            r = pygame.Rect(ctl_x + i * (cw + cg), cy, cw, 48)
            sel = i == cur
            hov = self.mouse is not None and r.collidepoint(self.mouse)
            ui.rect(s, wg.SURFACE2 if not hov else wg.HOVER_FILL, r, border_radius=10)
            if i == 0:
                self._t("s", "Da cena", (r.centerx, r.centery - 9), wg.TEXT, "c")
            else:
                cols = [tuple(c) for c in pals[i - 1]["colors"][:4]] or [(128, 128, 128)]
                sw = (r.w - 12) // len(cols)
                for k, col in enumerate(cols):
                    ui.rect(s, col, pygame.Rect(r.x + 6 + k * sw, r.y + 6, sw - 2 if k < len(cols) - 1 else sw, 22), border_radius=4)
                self._t("xs", self._fit_text("xs", pals[i - 1]["name"], r.w - 8), (r.centerx, r.y + 31), wg.TEXT if sel else wg.DIM, "c")
            ui.rect(s, wg.SEL if sel else (wg.HOVER_EDGE if hov else wg.CTRL), r, width=3 if sel else 1, border_radius=10)
            self.live_hits.append((r, f"macro:pal:{i}"))
        cy += 48
        return max(ph, cy)

    def _draw_detail(self, an, fps, lat, vsync, status, genre, now_t):
        """What the program hears and how it is doing: BPM, key, energy, the timeline, the image now, the whole track, the status and the analysis."""
        s = self.surf
        Wc = s.get_width()
        silent = an.silence > 0.6
        learning = an.bpm <= 0 or an.conf < 0.5 or an.active_t < 8.0

        # ---- header: BPM, what is playing, health
        bpm_txt = f"{an.bpm:5.1f}".strip() if an.bpm > 0 else "--"
        # beat feedback: a flash that decays through the beat (strongest on the one) and also follows the real kick; it drives the dots
        pulse = 0.0
        if an.bpm > 0 and not silent:
            pulse = max(math.exp(-an.phase * 5.5), 0.75 * an.kick)
            if an.beat_in_bar == 0:
                pulse = min(1.0, pulse * 1.15)
        manual = an.manual_bpm > 0                                       # the tempo was tapped by hand (it stays until AUTO)
        flash = max(0.0, 1.0 - (time.perf_counter() - self.tap_t) / 0.25)           # a tap lights the number for a quarter of a second
        blk = pygame.Rect(0, 0, 100, 60)                                 # the whole BPM block is the tap button
        bhov = self.mouse is not None and blk.collidepoint(self.mouse)
        self._t("xl", bpm_txt, (0, 0), wg.ACCENT if flash > 0 else (wg.ACCENT2 if (manual or bhov) else wg.TEXT))        # the number stays still; the dots below carry the beat
        self._t("xs", "BPM", (2, 42), wg.ACCENT2 if manual else wg.DIM)
        if an.bpm > 0 and not silent:                                   # one dot per beat of the bar, the current one lit
            for i in range(an.bpb):
                on = i == an.beat_in_bar
                c = tuple(int(46 + ((wg.ACCENT if i == 0 else wg.ACCENT2)[j] - 46) * (0.35 + 0.65 * pulse)) for j in range(3)) if on else wg.SURFACE2
                ui.circle(s, c, (62 + i * 16, 50), 5 if on else 4)
        pr = pygame.Rect(104, 4, 40, wg.MIN_H)                           # says what a click does: TAP (tap the beat), AUTO (give the tempo back to the program: lit while the tempo is by hand)
        phov = self.mouse is not None and pr.collidepoint(self.mouse)
        wg.button(s, self.fonts["xs"], pr, "AUTO" if manual else "TAP", "select" if manual else "plain", hover=phov or flash > 0, radius=pr.h // 2, pad=4)
        self.live_hits.append((pr, "bpm:auto" if manual else "bpm:tap"))
        self.live_hits.append((blk, "bpm:tap"))
        # the key (tom) next to the BPM: it matters for mixing, so it sits at the top
        key_known = an.key_name != "--" and not silent
        self._t("xl", an.key_name if key_known else "--", (150, 0), wg.TEXT if key_known else wg.DIM)
        self._t("xs", "TOM", (152, 42), wg.DIM)
        state = "Sem áudio" if silent else an.state.capitalize()
        tx = 262
        self._t("m", state + (f"  ·  {genre}" if (genre not in ("?", None, "") and not silent) else ""), (tx, 2), wg.TEXT)
        # the energy of the music, big: ten segments (green, then yellow, then red) and the level as a number
        lvl = max(0, min(10, int(an.level10)))
        for i in range(10):
            col = (wg.OK if i < 6 else wg.TEXT if i < 8 else wg.ACCENT) if i < lvl else wg.SURFACE2
            ui.rect(s, col, (tx + i * 17, 34, 13, 20), border_radius=4)
        self._t("m", f"{lvl}", (tx + 10 * 17 + 8, 30), wg.TEXT)
        self._t("xs", "ENERGIA", (tx + 10 * 17 + 8 + self.fonts["m"].size(f"{lvl}")[0] + 8, 36), wg.DIM)
        ok = status is None or status.get("shader_ok", True)
        if not ok:
            ht, hc = "Erro no efeito visual", wg.DANGER
        elif silent:
            ht, hc = "Sem áudio", wg.TEXT
        elif fps < 25:
            ht, hc = f"Travando: {fps:.0f} quadros/s", wg.TEXT
        elif learning:
            ht, hc = (f"Aprendendo o ritmo {an.conf * 100:.0f}%" if an.bpm > 0 else "Aprendendo o ritmo…"), wg.ACCENT2
        else:
            ht, hc = "Tudo certo", wg.OK
        wch = self.fonts["s"].size(ht)[0] + 38
        r = pygame.Rect(Wc - wch, 4, wch, 26)
        ui.rect(s, wg.SURFACE2, r, border_radius=13)
        ui.rect(s, wg.BORDER, r, width=1, border_radius=13)
        ui.circle(s, hc, (r.x + 14, r.centery), 5)
        self._t("s", ht, (r.x + 26, r.y + 3), hc)

        # ---- timeline card
        top = 70
        card = pygame.Rect(0, top, Wc, 238)
        self._card(card)
        zl = (1, 2, 4)[self.zoom_idx % 3]
        lx = 14
        for name, col in (("Graves", LOW), ("Médios", MID), ("Agudos", HIGH)):
            ui.rect(s, col, (lx, top + 16, 10, 10), border_radius=2)
            self._t("s", name, (lx + 15, top + 10), wg.DIM)
            lx += 15 + self.fonts["s"].size(name)[0] + 14
        bw = 108
        self._button(pygame.Rect(Wc - 14 - bw, top + 7, bw, 26), "Continuar" if self.frozen is not None else "Congelar", "freeze")
        self._button(pygame.Rect(Wc - 14 - bw - 8 - 90, top + 7, 90, 26), f"Zoom {self._zoom_label(zl)}", "zoom")
        wy, wh = top + 42, 124
        wx, ww = 12, Wc - 24
        ph = int(ww * 0.68)
        mid_y = wy + wh // 2
        half = wh // 2 - 6
        ui.rect(s, wg.BG, (wx, wy, ww, wh), border_radius=8)
        fut = pygame.Rect(wx + ph, wy, ww - ph, wh)
        ui.rect(s, (12, 13, 22), fut, border_top_right_radius=8, border_bottom_right_radius=8)
        n = an.deck_n if self.frozen is None else self.frozen
        pps = PX_PER_SEC / zl
        span = min(ph * zl, n)
        if span >= zl:
            cols = span // zl
            seg = an.deck[1:4, n - cols * zl:n].reshape(3, cols, zl).max(axis=2) ** 1.5
            dim = np.where(n - (cols - np.arange(cols)) * zl >= an.trk_i0, 1.0, 0.45)
            s.blit(self._wave_surface(seg[0], seg[1], seg[2], wh, half, dim), (wx + ph - cols, wy))
        ui.rect(s, wg.BORDER, fut, width=1, border_top_right_radius=8, border_bottom_right_radius=8)
        # beat grid in the past and the predicted grid in the future
        ref_t = an.now_t if self.frozen is None else self.frozen_t
        for (t, bib, barn) in an.beat_log:
            x = wx + ph - int((ref_t - t) * pps)
            if x < wx or x > wx + ph:
                continue
            Lh = 14 if bib == 0 else 8
            c = wg.ACCENT if bib == 0 else wg.DIM
            pygame.draw.line(s, c, (x, wy + 2), (x, wy + 2 + Lh))
            pygame.draw.line(s, c, (x, wy + wh - 2), (x, wy + wh - 2 - Lh))
        t_end, said, building = self.predict(an)
        if an.bpm > 0 and not silent and self.frozen is None:
            period = 60.0 / an.bpm
            d0 = (1.0 - an.phase) * period
            k = 0
            while True:
                x = wx + ph + int((d0 + k * period) * pps)
                if x > wx + ww - 2:
                    break
                bib = (an.beat_in_bar + 1 + k) % an.bpb
                c = (150, 30, 60) if bib == 0 else wg.BORDER
                pygame.draw.line(s, c, (x, wy + 2 + 18), (x, wy + 2 + (30 if bib == 0 else 26)))
                k += 1
        # sections of the music: every state (calmo, groove, energia alta, breakdown, drop, silêncio) lasts until the next one, the last until the
        # playhead. A tinted band over the wave and a bar at the top with the name; build-ups get their own thin bar under it
        cues = [(wx + ph - int((n - i) / zl), st) for (i, st) in an.state_log]
        for k, (x0, st) in enumerate(cues):
            x1 = cues[k + 1][0] if k + 1 < len(cues) else wx + ph
            sx, ex = max(x0, wx), min(x1, wx + ph)
            if ex <= sx:
                continue
            c, label, tint = STATE_STYLE.get(st, (wg.DIM, st.capitalize(), 16))
            band = pygame.Surface((ex - sx, wh - 2), pygame.SRCALPHA)
            band.fill((c[0], c[1], c[2], tint))
            s.blit(band, (sx, wy + 1))
            bw = max(3, ex - sx - 1)
            ui.rect(s, c, (sx, wy + 4, bw, 17), border_radius=8)
            for cand in (label, STATE_SHORT.get(st, "")):                                  # the whole name, or a short one when the bar is narrow
                img = self.fonts["xs"].render(cand, True, _ink(c))
                if cand and img.get_width() + 14 <= bw:
                    s.blit(img, (sx + 7, wy + 4 + 8 - img.get_height() // 2))
                    break
            if x0 >= wx and st in ("DROP", "BREAKDOWN"):
                pygame.draw.line(s, c, (x0, wy + 21), (x0, wy + wh - 18), 2)            # where a drop or a breakdown starts
        for (a0, a1) in an.build_spans:
            x0 = wx + ph - int((n - a0) / zl)
            x1 = wx + ph - int((n - (a1 if a1 is not None else n)) / zl)
            sx, ex = max(x0, wx), min(x1, wx + ph)
            if ex - sx < 2:
                continue
            ui.rect(s, YELLOW, (sx, wy + 24, max(3, ex - sx - 1), 13), border_radius=6)
            img = self.fonts["xs"].render("Build-up", True, _ink(YELLOW))
            if img.get_width() + 12 <= ex - sx:
                s.blit(img, (sx + 6, wy + 24 + 6 - img.get_height() // 2))
        # prediction: the rest of the phrase and what is expected after it, as ghost sections, plus the named boundary
        if t_end is not None and not silent and self.frozen is None:
            xe = wx + ph + int(t_end * pps)
            fx0, fx1 = wx + ph + 3, wx + ww - 3
            ex_ = min(xe, fx1)
            if ex_ - fx0 > 6:
                ui.rect(s, (46, 50, 72), (fx0, wy + 4, ex_ - fx0, 17), border_radius=8)
                img = self.fonts["xs"].render("Resto da frase", True, wg.TEXT)
                if img.get_width() + 14 <= ex_ - fx0:
                    s.blit(img, (fx0 + 7, wy + 4 + 8 - img.get_height() // 2))
            if xe < fx1 - 8:
                ui.rect(s, (120, 30, 50) if building else wg.CTRL_FILL, (xe + 2, wy + 4, fx1 - xe - 2, 17), border_radius=8)
                img = self.fonts["xs"].render("Drop?" if building else "Próxima frase", True, wg.TEXT)
                if img.get_width() + 14 <= fx1 - xe - 2:
                    s.blit(img, (xe + 9, wy + 4 + 8 - img.get_height() // 2))
                pygame.draw.line(s, wg.DANGER, (xe, wy + 21), (xe, wy + wh - 18), 2)
                img = self.fonts["xs"].render("Drop previsto" if building else "Fim da frase", True, _ink(wg.DANGER))
                lw = img.get_width() + 14
                lx = max(wx + ph + 6, min(xe - lw // 2, wx + ww - lw - 6))
                ui.rect(s, wg.DANGER, (lx, wy + wh - 44, lw, 17), border_radius=8)
                s.blit(img, (lx + 7, wy + wh - 44 + 8 - img.get_height() // 2))
            cw_ = self.fonts["s"].size(said)[0] + 20
            self._chip(max(wx + ph + 8, wx + ww - cw_ - 8), wy + 28, said, color=wg.TEXT if building else wg.TEXT, border=wg.TEXT if building else wg.BORDER)
        # captions of the two halves
        self._t("xs", "PREVISÃO", (wx + ww - 10, wy + wh - 15), wg.DIM, "r")
        ui.rect(s, (32, 35, 54), (wx, wy, ww, wh), width=1, border_radius=8)                  # the frame of the whole timeline
        # playhead: white line with a magenta marker
        beat = pulse if (an.bpm > 0 and not silent) else 0.0                       # the same flash as the dots: strongest on the beat, fading through it
        hc = tuple(int(90 + (255 - 90) * beat) for _ in range(3))
        if beat > 0.15:
            glow = pygame.Surface((13, wh + 12), pygame.SRCALPHA)
            glow.fill((255, 255, 255, int(70 * beat)))
            s.blit(glow, (wx + ph - 6, wy - 6))
        pygame.draw.line(s, hc, (wx + ph, wy - 4), (wx + ph, wy + wh + 4), 3 + (2 if beat > 0.55 else 0))
        tc_ = tuple(int(105 + (c - 105) * beat) if i else int(120 + (c - 120) * beat) for i, c in enumerate(wg.ACCENT))
        pygame.draw.polygon(s, tc_, [(wx + ph - 6, wy + wh + 11), (wx + ph + 6, wy + wh + 11), (wx + ph, wy + wh + 2)])
        if silent:
            self._t("m", "Toque uma música no computador", (wx + ph // 2, mid_y - 12), wg.TEXT, "c")
        # phrase progress (one segment per bar) and the reading
        sy = wy + wh + 16
        seg_w = (ww - (an.phrase_len - 1) * 3) / an.phrase_len
        for i in range(an.phrase_len):
            rr = pygame.Rect(int(wx + i * (seg_w + 3)), sy, int(seg_w), 6)
            ui.rect(s, wg.SURFACE2, rr, border_radius=3)
            if an.bpm > 0 and not silent:
                if i < an.phrase_pos:
                    ui.rect(s, wg.TEXT, rr, border_radius=3)               # the bars of the phrase that are done stay light
                elif i == an.phrase_pos:
                    ui.rect(s, wg.ACCENT, (rr.x, rr.y, max(3, int(rr.w * an.bar_phase)), rr.h), border_radius=3)
        if an.bpm > 0 and not silent:
            self._t("s", f"Compasso {max(0, an.bar_n) + 1}  ·  batida {an.beat_in_bar + 1}/{an.bpb}  ·  frase {an.phrase_pos + 1}/{an.phrase_len}", (wx, sy + 12), wg.DIM)

        if Wc >= 1180:                                                   # a wide window: two columns, what you act on at left, the shortcuts and the analysis at right
            gap = 12
            Lw = (Wc - gap) // 2
            y1 = top + 238 + 10
            le = self._col(0, Lw, lambda: self._left_col(an, fps, lat, vsync, status, y1, now_t))
            re_ = self._col(Lw + gap, Wc - gap - Lw, lambda: self._right_col(an, status, y1))
            return max(le, re_)
        iy = top + 238 + 10
        iy2 = self._blk_image(status, iy, Wc)
        end = self._left_col(an, fps, lat, vsync, status, iy, now_t, image_done=iy2)
        self._keys(status, end - 148)
        ey = end + 8
        eh = self._ear_card(an, ey, Wc)
        return ey + eh

    def _col(self, x0, w, fn):
        """Draw fn() on a column of the surface: it sees a surface w wide, and the hits and the pointer are moved to match."""
        full = self.surf
        n = len(self.live_hits)
        mouse = self.mouse
        self.surf = full.subsurface(pygame.Rect(x0, 0, w, full.get_height()))
        if mouse is not None:
            self.mouse = (mouse[0] - x0, mouse[1])
        try:
            end = fn()
        finally:
            self.surf, self.mouse = full, mouse
        self.live_hits[n:] = [(r.move(x0, 0), b) for r, b in self.live_hits[n:]]
        return end

    def _blk_image(self, status, iy, Wc):
        """What the picture is doing now."""
        s = self.surf
        info = (status or {}).get("image") or {}
        card2 = pygame.Rect(0, iy, Wc, 86)
        self._card(card2)
        self._t("xs", "IMAGEM AGORA", (14, iy + 9), wg.TITLE)
        x, y = 14, iy + 30
        chips = [f"{info.get('scene', '--')} · {info.get('style', '--')}", f"Câmera {info.get('camera', '--')}", f"Movimento {info.get('movement', '--')}"]
        for txt in chips:
            w_ = self.fonts["s"].size(txt)[0] + 20
            if x + w_ > Wc - 14:
                x, y = 14, y + 28
            x += self._chip(x, y, txt) + 6
        why = info.get("why")
        if why:
            txt = f"Última troca: {why}, há {info.get('since', 0):.0f} s"
            w_ = self.fonts["s"].size(txt)[0] + 20
            if x + w_ > Wc - 14:
                x, y = 14, y + 28
            self._chip(x, y, txt, color=wg.DIM)

        return iy + 86

    def _left_col(self, an, fps, lat, vsync, status, y0, now_t, image_done=None):
        """The image now, the scenes, the whole track and the status. Returns where it ends."""
        s = self.surf
        Wc = s.get_width()
        iy = y0
        if image_done is None:
            image_done = self._blk_image(status, iy, Wc)
        oy = image_done + 12
        oh = 22
        T = an.track_time
        view = max(T, 120.0)
        ppsv = (Wc - 4) / view
        colsn = int(T * ppsv)
        ui.rect(s, wg.BG, (0, oy, Wc - 4, oh), border_radius=6)
        if colsn > 2 and an.deck_n - an.trk_i0 > 4:
            key = (colsn, an.trk_i0, Wc)
            if now_t - self.ov_cache[0] > 0.5 or getattr(self, "ov_surf_c", None) is None or key != getattr(self, "ov_key_c", None):
                self.ov_cache = (now_t, None)
                seg = an.deck[1:4, an.trk_i0:an.deck_n]
                idx = (np.arange(seg.shape[1]) * colsn // seg.shape[1])
                starts = np.searchsorted(idx, np.arange(colsn))
                red = np.maximum.reduceat(seg, starts, axis=1)
                rr_ = red[:, :colsn] ** 1.5
                surf = self._wave_surface(rr_[0], rr_[1], rr_[2], oh, oh // 2 - 2, np.ones(rr_.shape[1]))
                self.ov_surf_c, self.ov_key_c = surf, key
            s.blit(self.ov_surf_c, (0, oy))
        for (i, kind) in an.marks[:24]:
            xm = int((i - an.trk_i0) * an.hop_dt * ppsv)
            if 0 <= xm <= Wc - 4:
                pygame.draw.line(s, KIND_COLOR.get(kind, wg.DIM), (xm, oy), (xm, oy + oh), 1)
        xe2 = colsn
        pygame.draw.line(s, wg.TEXT, (xe2, oy - 2), (xe2, oy + oh + 2), 2)
        pygame.draw.polygon(s, wg.ACCENT, [(xe2 - 5, oy + oh + 9), (xe2 + 5, oy + oh + 9), (xe2, oy + oh + 2)])
        step = 30 if view <= 360 else 60
        for sec in range(0, int(view) + 1, step):
            xt = int(sec * ppsv)
            if sec % 60 == 0:
                self._t("xs", f"{sec // 60}:00", (min(max(xt, 10), Wc - 16), oy + oh + 6), wg.DIM, "c")

        dy = oy + oh + 30
        self._t("xs", "STATUS", (0, dy), wg.TITLE)
        self._status(fps, lat, vsync, status, dy + 22)
        return dy + 148

    def _right_col(self, an, status, y0):
        """The shortcuts of the picture and the analysis, in the right column of a wide window."""
        Wc = self.surf.get_width()
        self._keys(status, y0, x0=0)
        ey = y0 + 148 + 8
        return ey + self._ear_card(an, ey, Wc)

    @staticmethod
    def _zoom_label(z):
        return {1: "4 s", 2: "8 s", 4: "16 s"}[z]

    def _status(self, fps, lat, vsync, status, y):
        """How the program itself is doing (the music is shown above). Always visible."""
        s = self.surf
        dot = wg.SEL if fps >= 55 else (255, 220, 100) if fps >= 40 else (255, 110, 110)
        ui.circle(s, dot, (7, y + 10), 5)
        self._t("m", f"{fps:4.0f} FPS", (20, y - 2), wg.TEXT)
        self._t("s", f"{'sem cortes na imagem' if vsync else 'VSync desligado'}  ·  atraso ~{lat:3.0f} ms", (20, y + 26), wg.DIM)
        y += 52
        if status:
            self._t("s", self._fit_text("s", f"GPU  {status['gpu']}  ·  {status['backend']}", 290), (0, y), wg.TEXT)
            if status["shader_ok"]:
                self._t("s", "Efeitos visuais funcionando", (0, y + 20), wg.OK)
            else:
                self._t("s", self._fit_text("s", "Erro no efeito visual: " + status["shader_msg"], 290), (0, y + 20), (255, 130, 150))
            y += 42
            tmg = status.get("timing")
            if tmg:
                self._t("xs", self._fit_text("xs", "  ·  ".join(f"{k} {v:.1f}" for k, v in tmg.items()) + " ms", 300), (0, y - 2), wg.DIM)
                y += 18
        return y

    # ------------------------------------------------------------- "O que estou ouvindo": the plug-in style panels
    SECT_COL = ((70, 74, 98), (60, 52, 137), (15, 110, 86), (153, 60, 29), (24, 95, 165), (153, 53, 86), (133, 79, 11), (95, 94, 90))

    def _panel(self, r, title, right=""):
        ui.rect(self.surf, (19, 22, 33), r, border_radius=10)
        ui.rect(self.surf, wg.BORDER, r, width=1, border_radius=10)
        self._t("xs", title, (r.x + 10, r.y + 7), wg.ACCENT2)
        if right:
            self._t("xs", right, (r.right - 10, r.y + 7), wg.DIM, "r")

    def _spark(self, r, vals, color, fill=False):
        """A small history line (the last 30 s) inside rect r, values 0..1."""
        if len(vals) < 2:
            return
        n = len(vals)
        pts = [(r.x + int(i * (r.w - 1) / 59.0) + (r.w - 1 - int((n - 1) * (r.w - 1) / 59.0)), r.bottom - 2 - int(v * (r.h - 4))) for i, v in enumerate(vals)]
        if fill:
            pygame.draw.polygon(self.surf, tuple(c // 4 for c in color), pts + [(pts[-1][0], r.bottom - 1), (pts[0][0], r.bottom - 1)])
        pygame.draw.lines(self.surf, color, False, pts, 2)

    def _alpha_rect(self, r, color, alpha):
        sh = pygame.Surface((max(1, r.w), max(1, r.h)), pygame.SRCALPHA)
        sh.fill((color[0], color[1], color[2], alpha))
        self.surf.blit(sh, r.topleft)

    def _ear_card(self, an, y, Wc):
        """The card "O que estou ouvindo", drawn like the displays of audio plug-ins: a sentence that says what the music is doing, a 16-step grid of the
        drums, the spectrum with the brightness / melody / vocal band marked on it, the chroma with the chord, a loudness meter, a goniometer, the tension
        and the sections. While the timeline is frozen the card is frozen with it."""
        import time as _time
        ear = an.ear
        ch = 58 + 132 + 8 + 142 + 8 + 128 + 10 if self.ear_open else 62
        self.live_hits.append((pygame.Rect(0, y, Wc, 30), "ear:toggle"))
        cache = getattr(self, "_ear_cache", None)
        if self.frozen is not None and cache is not None and cache.get_size() == (Wc, ch):
            self.surf.blit(cache, (0, y))
            return ch
        real = self.surf
        cs = pygame.Surface((Wc, ch), pygame.SRCALPHA)
        self.surf = cs
        try:
            self._ear_draw(an, ear, Wc, ch, _time.perf_counter())
        finally:
            self.surf = real
        real.blit(cs, (0, y))
        self._ear_cache = cs
        return ch

    def _ear_draw(self, an, ear, Wc, ch, now):
        s = self.surf
        silent = an.silence > 0.6
        self._card(pygame.Rect(0, 0, Wc, ch))
        self._t("xs", "O QUE ESTOU OUVINDO", (14, 9), wg.TITLE)
        self._t("xs", "estimativas  ·  o card congela com a linha do tempo" if self.frozen is not None else ("estimativas  ·  aceso = confiável" if self.ear_open else "toque para abrir"), (Wc - 38, 9), wg.DIM, "r")
        kx, ky = Wc - 22, 15                                                                 # the caret: open / closed
        pygame.draw.polygon(s, wg.TITLE, [(kx - 5, ky - 3), (kx + 5, ky - 3), (kx, ky + 3)] if self.ear_open else [(kx - 3, ky - 5), (kx - 3, ky + 5), (kx + 3, ky)])
        # the sentence
        x = 14
        for text, hl in ear.sentence(an):
            img = self.fonts["s"].render(text, True, wg.ACCENT2 if hl else wg.TEXT)
            if x + img.get_width() > Wc - 14:
                break
            s.blit(img, (x, 30))
            x += img.get_width()
        if not self.ear_open:
            return
        px, pw_all, gap = 14, Wc - 28, 8
        # ---- row 1: the drum grid and the tempo
        y1 = 58
        gw = pw_all - 150 - gap
        r = pygame.Rect(px, y1, gw, 132)
        self._panel(r, "RITMO", f"compasso {max(0, an.bar_n) + 1}  ·  grade de 16 passos" if an.bpm > 0 and not silent else "ouvindo o ritmo…")
        lab_w = 58
        cw = (gw - 20 - lab_w) / 16.0
        gx0, gy0 = r.x + 10 + lab_w, r.y + 31
        for i, bn in enumerate(range(an.bpb)):
            self._t("xs", str(bn + 1), (int(gx0 + i * (16 / an.bpb) * cw + 2), r.y + 18), wg.DIM)
        names = ("Kick", "Caixa", "Chimbal", "Graves")
        if ear.grid_step >= 0 and not silent:
            self._alpha_rect(pygame.Rect(int(gx0 + ear.grid_step * cw), gy0 - 4, max(2, int(cw)), 4 * 24), wg.ACCENT, 40)
        for row in range(4):
            yy = gy0 + row * 24
            self._t("xs", names[row], (r.x + 10, yy + 2), wg.TEXT if ear.grid[row].max() > 0 else wg.DIM)
            for st in range(16):
                cr = pygame.Rect(int(gx0 + st * cw) + 1, yy, max(3, int(cw) - 3), 18)
                cur, prev = float(ear.grid[row, st]), float(ear.grid_prev[row, st])
                col = (28, 31, 46) if st % 4 else (34, 38, 56)
                if prev > 0 and cur <= 0:
                    col = (30, 42, 78)                                                    # the ghost of the bar before
                if cur > 0:
                    k = 0.45 + 0.55 * cur
                    base = wg.SEL if row != 0 else (110, 160, 255)
                    col = tuple(int(c * k) for c in base)
                    if st == ear.grid_step:
                        col = wg.ACCENT
                ui.rect(s, col, cr, border_radius=4)
        # tempo
        rt = pygame.Rect(px + gw + gap, y1, 150, 132)
        self._panel(rt, "ANDAMENTO")
        cx, cy = rt.centerx, rt.y + 86
        pygame.draw.arc(s, wg.SURFACE2, (cx - 52, cy - 52, 104, 104), math.radians(0), math.radians(180), 7)
        stable = max(0.0, 1.0 - ear.tempo_spread / 8.0) if an.bpm > 0 else 0.0
        if stable > 0.02 and not silent:
            pygame.draw.arc(s, wg.ACCENT2 if ear.tempo_spread < 1.5 else wg.TEXT, (cx - 52, cy - 52, 104, 104), math.radians(180 - 180 * stable), math.radians(180), 7)
        self._t("l", f"{an.bpm:.0f}" if an.bpm > 0 and not silent else "--", (cx, cy - 34), wg.TEXT, "c")
        self._t("xs", ("estável" if ear.tempo_spread < 1.5 else "variando") + (f" ±{ear.tempo_spread / 2:.1f}" if an.bpm > 0 else ""), (cx, cy - 4), wg.DIM, "c")
        lab = "baixa" if ear.density < 3.0 else ("média" if ear.density < 7.0 else "alta")
        self._t("xs", f"densidade {lab} · {ear.density:.1f}/s", (cx, rt.bottom - 18), wg.DIM, "c")
        # ---- row 2: the spectrum and the chroma
        y2 = y1 + 132 + gap
        now_low = ear.chord_conf < 0.2 and ear.note_conf < 0.25
        if not now_low:
            self._harm_on_t = now
        harm_off = now_low and now - getattr(self, "_harm_on_t", now) > 6.0               # no harmony for a while: the spectrum takes the room
        hw = 0 if harm_off else 196
        sw = pw_all - (hw + gap if hw else 0)
        r = pygame.Rect(px, y2, sw, 142)
        self._panel(r, "ESPECTRO", "20 Hz — 16 kHz")
        ax, ay, aw, ah = r.x + 10, r.y + 24, r.w - 20, 92
        nb = len(an.bands)
        fmax = min(16000.0, an.rate / 2 - 1)
        fx = lambda f: ax + int(aw * max(0.0, min(1.0, math.log(max(f, 30.0) / 30.0) / math.log(fmax / 30.0))))
        self._alpha_rect(pygame.Rect(fx(30), ay, fx(200) - fx(30), ah), wg.ACCENT, 28)
        self._alpha_rect(pygame.Rect(fx(1000), ay, fx(3400) - fx(1000), ah), wg.ACCENT2, 30 if ear.vocal > 0.4 else 14)
        self._t("xs", "graves", (fx(30) + 4, ay + 2), wg.DANGER)
        self._t("xs", "faixa vocal" + (" · voz" if ear.vocal > 0.4 else ""), (fx(1000) + 4, ay + 2), wg.SEL if ear.vocal > 0.4 else wg.DIM)
        if not silent:
            top = [(ax + int(i * aw / (nb - 1)), ay + ah - int(float(an.bands[i]) * (ah - 14))) for i in range(nb)]
            pygame.draw.polygon(s, (27, 47, 102), top + [(ax + aw, ay + ah), (ax, ay + ah)])
            pygame.draw.lines(s, wg.ACCENT2, False, top, 2)
            pk = [(ax + int(i * aw / (nb - 1)), ay + ah - int(float(ear.peak[i]) * (ah - 14))) for i in range(nb)]
            pygame.draw.lines(s, (90, 112, 170), False, pk, 1)
            if ear.cen > 0:
                cxx = fx(ear.cen)
                pygame.draw.line(s, wg.ACCENT, (cxx, ay + 14), (cxx, ay + ah), 2)
                self._t("xs", f"brilho {ear.cen / 1000:.1f}k", (min(cxx + 4, ax + aw - 62), ay + 14), wg.DANGER)
            if ear.note != "--" and ear.note_hz > 0:
                nx = fx(ear.note_hz)
                i = max(0, min(nb - 1, int((nx - ax) * (nb - 1) / aw)))
                ny = ay + ah - int(float(an.bands[i]) * (ah - 14))
                pygame.draw.line(s, (255, 255, 255), (nx, ny), (nx, ay + ah - 2), 1)
                ui.circle(s, (255, 255, 255), (nx, ny), 4)
                self._t("xs", ear.note, (nx, ay + ah - 15), (255, 255, 255), "c")
            if ear.riser > 0.35:
                self._t("xs", "▲ riser", (ax + aw - 4, ay + 2), wg.TEXT, "r")
        for f, lab in ((50, "50"), (100, "100"), (500, "500"), (1000, "1k"), (5000, "5k"), (10000, "10k")):
            self._t("xs", lab, (fx(f), r.bottom - 18), wg.DIM, "c")
        if not harm_off:
            rh = pygame.Rect(px + sw + gap, y2, hw, 142)
            self._panel(rh, "HARMONIA", f"tom {an.key_name}" if an.key_name != "--" and not silent else "")
            chord_notes = set()
            if ear.chord != "--" and not silent:
                minor = ear.chord.endswith("m")
                root = NOTE_IDX[ear.chord.rstrip("m")]
                chord_notes = {root, (root + (3 if minor else 4)) % 12, (root + 7) % 12}
            key_root = NOTE_IDX.get(an.key_name.rstrip("m"), -1) if an.key_name != "--" else -1
            bw = (hw - 20) / 12.0
            cmax = max(float(ear.chroma.max()), 1e-6)
            for i in range(12):
                hgt = int(54 * float(ear.chroma[i]) / cmax) if not silent else 0
                br = pygame.Rect(rh.x + 10 + int(i * bw), rh.y + 78 - hgt, max(4, int(bw) - 2), max(2, hgt))
                ui.rect(s, wg.ACCENT2 if i in chord_notes else wg.SURFACE2, br, border_radius=2)
                nm = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")[i]
                if len(nm) == 1:                                                            # only the natural notes are named; the sharps are the narrow bars between them
                    self._t("xs", nm, (rh.x + 10 + int(i * bw) + int(bw) // 2 - 3, rh.y + 82), wg.TEXT if i == key_root else wg.DIM)
                elif i == key_root:
                    self._t("xs", "#", (rh.x + 10 + int(i * bw) + int(bw) // 2 - 3, rh.y + 82), wg.TEXT)
                if i == key_root:
                    pygame.draw.line(s, wg.ACCENT, (br.x, rh.y + 96), (br.right, rh.y + 96), 2)
            self._t("l", ear.chord if ear.chord != "--" and not silent else "—", (rh.x + 10, rh.y + 98), wg.TEXT if ear.chord != "--" else wg.DIM)
            conf = pygame.Rect(rh.x + 90, rh.y + 106, hw - 100, 4)
            ui.rect(s, wg.SURFACE2, conf, border_radius=2)
            if ear.chord != "--" and not silent:
                ui.rect(s, wg.ACCENT, (conf.x, conf.y, max(3, int(conf.w * ear.chord_conf)), 4), border_radius=2)
            self._t("xs", self._fit_text("xs", " · ".join(ear.chord_seq[-4:]) or "ouvindo…", hw - 100), (rh.x + 90, rh.y + 114), wg.DIM)
        # ---- row 3: loudness, stereo, tension, sections
        y3 = y2 + 142 + gap
        h3 = 128
        rv = pygame.Rect(px, y3, 84, h3)
        self._panel(rv, "VOLUME")
        for k, (val, col) in enumerate(((an.lf, wg.ACCENT2), (ear.lf_long, wg.SEL))):
            bx = rv.x + 12 + k * 28
            ui.rect(s, wg.SURFACE2, (bx, rv.y + 24, 18, 78), border_radius=4)
            if not silent:
                hh = int(78 * max(0.0, min(1.0, (val + 50.0) / 50.0)))
                ui.rect(s, col, (bx, rv.y + 24 + 78 - hh, 18, max(2, hh)), border_radius=4)
        if not silent:
            py_ = rv.y + 24 + 78 - int(78 * max(0.0, min(1.0, (ear.lf_peak + 50.0) / 50.0)))
            pygame.draw.line(s, wg.ACCENT, (rv.x + 10, py_), (rv.x + 70, py_), 2)
        self._t("xs", f"{an.lf:.0f} dB" if not silent and an.lf > -80 else "—", (rv.centerx, rv.bottom - 20), wg.DIM, "c")
        rs = pygame.Rect(rv.right + gap, y3, 128, h3)
        self._panel(rs, "ESTÉREO")
        gcx, gcy, gr = rs.centerx, rs.y + 62, 34
        ui.circle(s, wg.SURFACE2, (gcx, gcy), gr, 1)
        pygame.draw.line(s, wg.SURFACE2, (gcx, gcy - gr), (gcx, gcy + gr), 1)
        pygame.draw.line(s, wg.SURFACE2, (gcx - gr, gcy), (gcx + gr, gcy), 1)
        if ear.lr is not None and not silent:
            lft, rgt = ear.lr
            n = min(len(lft), 160)
            lo, ro = lft[-n:], rgt[-n:]
            mid, sid = (lo + ro) * 0.7071, (lo - ro) * 0.7071
            gain = gr / max(0.06, float(np.abs(mid).max()), float(np.abs(sid).max()))
            for i in range(0, n, 2):
                pxx = int(gcx + max(-gr, min(gr, sid[i] * gain)))
                pyy = int(gcy - max(-gr, min(gr, mid[i] * gain)))
                s.set_at((pxx, pyy), wg.SEL)
                s.set_at((pxx + 1, pyy), wg.SEL)
        elif not silent:
            self._t("xs", "mono", (gcx, gcy - 6), wg.DIM, "c")
        cb = pygame.Rect(rs.x + 12, rs.bottom - 28, rs.w - 24, 4)
        ui.rect(s, wg.SURFACE2, cb, border_radius=2)
        pygame.draw.line(s, (60, 66, 92), (cb.centerx, cb.y - 2), (cb.centerx, cb.bottom + 2), 1)
        if not silent:
            mx = cb.centerx + int((cb.w // 2) * max(-1.0, min(1.0, ear.corr)))
            ui.circle(s, wg.ACCENT if ear.corr < 0 else wg.ACCENT2, (mx, cb.centery), 4)
        self._t("xs", f"{ear.width * 100:.0f}% largo" if ear.width > 0 and not silent else "mono", (rs.centerx, rs.bottom - 18), wg.DIM, "c")
        rest = pw_all - 84 - 128 - 2 * gap
        rtn = pygame.Rect(rs.right + gap, y3, rest // 2 - 4, h3)
        self._panel(rtn, "TENSÃO")
        tb = pygame.Rect(rtn.x + 10, rtn.y + 26, rtn.w - 20, 8)
        ui.rect(s, wg.SURFACE2, tb, border_radius=4)
        if not silent:
            ui.rect(s, wg.ACCENT if an.tension > 0.5 else wg.ACCENT2, (tb.x, tb.y, max(4, int(tb.w * max(0.0, min(1.0, an.tension)))), 8), border_radius=4)
        self._spark(pygame.Rect(rtn.x + 10, rtn.y + 42, rtn.w - 20, 30), list(ear.hist["tens"]), wg.ACCENT, True)
        lamps = (("VOZ", ear.vocal > 0.4, False), ("RISER", ear.riser > 0.35, ear.riser > 0.7), ("REPETE", ear.repeat_at is not None, False))
        lx = rtn.x + 10
        for name, on, hot in lamps:
            w_ = self.fonts["xs"].size(name)[0] + 14
            if lx + w_ > rtn.right - 6:
                break
            ui.rect(s, wg.ACCENT if hot else ((0x2E, 0x33, 0x24) if on and not silent else (26, 29, 43)), (lx, rtn.bottom - 30, w_, 20), border_radius=10)
            ui.rect(s, wg.ACCENT if hot else (wg.ACCENT2 if on and not silent else wg.BORDER), (lx, rtn.bottom - 30, w_, 20), width=1, border_radius=10)
            if name == "RISER" and not silent and ear.riser > 0.02:                      # the level of the reading, so a weak riser shows before the lamp lights
                ui.rect(s, (60, 66, 110), (lx + 3, rtn.bottom - 13, max(2, int((w_ - 6) * min(1.0, ear.riser / 0.35))), 2), border_radius=1)
            self._t("xs", name, (lx + 7, rtn.bottom - 27), wg.TEXT if on and not silent else wg.DIM)
            lx += w_ + 5
        rst = pygame.Rect(rtn.right + gap, y3, pw_all - (rtn.right + gap - px), h3)
        self._panel(rst, "ESTRUTURA", f"agora {ear.sect_now}" if ear.sect_now else "")
        sb = pygame.Rect(rst.x + 10, rst.y + 26, rst.w - 20, 28)
        ui.rect(s, wg.SURFACE2, sb, border_radius=5)
        span = 120.0
        t_now = an.track_time
        for (t0, t1, lab) in ear.sect:
            x0 = sb.x + int(sb.w * max(0.0, (t0 - (t_now - span)) / span))
            x1 = sb.x + int(sb.w * min(1.0, (t1 - (t_now - span)) / span))
            if x1 - x0 < 3:
                continue
            col = self.SECT_COL[(ord(lab) - 65) % len(self.SECT_COL)]
            ui.rect(s, col, (x0, sb.y + 2, x1 - x0 - 1, sb.h - 4), border_radius=4)
            if x1 - x0 > 16:
                self._t("xs", lab, (x0 + 6, sb.y + 6), (255, 255, 255))
        pygame.draw.line(s, (255, 255, 255), (sb.right - 1, sb.y - 2), (sb.right - 1, sb.bottom + 2), 2)
        self._t("xs", "−2 min", (sb.x, sb.bottom + 4), wg.DIM)
        self._t("xs", "agora", (sb.right, sb.bottom + 4), wg.DIM, "r")
        txt = f"soa igual a {mmss_(ear.repeat_at)}" if ear.repeat_at is not None else ("parte nova" if ear.sect_now else "ouvindo…")
        self._t("s", txt, (rst.x + 10, rst.bottom - 30), wg.TEXT if ear.repeat_at is not None else wg.DIM)
        tip = pygame.Rect(rst.x + 10, rst.bottom - 12, rst.w - 20, 3)
        ui.rect(s, wg.SURFACE2, tip, border_radius=1)
        if ear.repeat_at is not None:
            ui.rect(s, wg.ACCENT, (tip.x, tip.y, max(3, int(tip.w * max(0.0, min(1.0, ear.repeat_sim)))), 3), border_radius=1)

    def _fit_text(self, font, text, w):
        return wg.fit(self.fonts[font], text, w)

    # the keys of the picture window, as buttons: (key sent to the picture window, cap, name, state in status["keys"])
    KEYS = (("f", "F", "Tela cheia", "fullscreen"), ("v", "V", "VSync", "vsync"), ("s", "S", "Strobe", "strobe"), ("d", "D", "Drop teste", None),
            ("a", "A", "Auto", "auto"), ("p", "P", "Modo palco", "stage"), ("Escape", "Esc", "Sai da tela", None), (None, "1–9", "Cenas", None))

    def _keys(self, status, y, x0=318):
        """Every shortcut of the picture window as a button next to the status: click it, or press the key on the picture. Lit = on."""
        s = self.surf
        st = (status or {}).get("keys") or {}
        Wc = s.get_width()
        gap, bh = 8, 46
        bw = (Wc - x0 - 3 * gap) // 4
        self._t("xs", "ATALHOS DA IMAGEM", (x0, y), wg.TITLE)
        for i, (key, cap, name, flag) in enumerate(self.KEYS):
            r = pygame.Rect(x0 + (i % 4) * (bw + gap), y + 22 + (i // 4) * (bh + gap), bw, bh)
            lit = bool(st.get(flag)) if flag else False
            hov = key is not None and self.mouse is not None and r.collidepoint(self.mouse)
            ui.rect(s, (0x2E, 0x33, 0x24) if lit else (wg.HOVER_FILL if hov else wg.SURFACE2), r, border_radius=10)
            ui.rect(s, wg.SEL if lit else (wg.HOVER_EDGE if hov else wg.BORDER), r, width=1, border_radius=10)
            col = wg.SEL if lit else (wg.TEXT if (hov or key) else wg.DIM)
            img = self.fonts["sb"].render(cap, True, col)
            s.blit(img, (r.centerx - img.get_width() // 2, r.y + 6))
            img = self.fonts["xs"].render(name, True, wg.TEXT if lit else wg.DIM)
            s.blit(img, (r.centerx - img.get_width() // 2, r.y + 27))
            if key is not None:
                self.live_hits.append((r, "key:" + key))

    def live_click(self, pos):
        """A click on the Ao vivo content (pos is in the content's own coordinates). Returns True when it hit something."""
        for rect, bid in self.live_hits:
            if rect.collidepoint(pos):
                if bid == "freeze":
                    self.frozen, self.frozen_t = (self._n_now, self._t_now) if self.frozen is None else (None, 0.0)
                elif bid == "zoom":
                    self.zoom_idx = (self.zoom_idx + 1) % 3
                return bid
        return None

    def update(self, now, an, genre="?", force=False):
        if not (force or now - self.last >= self.interval):
            return
        self.last = now
        self.draw(an, genre, now)
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
        self.win = self.ren = self.tex = None
        self.id = None
