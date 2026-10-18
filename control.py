"""Control window: live music monitor on the left, settings on the right.

The display window renders only the effect; everything else lives here.
"""
import math
import os

os.environ.setdefault("SDL_RENDER_DRIVER", "software")   # keep this window off the OpenGL context

import pygame

import menu as M


class ControlWindow:
    LEFT = 344
    PAD = 16

    def __init__(self, menu, pos=None, headless=False):
        self.menu = menu
        self.W = self.PAD * 2 + self.LEFT + 16 + menu.W
        self.view_h = min(menu.H, 740)
        menu.view_h = self.view_h
        self.H = max(self.view_h, 600) + self.PAD * 2
        self.panel_pos = (self.PAD + self.LEFT + 16, self.PAD)
        self.surf = pygame.Surface((self.W, self.H))
        self.f_title = pygame.font.SysFont("segoeui", 12, bold=True)
        self.f_big = pygame.font.SysFont("segoeui", 56, bold=True)
        self.f_mid = pygame.font.SysFont("segoeui", 20, bold=True)
        self.f = pygame.font.SysFont("segoeui", 15)
        self.fb = pygame.font.SysFont("segoeui", 15, bold=True)
        self.f_s = pygame.font.SysFont("segoeui", 12)
        self.last = -1.0
        self.force = True
        self.win = self.ren = self.tex = None
        if not headless:
            from pygame._sdl2 import video
            self.win = video.Window("Audio Organism - Controles", (self.W, self.H), position=pos)
            self.ren = video.Renderer(self.win)
            self.tex = video.Texture(self.ren, (self.W, self.H), streaming=True)
            self.id = self.win.id

    # ---------------------------------------------------------------- input
    def handle(self, e):
        """Route an event from the control window; returns an action string or None."""
        if e.type == pygame.KEYDOWN:
            return self.menu.key(e.key, getattr(e, "mod", 0))
        if e.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL):
            return self.menu.mouse(e, self.panel_pos[0], self.panel_pos[1], 1.0)
        return None

    # ----------------------------------------------------------------- draw
    def _t(self, font, text, pos, color, anchor="l"):
        img = font.render(text, True, color)
        x, y = pos
        if anchor == "r":
            x -= img.get_width()
        elif anchor == "c":
            x -= img.get_width() // 2
        self.surf.blit(img, (x, y))
        return img.get_width()

    def bar(self, x, y, w, v, col, h=6):
        pygame.draw.rect(self.surf, (46, 44, 84), (x, y, w, h), border_radius=3)
        pygame.draw.rect(self.surf, col, (x, y, max(3, int(w * max(0.0, min(1.0, v)))), h), border_radius=3)

    def draw(self, an, fps, lat, vsync, status=None):
        s = self.surf
        s.fill(M.BG)
        P = self.PAD
        card = pygame.Rect(P, P, self.LEFT, self.H - 2 * P)
        pygame.draw.rect(s, M.SURFACE, card, border_radius=14)
        pygame.draw.rect(s, M.BORDER, card, width=1, border_radius=14)
        x0, w = card.x + 18, card.w - 36
        y = card.y + 16

        # header: title + audio status
        self._t(self.f_title, "A O   V I V O", (x0, y), M.ACCENT)
        silent = an.silence > 0.6
        label = "SEM ÁUDIO" if silent else "OUVINDO"
        col = M.WARN if hasattr(M, "WARN") else (255, 200, 90)
        col = (255, 200, 90) if silent else M.OK
        tw = self.f_title.size(label)[0] + 30
        pr = pygame.Rect(x0 + w - tw, y - 4, tw, 24)
        pygame.draw.rect(s, (*col, 40) if False else (36, 34, 66), pr, border_radius=12)
        pygame.draw.circle(s, col, (pr.x + 13, pr.centery), 4)
        self._t(self.f_title, label, (pr.x + 23, pr.y + 5), col)

        # BPM + confidence
        y += 32
        bpm = f"{an.bpm:5.1f}" if an.bpm > 0 else " --"
        self._t(self.f_big, bpm, (x0 - 2, y), M.TEXT)
        self._t(self.f_s, "BPM", (x0 + 168, y + 40), M.DIM)
        y += 66
        self._t(self.f_s, f"confiança {an.conf * 100:3.0f}%", (x0, y), M.DIM)
        self.bar(x0 + 100, y + 6, w - 100, an.conf, M.ACCENT2, 5)

        # musical part chip
        y += 28
        self._t(self.f_s, "PARTE DA MÚSICA", (x0, y), M.DIM)
        st = an.state
        sw = self.fb.size(st)[0] + 24
        cr = pygame.Rect(x0, y + 18, sw, 30)
        pygame.draw.rect(s, (60, 26, 78), cr, border_radius=15)
        pygame.draw.rect(s, M.ACCENT, cr, width=1, border_radius=15)
        self._t(self.fb, st, (cr.centerx, cr.y + 5), (255, 170, 230), "c")

        # level bars
        y += 62
        rows = (("energia", an.energy, M.ACCENT), ("graves", an.bass, (255, 70, 200)), ("médios", an.mid, (150, 120, 255)),
                ("agudos", an.high, M.ACCENT2), ("build-up", an.tension, (255, 200, 90)))
        for i, (nm, v, c) in enumerate(rows):
            yy = y + i * 24
            self._t(self.f_s, nm, (x0, yy), M.DIM)
            self.bar(x0 + 76, yy + 5, w - 76 - 40, v, c)
            self._t(self.f_s, f"{v * 100:3.0f}", (x0 + w, yy), M.DIM, "r")

        # spectrum (160 bands, dB scale, peak hold)
        y += len(rows) * 24 + 14
        self._t(self.f_s, "ESPECTRO", (x0, y), M.DIM)
        sh = 92
        base = y + 18 + sh
        n = len(an.spec)
        bw = w / n
        for i in range(n):
            v = float(an.spec[i])
            t = i / n
            c = (int(255 - 175 * t), int(70 + 150 * t), int(200 + 55 * t))
            x = int(x0 + i * bw)
            wpx = max(1, int(x0 + (i + 1) * bw) - x - (1 if bw > 2.4 else 0))
            hgt = int(v * sh)
            if hgt > 0:
                pygame.draw.rect(s, c, (x, base - hgt, wpx, hgt))
            ph = int(float(an.spec_peak[i]) * sh)
            if ph > 1:
                pygame.draw.rect(s, (235, 240, 255), (x, base - ph - 1, wpx, 1))
        for f_hz, lab in ((50, "50"), (200, "200"), (1000, "1k"), (5000, "5k"), (15000, "15k")):
            fx = x0 + w * (math.log10(f_hz / 25.0) / math.log10(18000.0 / 25.0))
            self._t(self.f_s, lab, (int(fx), base + 3), (110, 118, 160), "c")
        if silent:
            self._t(self.fb, "Toque uma música no computador", (x0 + w // 2, y + 18 + sh // 2 - 10), (255, 200, 90), "c")

        # fps / latency / beat
        y = base + 30
        dot = (110, 235, 170) if fps >= 55 else (255, 220, 100) if fps >= 40 else (255, 110, 110)
        pygame.draw.circle(s, dot, (x0 + 6, y + 13), 5)
        self._t(self.f_mid, f"{fps:4.0f} FPS", (x0 + 18, y), M.TEXT)
        self._t(self.f_s, "VSync" if vsync else "sem limite", (x0 + 124, y + 6), M.DIM)
        self._t(self.f_s, f"latência ~{lat:3.0f} ms", (x0, y + 28), M.DIM)
        k = max(an.kick, an.snare * 0.6)
        pygame.draw.circle(s, (int(60 + 195 * k),) * 3, (x0 + w - 12, y + 14), 10)
        self._t(self.f_s, "batida", (x0 + w - 36, y + 30), M.DIM, "c")

        # GPU + shader status (hot reload)
        if status:
            gy = card.bottom - 118
            self._t(self.f_s, "GPU", (x0, gy), M.DIM)
            self._t(self.f_s, f"{status['gpu'][:30]}  ·  {status['backend']}", (x0 + 34, gy), M.TEXT)
            ok = status["shader_ok"]
            pygame.draw.circle(s, M.OK if ok else (255, 110, 130), (x0 + 5, gy + 27), 4)
            if ok:
                self._t(self.f_s, f"Shaders ok  ·  {status['reloads']} recarregado(s)", (x0 + 16, gy + 20), M.OK)
            else:
                self._t(self.f_s, "Erro no shader (usando o anterior):", (x0 + 16, gy + 20), (255, 130, 150))
                msg = status["shader_msg"]
                self._t(self.f_s, msg[:44], (x0, gy + 38), (255, 170, 185))
                if len(msg) > 44:
                    self._t(self.f_s, msg[44:88], (x0, gy + 53), (255, 170, 185))

        # shortcuts
        self._t(self.f_s, "Na imagem:  F tela cheia  ·  D drop de teste", (x0, card.bottom - 40), (130, 138, 180))
        self._t(self.f_s, "Esc sai da tela cheia", (x0, card.bottom - 24), (130, 138, 180))

        # settings panel (scrollable) + scrollbar + confirmation toast
        self.menu.render()
        mw = self.menu
        area = pygame.Rect(0, mw.scroll, mw.W, self.view_h)
        s.blit(mw.surf, self.panel_pos, area)
        if mw.max_scroll() > 0:
            tx = self.panel_pos[0] + mw.W + 4
            th = max(40, int(self.view_h * self.view_h / mw.heights[mw.tab]))
            ty = self.panel_pos[1] + int((self.view_h - th) * mw.scroll / mw.max_scroll())
            pygame.draw.rect(s, (46, 44, 84), (tx, self.panel_pos[1], 5, self.view_h), border_radius=3)
            pygame.draw.rect(s, M.ACCENT2, (tx, ty, 5, th), border_radius=3)
        if mw.toast:
            txt = mw.toast[0]
            tw = self.fb.size(txt)[0] + 28
            r = pygame.Rect(self.panel_pos[0] + mw.W - tw, self.panel_pos[1] + 6, tw, 30)
            pygame.draw.rect(s, M.OK, r, border_radius=15)
            self._t(self.fb, txt, (r.centerx, r.y + 5), M.ON_ACCENT, "c")

    def update(self, now, an, fps, lat, vsync, status=None, force=False):
        if not (force or self.force or self.menu.need or now - self.last >= 0.05):
            return
        self.last = now
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
