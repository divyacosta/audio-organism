"""The picture of the visual "Logo / texto": the text the person typed or the image they chose, as RGBA bytes for the GPU.
Cached by what it is made of (text, file, date of the file), so asking for it every frame costs nothing."""
import os
import threading

import pygame

MAX_W = 2048
_cache = {}
_lock = threading.Lock()
_font_cache = {}


def folder():
    """Where a logo placed by hand is looked for: Documentos\\AudioOrganism (logo.png)."""
    return os.path.join(os.environ.get("VIS_SHAREDIR") or os.path.join(os.path.expanduser("~"), "Documents", "AudioOrganism"))


def _font(size):
    f = _font_cache.get(size)
    if f is None:
        if not pygame.font.get_init():
            pygame.font.init()
        f = _font_cache[size] = pygame.font.SysFont("segoeui,arial", size, bold=True)
    return f


def _text_surface(text):
    lines = [ln for ln in str(text or "").replace("\\n", "\n").split("\n")] or [""]
    lines = [ln if ln else " " for ln in lines][:4]
    size = 200
    while True:
        f = _font(size)
        imgs = [f.render(ln, True, (255, 255, 255)) for ln in lines]
        w = max(i.get_width() for i in imgs)
        if w <= MAX_W - 80 or size <= 40:
            break
        size = int(size * 0.8)
    lh = imgs[0].get_height()
    surf = pygame.Surface((w + 80, lh * len(imgs) + 60), pygame.SRCALPHA)
    for i, img in enumerate(imgs):
        surf.blit(img, ((surf.get_width() - img.get_width()) // 2, 30 + i * lh))
    return surf


def make(text, path=""):
    """(key, rgba bytes, width, height) for a text, or for the image at `path` when that file exists (the text is then ignored)."""
    path = str(path or "").strip().strip('"')
    if not path:
        auto = os.path.join(folder(), "logo.png")
        path = auto if os.path.exists(auto) and not str(text or "").strip() else ""
    stamp = 0.0
    if path:
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            path = ""
    key = (str(text or ""), path, stamp)
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            return hit
        surf = None
        if path:
            try:
                img = pygame.image.load(path)
                s = min(1.0, MAX_W / max(img.get_width(), 1), 1024.0 / max(img.get_height(), 1))
                if s < 1.0:
                    img = pygame.transform.smoothscale(img, (max(2, int(img.get_width() * s)), max(2, int(img.get_height() * s))))
                surf = pygame.Surface(img.get_size(), pygame.SRCALPHA)
                surf.blit(img, (0, 0))
            except Exception:
                surf = None
        if surf is None:
            surf = _text_surface(text if str(text or "").strip() else "Audio Organism")
        w, h = surf.get_size()
        out = (key, pygame.image.tostring(surf, "RGBA"), w, h)
        if len(_cache) > 12:
            _cache.clear()
        _cache[key] = out
        return out
