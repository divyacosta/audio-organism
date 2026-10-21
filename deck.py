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

os.environ.setdefault("SDL_RENDER_DRIVER", "software")

import numpy as np
import pygame

import ui

W, H = 1180, 600
LOW = (80, 220, 255)                    # graves: cyan (outer layer of the wave)
MID = (150, 120, 255)                   # médios: violet
HIGH = (255, 70, 200)                   # agudos: magenta (the core)
BLUE, ORANGE, WHITE_W = LOW, MID, HIGH  # names used by the wide Deck window
RED = (255, 120, 150)
YELLOW = (255, 200, 90)
CUE_COLORS = [(232, 48, 48), (60, 160, 255), (40, 200, 60), (140, 70, 240), (40, 200, 60), (240, 110, 30), (50, 80, 235), (240, 210, 30)]
KIND_COLOR = {"DROP": RED, "BREAK": (160, 168, 208), "BUILD": YELLOW}
KIND_LABEL = {"DROP": "Drop", "BREAK": "Breakdown", "BUILD": "Build-up"}
# the sections of the timeline: state -> (colour, name, tint of the band over the wave)
STATE_SHORT = {"HIGH ENERGY": "Alta", "BREAKDOWN": "Break", "SILENCE": "Mudo", "GROOVE": "Gr."}
STATE_STYLE = {"CALM": ((96, 170, 205), "Calmo", 14), "GROOVE": (MID, "Groove", 14), "HIGH ENERGY": (HIGH, "Energia alta", 20),
               "BREAKDOWN": (KIND_COLOR["BREAK"], "Breakdown", 26), "DROP": (RED, "Drop", 30), "SILENCE": ((70, 72, 100), "Silêncio", 40)}
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
        for name, size, bold in (("xs", 12, False), ("s", 14, False), ("sb", 14, True), ("m", 18, True), ("l", 26, True), ("xl", 34, True), ("big", 60, True)):
            self.fonts[name] = pygame.font.SysFont("segoeui", size, bold=bold)
        self.win = self.ren = self.tex = None
        self.id = None
        self.last = -1.0
        self.interval = 1.0 / 30.0
        self.ov_cache = (0.0, None)
        self.mouse = None                                        # pointer position over the live content, for hover
        self.live_hits = []
        self.zoom_idx = 1                                        # 0: 4 s, 1: 8 s, 2: 16 s of history
        self.frozen, self.frozen_t = None, 0.0                   # a frozen waveform stops scrolling (hop index it stopped at)
        self.blend = 0                                           # 0 = blended layers (screen), 1 = solid layers
        self.live_end = 0
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
        ui.rect(s, (118, 142, 190), (0, 0, 96, HEAD_H))
        self._t("l", "AO", (48, 8), (14, 22, 40), "c")
        self._t("xs", "AO VIVO", (48, 42), (14, 22, 40), "c")
        title = "SEM ÁUDIO" if silent else an.state + (f"  ·  {genre}" if genre not in ("?", None, "") else "")
        self._t("l", title, (112, 4), (245, 245, 250))
        bpm = f"{an.bpm:5.1f}" if an.bpm > 0 else " --"
        self._t("l", f"{self._fmt(an.track_time)}    {bpm}    {an.key_name}", (136, 34), (245, 245, 250))
        chips = (("ENERGIA", f"{an.level10}/10"), ("BATIDA", f"{an.beat_in_bar + 1} / {an.bpb}" if an.bpm > 0 else "--"),
                 ("FRASE", f"{an.phrase_pos + 1} / {an.phrase_len}" if an.bpm > 0 else "--"))
        for i, (a, b) in enumerate(chips):
            r = pygame.Rect(W - 3 * 128 + i * 128 + 6, 6, 118, HEAD_H - 12)
            ui.rect(s, (46, 46, 50), r, border_radius=4)
            self._t("sb", a, (r.centerx, r.y + 6), (200, 200, 208), "c")
            self._t("m", b, (r.centerx, r.y + 26), (245, 245, 250), "c")

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
        pygame.draw.polygon(s, (255, 130, 30), [(PLAYHEAD_X - 9, ZOOM_Y + ZOOM_H + 16), (PLAYHEAD_X + 9, ZOOM_Y + ZOOM_H + 16), (PLAYHEAD_X, ZOOM_Y + ZOOM_H + 4)])
        if silent:
            self._t("l", "Toque uma música no computador", (W // 2, mid_y - 16), (255, 200, 90), "c")

        # ---- info row
        iy = 430
        r = pygame.Rect(24, iy, 190, 78)
        ui.rect(s, (255, 120, 30), r, width=2)
        self._t("s", "BPM", (r.x + 8, r.y + 4), (255, 150, 60))
        ui.rect(s, (255, 120, 30), (r.right - 62, r.y, 62, 20))
        self._t("xs", "AUTO", (r.right - 31, r.y + 2), (10, 10, 10), "c")
        self._t("big", f"{an.bpm:5.1f}" if an.bpm > 0 else "--", (r.centerx, r.y + 14), (255, 130, 40), "c")
        self._t("big", self._fmt(an.track_time, True), (300, iy - 4), (245, 245, 250))
        self._t("s", f"CONFIANÇA {an.conf * 100:3.0f}%", (305, iy + 66), (170, 170, 180))
        self._t("s", f"DROPS {sum(1 for _, k in an.marks if k == 'DROP')}", (470, iy + 66), (170, 170, 180))
        self._t("s", f"VOLUME {an.lf:4.0f} dB", (580, iy + 66), (170, 170, 180))
        kx = 820
        self._t("s", "ENERGIA", (kx, iy + 2), (170, 170, 180))
        for i in range(10):
            on = i < an.level10
            ui.rect(s, (60, 200, 90) if on and i < 6 else ((240, 190, 40) if on and i < 8 else ((235, 60, 60) if on else (46, 46, 50))), (kx + i * 16, iy + 24, 12, 22))
        self._t("s", "KEY", (W - 90, iy + 2), (170, 170, 180), "c")
        self._t("xl", an.key_name, (W - 90, iy + 22), (245, 245, 250), "c")

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
        pygame.draw.polygon(s, (255, 130, 30), [(xe - 7, oy + oh + 12), (xe + 7, oy + oh + 12), (xe, oy + oh + 2)])
        step = 30 if view <= 360 else 60
        for sec in range(0, int(view) + 1, step):
            x = ox + int(sec * pps)
            pygame.draw.line(s, (120, 120, 128), (x, oy + oh + 2), (x, oy + oh + (9 if sec % 60 == 0 else 5)))
            if sec % 60 == 0:
                self._t("xs", f"{sec // 60}:00", (x, oy + oh + 6), (190, 190, 198), "c")


    # ------------------------------------------------------------ the "Ao vivo" tab (timeline layout)
    def _chip(self, x, y, text, color=None, border=None, font="s", pad=10, h=22):
        """A rounded pill; returns its width."""
        import menu as M
        img = self.fonts[font].render(text, True, color or M.TEXT)
        w = img.get_width() + 2 * pad
        r = pygame.Rect(x, y, w, h)
        ui.rect(self.surf, M.SURFACE2, r, border_radius=h // 2)
        ui.rect(self.surf, border or M.BORDER, r, width=1, border_radius=h // 2)
        self.surf.blit(img, (x + pad, y + (h - img.get_height()) // 2))
        return w

    def _button(self, rect, label, bid, color=None):
        import menu as M
        hov = self.mouse is not None and rect.collidepoint(self.mouse)
        ui.rect(self.surf, (44, 42, 82) if hov else M.SURFACE2, rect, border_radius=10)
        ui.rect(self.surf, M.ACCENT2 if hov else M.BORDER, rect, width=1, border_radius=10)
        img = self.fonts["sb"].render(label, True, color or M.ACCENT2)
        self.surf.blit(img, (rect.centerx - img.get_width() // 2, rect.centery - img.get_height() // 2))
        self.live_hits.append((rect, bid))

    BLEND_ALPHA = (0.80, 0.62, 0.75)         # opacity of the low / mid / high layers when they are transparent

    def _wave_surface(self, lo, mi, hi, hpx, half, dim):
        """The three-band waveform as an image. Blend 0 (default): each layer is semi-transparent, so the ones behind it show through and every band keeps its
        own silhouette (additive and screen modes were tried: they wash the core out to white). Blend 1: the layers are solid and drawn one over the other.
        lo / mi / hi are 0..1 per column, dim is the brightness per column (dimmer before the track started)."""
        cols = len(lo)
        rows = np.abs(np.arange(hpx) - hpx // 2)[:, None]
        bg = np.array((6, 5, 15), float) / 255.0
        img = np.broadcast_to(bg, (hpx, cols, 3)).copy()
        for h, col, al in zip((lo * half, mi * half * 0.85, hi * half * 0.6), (LOW, MID, HIGH), self.BLEND_ALPHA):
            m = (rows <= h[None, :])[..., None].astype(float)
            c = np.array(col, float) / 255.0
            if self.blend == 0:
                img = img * (1.0 - m * al) + m * c * al                # ordinary alpha: the layer behind shows through
            else:
                img = np.where(m > 0, c, img)
        img = img * dim[None, :, None]
        arr = np.clip(img * 255.0, 0, 255).astype(np.uint8)
        return pygame.surfarray.make_surface(arr.transpose(1, 0, 2))

    def _card(self, rect):
        import menu as M
        ui.rect(self.surf, M.SURFACE, rect, border_radius=14)
        ui.rect(self.surf, M.BORDER, rect, width=1, border_radius=14)

    def predict(self, an):
        """What the analysis expects next: seconds to the end of the phrase, and a sentence about it."""
        if an.bpm <= 0:
            return None, "Aprendendo o ritmo…", False
        period = 60.0 / an.bpm
        beats_left = (an.bpb - an.beat_in_bar - an.phase) + an.bpb * max(0, an.phrase_len - an.phrase_pos - 1)
        t_end = beats_left * period
        bars = max(1, int(round(beats_left / an.bpb)))
        if an.tension > 0.55:
            return t_end, f"Drop em ~{bars} comp.", True
        return t_end, f"Mudança em ~{bars} comp.", False

    def draw_live(self, an, fps, lat, vsync, status, genre, now_t):
        """The Ao vivo tab. It answers two questions: is the program hearing the song right, and what will the picture do next.
        Main part: header, the timeline (past on the left, prediction on the right), "A imagem agora" and the whole track.
        The rest is under "Diagnóstico" (closed by default)."""
        import menu as M
        s = self.surf
        Wc = s.get_width()
        s.fill(M.BG)
        self.live_hits = []
        self._n_now = an.deck_n
        self._t_now = an.now_t
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
        self._t("xl", bpm_txt, (0, 0), M.TEXT)                           # the number stays still; the dots below carry the beat
        self._t("xs", "B P M", (2, 42), M.DIM)
        if an.bpm > 0 and not silent:                                   # one dot per beat of the bar, the current one lit
            for i in range(an.bpb):
                on = i == an.beat_in_bar
                c = tuple(int(46 + ((M.ACCENT if i == 0 else M.ACCENT2)[j] - 46) * (0.35 + 0.65 * pulse)) for j in range(3)) if on else (46, 44, 84)
                ui.circle(s, c, (62 + i * 16, 50), 5 if on else 4)
        # the key (tom) next to the BPM: it matters for mixing, so it sits at the top
        key_known = an.key_name != "--" and not silent
        self._t("xl", an.key_name if key_known else "--", (150, 0), M.TEXT if key_known else M.DIM)
        self._t("xs", "T O M", (152, 42), M.DIM)
        state = "Sem áudio" if silent else an.state.capitalize()
        tx = 262
        self._t("m", state + (f"  ·  {genre}" if (genre not in ("?", None, "") and not silent) else ""), (tx, 2), M.TEXT)
        # the energy of the music, big: ten segments (green, then yellow, then red) and the level as a number
        lvl = max(0, min(10, int(an.level10)))
        for i in range(10):
            col = (M.OK if i < 6 else (240, 190, 40) if i < 8 else M.DANGER) if i < lvl else (46, 44, 84)
            ui.rect(s, col, (tx + i * 17, 34, 13, 20), border_radius=4)
        self._t("m", f"{lvl}", (tx + 10 * 17 + 8, 30), M.TEXT)
        self._t("xs", "E N E R G I A", (tx + 10 * 17 + 8 + self.fonts["m"].size(f"{lvl}")[0] + 8, 36), M.DIM)
        ok = status is None or status.get("shader_ok", True)
        if not ok:
            ht, hc = "Erro no shader", M.DANGER
        elif silent:
            ht, hc = "Sem áudio", (255, 200, 90)
        elif fps < 25:
            ht, hc = f"Lento: {fps:.0f} FPS", (255, 200, 90)
        elif learning:
            ht, hc = (f"Aprendendo o BPM {an.conf * 100:.0f}%" if an.bpm > 0 else "Aprendendo o BPM…"), M.ACCENT2
        else:
            ht, hc = "Tudo certo", M.OK
        wch = self.fonts["s"].size(ht)[0] + 38
        r = pygame.Rect(Wc - wch, 4, wch, 26)
        ui.rect(s, M.SURFACE2, r, border_radius=13)
        ui.rect(s, M.BORDER, r, width=1, border_radius=13)
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
            self._t("s", name, (lx + 15, top + 10), M.DIM)
            lx += 15 + self.fonts["s"].size(name)[0] + 14
        bw = 108
        self._button(pygame.Rect(Wc - 14 - bw, top + 7, bw, 26), "Continuar" if self.frozen is not None else "Congelar", "freeze")
        self._button(pygame.Rect(Wc - 14 - bw - 8 - 90, top + 7, 90, 26), f"Zoom {self._zoom_label(zl)}", "zoom")
        wy, wh = top + 42, 124
        wx, ww = 12, Wc - 24
        ph = int(ww * 0.68)
        mid_y = wy + wh // 2
        half = wh // 2 - 6
        ui.rect(s, (6, 5, 15), (wx, wy, ww, wh), border_radius=8)
        fut = pygame.Rect(wx + ph, wy, ww - ph, wh)
        ui.rect(s, (13, 11, 32), fut, border_top_right_radius=8, border_bottom_right_radius=8)
        n = an.deck_n if self.frozen is None else self.frozen
        pps = PX_PER_SEC / zl
        span = min(ph * zl, n)
        if span >= zl:
            cols = span // zl
            seg = an.deck[1:4, n - cols * zl:n].reshape(3, cols, zl).max(axis=2) ** 1.5
            dim = np.where(n - (cols - np.arange(cols)) * zl >= an.trk_i0, 1.0, 0.45)
            s.blit(self._wave_surface(seg[0], seg[1], seg[2], wh, half, dim), (wx + ph - cols, wy))
        ui.rect(s, M.BORDER, fut, width=1, border_top_right_radius=8, border_bottom_right_radius=8)
        # beat grid in the past and the predicted grid in the future
        ref_t = an.now_t if self.frozen is None else self.frozen_t
        for (t, bib, barn) in an.beat_log:
            x = wx + ph - int((ref_t - t) * pps)
            if x < wx or x > wx + ph:
                continue
            Lh = 14 if bib == 0 else 8
            c = M.ACCENT if bib == 0 else M.DIM
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
                c = (150, 60, 130) if bib == 0 else (70, 66, 110)
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
            c, label, tint = STATE_STYLE.get(st, (M.DIM, st.capitalize(), 16))
            band = pygame.Surface((ex - sx, wh - 2), pygame.SRCALPHA)
            band.fill((c[0], c[1], c[2], tint))
            s.blit(band, (sx, wy + 1))
            bw = max(3, ex - sx - 1)
            ui.rect(s, c, (sx, wy + 4, bw, 17), border_radius=8)
            for cand in (label, STATE_SHORT.get(st, "")):                                  # the whole name, or a short one when the bar is narrow
                img = self.fonts["xs"].render(cand, True, M.BG)
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
            img = self.fonts["xs"].render("Build-up", True, M.BG)
            if img.get_width() + 12 <= ex - sx:
                s.blit(img, (sx + 6, wy + 24 + 6 - img.get_height() // 2))
        # prediction: the rest of the phrase and what is expected after it, as ghost sections, plus the named boundary
        if t_end is not None and not silent and self.frozen is None:
            xe = wx + ph + int(t_end * pps)
            fx0, fx1 = wx + ph + 3, wx + ww - 3
            ex_ = min(xe, fx1)
            if ex_ - fx0 > 6:
                ui.rect(s, (52, 50, 96), (fx0, wy + 4, ex_ - fx0, 17), border_radius=8)
                img = self.fonts["xs"].render("Resta da frase", True, M.TEXT)
                if img.get_width() + 14 <= ex_ - fx0:
                    s.blit(img, (fx0 + 7, wy + 4 + 8 - img.get_height() // 2))
            if xe < fx1 - 8:
                ui.rect(s, (120, 52, 78) if building else (34, 32, 66), (xe + 2, wy + 4, fx1 - xe - 2, 17), border_radius=8)
                img = self.fonts["xs"].render("Drop?" if building else "Próxima frase", True, M.TEXT)
                if img.get_width() + 14 <= fx1 - xe - 2:
                    s.blit(img, (xe + 9, wy + 4 + 8 - img.get_height() // 2))
                pygame.draw.line(s, M.DANGER, (xe, wy + 21), (xe, wy + wh - 18), 2)
                img = self.fonts["xs"].render("Drop previsto" if building else "Fim da frase", True, M.BG)
                lw = img.get_width() + 14
                lx = max(wx + ph + 6, min(xe - lw // 2, wx + ww - lw - 6))
                ui.rect(s, M.DANGER, (lx, wy + wh - 44, lw, 17), border_radius=8)
                s.blit(img, (lx + 7, wy + wh - 44 + 8 - img.get_height() // 2))
            cw_ = self.fonts["s"].size(said)[0] + 20
            self._chip(max(wx + ph + 8, wx + ww - cw_ - 8), wy + 28, said, color=(255, 200, 90) if building else M.TEXT, border=(255, 200, 90) if building else M.BORDER)
        # captions of the two halves
        self._t("xs", "P R E V I S Ã O", (wx + ww - 10, wy + wh - 15), (90, 92, 138), "r")
        ui.rect(s, (36, 34, 70), (wx, wy, ww, wh), width=1, border_radius=8)                  # the frame of the whole timeline
        # playhead: white line with a magenta marker
        pygame.draw.line(s, M.TEXT, (wx + ph, wy - 4), (wx + ph, wy + wh + 4), 3)
        pygame.draw.polygon(s, M.ACCENT, [(wx + ph - 6, wy + wh + 11), (wx + ph + 6, wy + wh + 11), (wx + ph, wy + wh + 2)])
        if silent:
            self._t("m", "Toque uma música no computador", (wx + ph // 2, mid_y - 12), (255, 200, 90), "c")
        # phrase progress (one segment per bar) and the reading
        sy = wy + wh + 16
        seg_w = (ww - (an.phrase_len - 1) * 3) / an.phrase_len
        for i in range(an.phrase_len):
            rr = pygame.Rect(int(wx + i * (seg_w + 3)), sy, int(seg_w), 6)
            ui.rect(s, (46, 44, 84), rr, border_radius=3)
            if an.bpm > 0 and not silent:
                if i < an.phrase_pos:
                    ui.rect(s, MID, rr, border_radius=3)
                elif i == an.phrase_pos:
                    ui.rect(s, M.ACCENT, (rr.x, rr.y, max(3, int(rr.w * an.bar_phase)), rr.h), border_radius=3)
        if an.bpm > 0 and not silent:
            self._t("s", f"Compasso {max(0, an.bar_n) + 1}  ·  batida {an.beat_in_bar + 1}/{an.bpb}  ·  frase {an.phrase_pos + 1}/{an.phrase_len}", (wx, sy + 12), M.DIM)

        # ---- what the picture is doing now
        iy = top + 238 + 10
        info = (status or {}).get("image") or {}
        card2 = pygame.Rect(0, iy, Wc, 86)
        self._card(card2)
        self._t("xs", "A   I M A G E M   A G O R A", (14, iy + 9), M.ACCENT)
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
            self._chip(x, y, txt, color=M.DIM)

        # ---- the whole track
        oy = iy + 86 + 12
        oh = 22
        T = an.track_time
        view = max(T, 120.0)
        ppsv = (Wc - 4) / view
        colsn = int(T * ppsv)
        ui.rect(s, (6, 5, 15), (0, oy, Wc - 4, oh), border_radius=6)
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
                pygame.draw.line(s, KIND_COLOR.get(kind, M.DIM), (xm, oy), (xm, oy + oh), 1)
        xe2 = colsn
        pygame.draw.line(s, M.TEXT, (xe2, oy - 2), (xe2, oy + oh + 2), 2)
        pygame.draw.polygon(s, M.ACCENT, [(xe2 - 5, oy + oh + 9), (xe2 + 5, oy + oh + 9), (xe2, oy + oh + 2)])
        step = 30 if view <= 360 else 60
        for sec in range(0, int(view) + 1, step):
            xt = int(sec * ppsv)
            if sec % 60 == 0:
                self._t("xs", f"{sec // 60}:00", (min(max(xt, 10), Wc - 16), oy + oh + 6), M.DIM, "c")

        # ---- status, always in view
        dy = oy + oh + 30
        card3 = pygame.Rect(0, dy, Wc, 138)
        self._card(card3)
        self._t("xs", "S   T   A   T   U   S", (14, dy + 9), M.ACCENT)
        self._status(fps, lat, vsync, status, dy + 30)
        y = dy + 138
        self.live_end = y + 8
        return self.live_end

    @staticmethod
    def _zoom_label(z):
        return {1: "4 s", 2: "8 s", 4: "16 s"}[z]

    def _status(self, fps, lat, vsync, status, y):
        """How the program itself is doing (the music is shown above). Always visible."""
        import menu as M
        s = self.surf
        dot = (110, 235, 170) if fps >= 55 else (255, 220, 100) if fps >= 40 else (255, 110, 110)
        ui.circle(s, dot, (24, y + 10), 5)
        self._t("m", f"{fps:4.0f} FPS", (36, y - 2), M.TEXT)
        self._t("s", f"{'VSync' if vsync else 'sem VSync'}  ·  latência ~{lat:3.0f} ms", (150, y + 2), M.DIM)
        y += 28
        if status:
            self._t("s", f"GPU  {status['gpu'][:36]}  ·  {status['backend']}", (14, y), M.TEXT)
            if status["shader_ok"]:
                self._t("s", f"Shaders ok  ·  {status['reloads']} recarregado(s)", (14, y + 20), M.OK)
            else:
                self._t("s", "Erro no shader (usando o anterior): " + status["shader_msg"][:40], (14, y + 20), (255, 130, 150))
            y += 42
        self._t("xs", "Na imagem:  F tela cheia  ·  D drop de teste  ·  Esc sai da tela cheia", (14, y), (130, 138, 180))
        return y + 16

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
