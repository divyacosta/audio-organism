"""The look of the program in one place: the colour tokens, the fonts and the small widgets (chip, pill, button) that the settings panel (menu.py), the control
window (control.py) and the Palco (deck.py) all draw with.

Nothing here knows about a window or a list of hits: every function draws on the surface it is given and returns the rectangle it drew, and the caller registers
that rectangle in its own list of hits (the three screens keep theirs in three formats). The shapes (rounded rectangles, circles) are ui.py's.

One colour, one meaning:
  SEL        what is chosen, on, selected or focused (the theme lime, with dark ink)
  ACCENT     the same lime: the theme colour (NO AR, the main highlight)
  DANGER     a real error and what deletes (never a fill for ordinary actions)
  HOVER_EDGE the pointer is over it: a neutral, never the theme colour
  FOCUS      the keyboard focus ring: near white, never the theme colour
"""
import os

import pygame

import i18n

import ui

# ------------------------------------------------------------------ colour tokens
# The design system of the ScreenMaster (its App.xaml), in the names this file has always used. Neutral greys, one theme colour (lime),
# red only for a real error. The full write-up, with the rules and the components, is in DESIGN_SYSTEM.md.
BG = (0x16, 0x16, 0x17)            # canvas: the content behind the panels
SURFACE = (0x1C, 0x1C, 0x1F)       # Panel: the cards, the chrome (header, sidebar, footer)
SURFACE2 = (0x23, 0x23, 0x26)      # Raised: control fills, the rows at rest
HOVER_FILL = (0x26, 0x26, 0x2A)    # Hover: under the pointer
BORDER = (0x2A, 0x2A, 0x2D)        # Line: the hairline between things
LINE_STRONG = (0x3A, 0x3A, 0x3F)  # LineStrong: a stronger divider
CTRL = (0x7E, 0x7E, 0x84)          # the edge of a control, a little lighter than Outline so it reads on SURFACE2 (>= 3:1)
TITLE = (0x9A, 0x9A, 0xA0)         # the titles of the cards: the secondary text
TEXT = (0xE6, 0xE6, 0xE8)          # Text
DIM = (0x9A, 0x9A, 0xA0)           # Dim: the secondary text (>= 4.5:1 on SURFACE)
FAINT = (0x5A, 0x5A, 0x60)         # Faint: off or not applicable, still readable as a shape
SEL = (0xC6, 0xF2, 0x4E)           # Accent (the theme lime): what is chosen, on, selected, focused, and "agora"
ACCENT = SEL                       # the main colour of the theme: NO AR is the same lime, not a second colour
ACCENT_DIM = (0x2E, 0x33, 0x24)   # AccentDim: the selected row, the lime at ~12% over the panel
ACCENT2 = OK = SEL
BLUE = SEL                         # the waves and fills that were blue are the lime now
DANGER = (0xF0, 0x6A, 0x62)        # Danger: a real error and what deletes
WARN = TEXT                        # warnings are the strong neutral; red is for errors
PRIMARY_FILL = (0x2E, 0x2E, 0x33)  # PrimaryFill: the main action, a neutral button with a light label
PRIMARY_HOVER = (0x38, 0x38, 0x3E)
PRIMARY_LINE = (0x4A, 0x4A, 0x50)
PRIMARY_INK = (0xF2, 0xF2, 0xF3)
ON_SEL = (0x16, 0x16, 0x17)        # OnAccent: the text on the lime (the dark canvas)
ON_LIGHT = ON_SEL                  # the dark text on the light fills (lime, danger)
ON_ACCENT = ON_SEL                 # the text on ACCENT (the lime): the dark ink
CTRL_FILL = SURFACE2               # the resting fill of a control
HOVER_EDGE = (0x9A, 0x9A, 0xA0)    # the edge of what is under the pointer: the secondary neutral
FOCUS = SEL                        # the keyboard focus ring: the theme lime, as the ScreenMaster's Accent focus ring
PRIMARY_HOVER_EDGE = CTRL

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
FAMILY = "Segoe UI Variable,segoeui"      # the Windows 11 face for screens (the old segoeui file is the Light weight: thin and pixelated at 12-15 px)
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
    """(fill, edge, ink) of a button. kinds: "primary" (the one main action: neutral fill, light label), "select" (chosen: the lime with dark ink),
    "tone" (quiet, its edge and text carry a colour; armed = asked once, press again), "quiet" (text only), "danger" (what deletes) or "plain"."""
    if kind == "primary":                                                       # the main action: a neutral button with a light label (ScreenMaster's Primary)
        fill, edge, ink = (PRIMARY_HOVER if hover else PRIMARY_FILL), (CTRL if hover else PRIMARY_LINE), PRIMARY_INK
    elif kind == "quiet":                                                       # no fill and no edge at rest: text and icons (ScreenMaster's Quiet / IconButton)
        fill, edge, ink = (HOVER_FILL if hover else BG), (BORDER if hover else BG), (TEXT if hover else DIM)
    elif kind == "danger":                                                      # what deletes: the danger colour on a neutral fill
        fill, edge, ink = (HOVER_FILL if hover else SURFACE2), DANGER, DANGER
    elif kind == "select":
        fill, edge, ink = SEL, SEL, ON_SEL
    elif kind == "tone":
        tone = tone or SEL
        fill = tone if armed else (HOVER_FILL if hover else CTRL_FILL)
        edge = tone if (hover or armed or tone_edge) else CTRL                  # tone_edge: the edge says it even at rest (what deletes)
        ink = ON_LIGHT if armed else tone
    else:
        fill, edge, ink = (HOVER_FILL if hover else SURFACE), (HOVER_EDGE if hover else CTRL), TEXT     # the secondary: an outline on the panel, no fill (ScreenMaster's)
    if not enabled:
        fill, ink = dimmed(fill, 0.6), dimmed(DIM, 0.74)
    return fill, edge, ink


def button(surf, fnt, rect, text, kind="plain", hover=False, armed=False, enabled=True, tone=None, radius=None, hint=None, hint_font=None, dy=0, tone_edge=False, pad=5):
    """A button: its shape, edge and text (and a small second line, `hint`). The caller keeps its hit and its hover. Returns the rectangle."""
    r = pygame.Rect(rect)
    fill, edge, ink = button_colors(kind, hover, armed, enabled, tone, tone_edge)
    rad = radius if radius is not None else (8 if r.h >= 40 else 6 if r.h >= 24 else r.h // 2)     # the corners of the ScreenMaster's buttons: 6
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
