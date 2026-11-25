"""The look of the program in one place: the colour tokens, the fonts and the small widgets (chip, pill, button) that the settings panel (menu.py), the control
window (control.py) and the Palco (deck.py) all draw with.

Nothing here knows about a window or a list of hits: every function draws on the surface it is given and returns the rectangle it drew, and the caller registers
that rectangle in its own list of hits (the three screens keep theirs in three formats). The shapes (rounded rectangles, circles) are ui.py's.

One colour, one meaning:
  SEL        what is chosen: the lit option, the switch that is on, the current step, the chosen tile (a fill with dark ink, or a thick edge); also the links
  ACCENT     the main action and what is on the air (NO AR): never "chosen"
  HOVER_EDGE the pointer is over it: never the blue of SEL
  FOCUS      the keyboard focus ring: never the blue of SEL
"""
import os

import pygame

import i18n

import ui

# ------------------------------------------------------------------ colour tokens
BG = (9, 10, 16)
SURFACE = (18, 20, 30)
SURFACE2 = (30, 33, 47)
BORDER = (52, 56, 78)
CTRL = (100, 108, 144)          # the border of the controls (buttons, fields, choices): >= 3:1 on SURFACE and on SURFACE2
TITLE = (150, 158, 184)         # the titles of the cards
TEXT = (235, 235, 235)         # EBEBEB
DIM = (160, 165, 182)          # >= 4.5:1 on SURFACE
ACCENT = (235, 8, 56)          # EB0838: the main action, and what is on the air
SEL = (74, 134, 255)           # the blue (004FEC) lightened to read as text and lines on the dark surfaces: what is chosen or on
ACCENT2 = OK = SEL
DANGER = (255, 98, 120)
ON_ACCENT = (255, 255, 255)    # text on the red
ON_LIGHT = (10, 12, 22)        # dark text on the light fills (blue, danger)
ON_SEL = ON_LIGHT              # text on SEL
BLUE = (0, 79, 236)            # 004FEC, as it is, for fills and the waves
CTRL_FILL = (26, 28, 42)       # the resting fill of a control of the settings panel
HOVER_FILL = (40, 44, 64)      # the same under the pointer
PRIMARY_HOVER = (255, 60, 100)  # the main action under the pointer
HOVER_EDGE = (200, 204, 216)   # the edge of what is under the pointer: a light neutral, never the blue of SEL
FOCUS = TEXT                   # the keyboard focus ring: near white, never the blue of SEL

MIN_H = 24                     # the least height of anything that is clicked (WCAG 2.5.8)


def dimmed(c, f=0.45):
    return tuple(int(BG[i] + (c[i] - BG[i]) * f) for i in range(3))


def luminance(c):
    """Relative luminance of an RGB colour (WCAG)."""
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def contrast(a, b):
    """Contrast ratio of two colours (1..21): text needs 4.5, the edge of a control 3."""
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# ------------------------------------------------------------------ fonts
FAMILY = "segoeui"
SIZES = dict(cap=12, small=13, label=14, body=15, lead=18, head=20, title=22, h1=26, h2=34, display=60)         # the sizes the program writes with, by role
_fonts = {}


def font(role, bold=False):
    """The font of a role (SIZES), made the first time it is asked for and shared by every screen (pygame's font module has to be up by then)."""
    f = _fonts.get((role, bold))
    if f is not None:
        try:
            f.get_height()
        except pygame.error:                                  # the font module was restarted since: make it again
            f = None
    if f is None:
        f = _fonts[(role, bold)] = tfont(FAMILY, SIZES[role], bold)
    return f


class TFont(pygame.font.Font):
    """A font that writes and measures in the language of the panel (see i18n.py)."""
    def render(self, text, *a, **k):
        return super().render(i18n.T(text), *a, **k)

    def size(self, text):
        return super().size(i18n.T(text))


def tfont(family, size, bold=False):
    """The system font `family` as a TFont (the same file and size SysFont would take)."""
    path = None
    for name in family.split(","):
        path = pygame.font.match_font(name.strip(), bold=bold)
        if path:
            break
    f = TFont(path, size)
    if bold and path and "bold" not in os.path.basename(path).lower() and not path.lower().endswith(("bd.ttf", "b.ttf")):
        f.bold = True
    return f


def fit(fnt, text, w):
    """`text` cut to at most w pixels. A cut always ends in an ellipsis: a word is never left broken without one."""
    text = i18n.T(text)                                       # cut the words that are drawn (in the language of the panel)
    if fnt.size(text)[0] <= w:
        return text
    while text and fnt.size(text + "…")[0] > w:
        text = text[:-1]
    return text.rstrip() + "…"


# ------------------------------------------------------------------ widgets
def touch(rect, min_h=MIN_H):
    """The rectangle of something that is clicked: `rect`, grown about its centre to at least min_h tall. Draw with it and register that same rectangle."""
    r = pygame.Rect(rect)
    if r.h < min_h:
        r.inflate_ip(0, min_h - r.h)
    return r


def chip(surf, fnt, x, y, text, color=None, border=None, pad=10, h=22, dy=0):
    """A small rounded label (a status, a name); not clicked. Returns the width it took."""
    img = fnt.render(text, True, color or TEXT)
    w = img.get_width() + 2 * pad
    r = pygame.Rect(x, y, w, h)
    ui.rect(surf, SURFACE2, r, border_radius=h // 2)
    ui.rect(surf, border or BORDER, r, width=1, border_radius=h // 2)
    surf.blit(img, (x + pad, y + (h - img.get_height()) // 2 + dy))
    return w


def pill(surf, fnt, rect, text, fill, fg, outline=None, dy=0):
    """A capsule with its text in the middle: a badge, or a small button (then `rect` is a touch() one). Returns the rectangle."""
    r = pygame.Rect(rect)
    ui.rect(surf, fill, r, border_radius=r.h // 2)
    if outline:
        ui.rect(surf, outline, r, width=1, border_radius=r.h // 2)
    img = fnt.render(fit(fnt, text, r.w - 8), True, fg)
    surf.blit(img, (r.centerx - img.get_width() // 2, r.y + (r.h - img.get_height()) // 2 + dy))
    return r


def button_colors(kind="plain", hover=False, armed=False, enabled=True, tone=None, tone_edge=False):
    """(fill, edge, ink) of a button. kind: "primary" (the one main action, red), "select" (chosen, blue with dark ink), "tone" (quiet, its edge and text carry
    a colour: blue, or red for what deletes; armed = asked once, press again) or "plain"."""
    if kind == "primary":
        fill, edge, ink = (PRIMARY_HOVER if hover else ACCENT), ACCENT, ON_ACCENT
    elif kind == "select":
        fill, edge, ink = SEL, SEL, ON_SEL
    elif kind == "tone":
        tone = tone or SEL
        fill = tone if armed else (HOVER_FILL if hover else CTRL_FILL)
        edge = tone if (hover or armed or tone_edge) else CTRL                  # tone_edge: the edge says it even at rest (what deletes)
        ink = ON_LIGHT if armed else tone
    else:
        fill, edge, ink = (HOVER_FILL if hover else SURFACE2), (HOVER_EDGE if hover else CTRL), TEXT
    if not enabled:
        fill, ink = dimmed(fill, 0.6), dimmed(DIM, 0.74)
    return fill, edge, ink


def button(surf, fnt, rect, text, kind="plain", hover=False, armed=False, enabled=True, tone=None, radius=None, hint=None, hint_font=None, dy=0, tone_edge=False, pad=5):
    """A button: its shape, edge and text (and a small second line, `hint`). The caller keeps its hit and its hover. Returns the rectangle."""
    r = pygame.Rect(rect)
    fill, edge, ink = button_colors(kind, hover, armed, enabled, tone, tone_edge)
    rad = radius if radius is not None else (12 if r.h >= 40 else 10 if r.h >= 28 else r.h // 2)
    ui.rect(surf, fill, r, border_radius=rad)
    ui.rect(surf, edge, r, width=2 if armed else 1, border_radius=rad)
    img = fnt.render(fit(fnt, text, r.w - 2 * pad), True, ink)
    if hint:
        hf = hint_font or fnt
        surf.blit(img, (r.centerx - img.get_width() // 2, r.centery - img.get_height() // 2 - 7 + dy))
        h2 = hf.render(fit(hf, hint, r.w - 8), True, ink if kind in ("primary", "select") else DIM)
        surf.blit(h2, (r.centerx - h2.get_width() // 2, r.centery + 8 + dy))
    else:
        surf.blit(img, (r.centerx - img.get_width() // 2, r.centery - img.get_height() // 2 + dy))
    return r
