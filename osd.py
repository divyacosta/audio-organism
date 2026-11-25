"""The words on the picture window (full screen only): a dark pill at the bottom with the name of the scene the person just brought to the screen and, for a
few seconds after entering full screen, the keys that matter (the picture is all there is on that screen: without this nobody knows how to get back).

The pill is rasterised here with pygame's fonts, sized for the height of the screen, and handed to the renderer as a picture (Renderer.set_osd); the renderer
draws it as one more quad over the finished picture. Nothing here touches the GPU, and nothing is drawn while the words are off.
"""
import time

import pygame

HINT = "Esc sai  ·  1–9 trocam a cena  ·  A liga a troca automática"
FADE_IN, FADE_OUT = 0.18, 0.60


class Osd:
    def __init__(self):
        self.title, self.hint = "", ""
        self.t0, self.dur = 0.0, 0.0
        self._cache = None                       # (key, rgba bytes, w, h) of the pill for the current words and screen height
        self._fonts = {}

    def show(self, title="", hint="", dur=2.4, now=None):
        """Write `title` (and, smaller under it, `hint`) on the picture for `dur` seconds, with a short fade in and a longer one out."""
        self.title, self.hint = str(title), str(hint)
        self.t0 = time.perf_counter() if now is None else now
        self.dur = float(dur)

    def hide(self):
        self.dur = 0.0

    def alpha(self, now=None):
        """The opacity of the words now: 0 when they are off."""
        t = (time.perf_counter() if now is None else now) - self.t0
        if self.dur <= 0.0 or t < 0.0 or t > self.dur + FADE_OUT:
            return 0.0
        if t < FADE_IN:
            return t / FADE_IN
        if t <= self.dur:
            return 1.0
        return 1.0 - (t - self.dur) / FADE_OUT

    def _font(self, px, bold):
        key = (px, bold)
        f = self._fonts.get(key)
        if f is None:
            if not pygame.font.get_init():
                pygame.font.init()
            import widgets
            f = self._fonts[key] = widgets.tfont("segoeui", px, bold)
        return f

    def image(self, screen_h):
        """(key, rgba bytes, w, h) of the pill for the words now, drawn for a screen `screen_h` pixels high (so it stays sharp and the same size to the eye on a
        laptop and on a projector). Drawn again only when the words or the height change."""
        key = (self.title, self.hint, int(screen_h))
        if self._cache is not None and self._cache[0] == key:
            return self._cache
        tpx = max(20, min(72, int(round(screen_h * 0.032))))
        hpx = max(14, int(round(tpx * 0.56)))
        lines = []
        if self.title:
            lines.append((self._font(tpx, True).render(self.title, True, (255, 255, 255)), tpx))
        if self.hint:
            lines.append((self._font(hpx, False).render(self.hint, True, (205, 210, 225)), hpx))
        if not lines:
            lines = [(self._font(hpx, False).render(" ", True, (255, 255, 255)), hpx)]
        padx, pady, gap = int(tpx * 0.95), int(tpx * 0.50), int(tpx * 0.16)
        w = max(img.get_width() for img, _ in lines) + padx * 2
        h = sum(img.get_height() for img, _ in lines) + gap * (len(lines) - 1) + pady * 2
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (6, 7, 12, 170), pygame.Rect(0, 0, w, h), border_radius=min(h // 2, int(tpx * 0.7)))
        y = pady
        for img, _ in lines:
            surf.blit(img, ((w - img.get_width()) // 2, y))
            y += img.get_height() + gap
        raw = (pygame.image.tobytes if hasattr(pygame.image, "tobytes") else pygame.image.tostring)(surf, "RGBA")
        self._cache = (key, raw, w, h)
        return self._cache
