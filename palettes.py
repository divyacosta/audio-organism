"""Colour palettes the scenes can use (the Cores tab). A palette is a dict: name, colors (a few RGB swatches, 0..255) and bgs (the rooms the
picture may sit in). When the picture changes its colours, a palette is used like this: a background is drawn from bgs, and every one of the
three universes takes three swatches (face, side, edge), the edge being the one that contrasts most with the background.

Scene palette 0 means "the character's own colours" (the families the engine always had); 1.. are the entries of the list, which the
person can duplicate and edit.
"""
import random


def _rgb(t):
    return [int(round(v * 255)) for v in t]


def factory():
    return [
        dict(name="Neon", colors=[_rgb(c) for c in ((0.30, 1.0, 0.25), (0.55, 0.22, 1.0), (0.85, 1.0, 0.92), (0.10, 0.90, 1.0), (1.0, 0.20, 0.85),
                                                     (1.0, 0.90, 0.20), (1.0, 0.08, 0.12), (0.12, 0.28, 1.0), (0.15, 0.85, 0.80), (1.0, 0.55, 0.20))],
             bgs=[_rgb((0.0, 0.0, 0.0)), _rgb((0.0, 0.01, 0.05))]),
        dict(name="Vitral", colors=[_rgb(c) for c in ((0.10, 0.25, 1.0), (0.55, 0.15, 1.0), (1.0, 0.72, 0.18), (0.15, 0.75, 1.0))],
             bgs=[_rgb((0.0, 0.0, 0.03)), _rgb((0.02, 0.0, 0.05)), _rgb((0.0, 0.01, 0.04))]),
        dict(name="Quente", colors=[_rgb(c) for c in ((1.0, 0.08, 0.55), (1.0, 0.42, 0.0), (1.0, 0.88, 0.05), (0.0, 0.88, 1.0), (0.1, 1.0, 0.35), (1.0, 0.05, 0.1))],
             bgs=[_rgb((0.0, 0.0, 0.0)), _rgb((0.95, 0.95, 0.96))]),
        dict(name="Pastel", colors=[_rgb(c) for c in ((1.0, 0.42, 0.72), (0.25, 0.88, 1.0), (1.0, 0.88, 0.35), (0.70, 0.52, 1.0), (0.45, 1.0, 0.78), (1.0, 0.48, 0.42))],
             bgs=[_rgb((0.97, 0.96, 0.98)), _rgb((0.07, 0.04, 0.14))]),
        dict(name="Cinza e destaque", colors=[_rgb(c) for c in ((0.17, 0.18, 0.21), (0.05, 0.05, 0.07), (1.0, 0.05, 0.18), (0.0, 0.85, 1.0), (1.0, 1.0, 1.0))],
             bgs=[_rgb((0.0, 0.0, 0.0))]),
        dict(name="Vermelho, azul e branco", colors=[_rgb(c) for c in ((1.0, 0.03, 0.24), (0.05, 0.25, 1.0), (1.0, 1.0, 1.0), (0.0, 0.0, 0.0))],
             bgs=[_rgb((0.0, 0.0, 0.0)), _rgb((0.92, 0.03, 0.22)), _rgb((0.05, 0.23, 0.92)), _rgb((0.92, 0.92, 0.92))]),
    ]


def valid(p):
    return (isinstance(p, dict) and isinstance(p.get("name"), str) and isinstance(p.get("colors"), list) and isinstance(p.get("bgs"), list)
            and all(isinstance(c, list) and len(c) == 3 for c in p["colors"] + p["bgs"]))


def lum(c):
    return 0.30 * c[0] + 0.59 * c[1] + 0.11 * c[2]


def roll(pal, rng=random):
    """-> (universes, background): universes = three [face, side, edge] of float RGB; background = float RGB."""
    cols = [tuple(v / 255.0 for v in c) for c in pal["colors"]] or [(1.0, 1.0, 1.0)]
    bgs = [tuple(v / 255.0 for v in b) for b in pal["bgs"]] or [(0.0, 0.0, 0.0)]
    bg = rng.choice(bgs)
    out = []
    for _ in range(3):
        picks = rng.sample(cols, 3) if len(cols) >= 3 else [cols[i % len(cols)] for i in range(3)]
        picks.sort(key=lambda c: -abs(lum(c) - lum(bg)))
        out.append([picks[1], picks[2], picks[0]])                  # face, side, edge (the edge contrasts most with the room)
    return out, bg


def items(pal):
    """The editable swatches of a palette: the backgrounds first, then the colours. -> list of (label, [r, g, b])."""
    return [("Fundo %d" % (i + 1), c) for i, c in enumerate(pal["bgs"])] + [("Cor %d" % (i + 1), c) for i, c in enumerate(pal["colors"])]


def item_ref(pal, k):
    """The list and index behind swatch k of items()."""
    nb = len(pal["bgs"])
    return (pal["bgs"], k) if k < nb else (pal["colors"], k - nb)
