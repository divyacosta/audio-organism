"""Small pictograms that stand for a setting, drawn with the shapes of ui.py (no image files). Each icon is a 32 x 32 square and takes the value of the
setting as `t` (0..1) when it has one, so the picture changes as the control moves: the panel gets wider, the layers shrink faster, the corners round off...
`on` is the state of a toggle (lit or dim)."""
import math

import pygame

import ui

SIZE = 32
SYM_SPOKES = {2: 6, 3: 8, 4: 5, 7: 12}           # m_sym index -> number of spokes of the radial cuts
ICON_IDS = {"m_psx", "m_psy", "m_pox", "m_poy", "m_decay", "m_thick", "m_funnel", "m_cuts", "m_round", "m_glass"} | {"m_sym%d" % i for i in range(8)} | {"m_symnone"} | {"cam_orbit", "cam_roll", "cam_shake", "cam_punch", "cam_funnel", "mv_speed", "mv_rot", "mv_pulse", "strobe", "react", "bloom", "bg_light"}


def has(cid):
    return cid in ICON_IDS


def _lerp(a, b, t):
    return a + (b - a) * max(0.0, min(1.0, t))


def _box(s, col, x, y, w, h, width=2, r=3):
    ui.rect(s, col, (int(x), int(y), max(2, int(w)), max(2, int(h))), width=width, border_radius=r)


def _arrow(s, col, a, b):
    """A line with a small head at both ends."""
    pygame.draw.line(s, col, a, b, 2)
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    for (p, sg) in ((a, 1), (b, -1)):
        h1 = (p[0] + sg * (ux * 4 - uy * 3), p[1] + sg * (uy * 4 + ux * 3))
        h2 = (p[0] + sg * (ux * 4 + uy * 3), p[1] + sg * (uy * 4 - ux * 3))
        pygame.draw.line(s, col, p, h1, 2)
        pygame.draw.line(s, col, p, h2, 2)


def draw(s, cid, rect, col, t=None, on=True):
    """Draw the icon of setting `cid` inside `rect` (32 x 32) in colour `col`."""
    x0, y0 = rect.x, rect.y
    cx, cy = x0 + SIZE // 2, y0 + SIZE // 2
    soft = tuple(int(c * 0.45 + 12) for c in col)
    t = 0.5 if t is None else t
    if cid == "m_psx":                                   # width of a panel
        w = _lerp(10, 26, t)
        _box(s, col, cx - w / 2, cy - 8, w, 12)
        _arrow(s, soft, (cx - w / 2, cy + 10), (cx + w / 2, cy + 10))
    elif cid == "m_psy":                                 # height of a panel
        h = _lerp(6, 24, t)
        _box(s, col, cx - 8, cy - h / 2, 12, h)
        _arrow(s, soft, (cx + 10, cy - h / 2), (cx + 10, cy + h / 2))
    elif cid in ("m_pox", "m_poy"):                      # how far the layers sit from each other
        d = _lerp(2, 12, t)
        if cid == "m_pox":
            _box(s, soft, cx - 6 - d / 2, cy - 5, 12, 10)
            _box(s, col, cx - 6 + d / 2, cy - 5, 12, 10)
        else:
            _box(s, soft, cx - 6, cy - 6 - d / 2, 12, 10)
            _box(s, col, cx - 6, cy - 4 + d / 2, 12, 10)
    elif cid == "m_decay":                               # each layer keeps a share of the size of the one before
        k = _lerp(0.55, 0.97, t)
        size = 26.0
        for i in range(4):
            _box(s, col if i == 0 else soft, cx - size / 2, cy - size / 2, size, size, width=2 if i == 0 else 1, r=2)
            size *= k
    elif cid == "m_thick":                               # thickness: a slab with depth
        d = _lerp(2, 10, t)
        _box(s, soft, cx - 11 + d, cy - 9 - d / 2, 18, 12, width=1)
        _box(s, col, cx - 11, cy - 4, 18, 12)
        pygame.draw.line(s, soft, (cx - 11, cy - 4), (cx - 11 + d, cy - 9 - d / 2), 1)
        pygame.draw.line(s, soft, (cx + 7, cy - 4), (cx + 7 + d, cy - 9 - d / 2), 1)
        pygame.draw.line(s, soft, (cx + 7, cy + 8), (cx + 7 + d, cy + 3 - d / 2), 1)
    elif cid == "m_funnel":                              # the funnel never closes below this
        bw = _lerp(3, 22, t)
        pts = [(cx - 13, cy - 11), (cx + 13, cy - 11), (cx + bw / 2, cy + 11), (cx - bw / 2, cy + 11)]
        pygame.draw.polygon(s, col, pts, 2)
    elif cid == "cam_orbit":                             # the camera sweeps around: an ellipse with a dot on it
        pygame.draw.ellipse(s, soft, (cx - 13, cy - 7, 26, 14), 2)
        ui.circle(s, col, (cx + 13 * math.cos(t * 5), cy + 7 * math.sin(t * 5)), 3)
    elif cid == "cam_roll":                              # tilt: a frame turned by t
        a = (t - 0.5) * 1.2
        pts = [(cx + 11 * math.cos(a + k), cy + 8 * math.sin(a + k)) for k in (0, math.pi)]
        pygame.draw.polygon(s, col, [(cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)) for dx, dy in ((-11, -8), (11, -8), (11, 8), (-11, 8))], 2)
    elif cid == "cam_shake":                             # shake: a zigzag, wider with t
        w = _lerp(1, 5, t)
        pts = [(cx - 13 + i * 5.2, cy + (w if i % 2 else -w)) for i in range(6)]
        pygame.draw.lines(s, col, False, pts, 2)
    elif cid == "cam_punch":                             # punch: an arrow going into a frame
        _box(s, soft, cx - 5, cy - 9, 16, 18, width=1)
        pygame.draw.line(s, col, (cx - 13, cy), (cx + _lerp(0, 5, t), cy), 2)
        pygame.draw.polygon(s, col, [(cx + _lerp(0, 5, t), cy), (cx + _lerp(0, 5, t) - 5, cy - 4), (cx + _lerp(0, 5, t) - 5, cy + 4)])
    elif cid == "cam_funnel":                            # funnel: converging lines
        pygame.draw.line(s, col, (cx - 12, cy - 11), (cx - 3, cy + 10), 2)
        pygame.draw.line(s, col, (cx + 12, cy - 11), (cx + 3, cy + 10), 2)
        pygame.draw.line(s, soft, (cx - 9, cy - 3), (cx + 9, cy - 3), 1)
    elif cid == "mv_speed":                              # speed: chevrons, more with t
        for i in range(1 + int(t * 3.99)):
            x = cx - 10 + i * 8
            pygame.draw.lines(s, col, False, [(x, cy - 9), (x + 6, cy), (x, cy + 9)], 2)
    elif cid == "mv_rot":                                # rotation: an open circle with a head
        pygame.draw.arc(s, col, (cx - 11, cy - 11, 22, 22), 0.6, 5.6, 2)
        pygame.draw.polygon(s, col, [(cx + 9, cy - 8), (cx + 14, cy - 3), (cx + 6, cy - 2)])
    elif cid == "mv_pulse":                              # pulse: rings, the outer one grows with t
        ui.circle(s, col, (cx, cy), 5, 2)
        ui.circle(s, soft, (cx, cy), int(_lerp(8, 14, t)), 1)
    elif cid == "strobe":                                # strobe: a bolt
        pygame.draw.polygon(s, col, [(cx + 3, cy - 13), (cx - 7, cy + 2), (cx - 1, cy + 2), (cx - 4, cy + 13), (cx + 8, cy - 4), (cx + 1, cy - 4)], 0 if t > 0.1 else 2)
    elif cid in ("react", "bloom"):                      # reaction / glow: bars of an equaliser, taller with t
        for i, hh in enumerate((0.5, 1.0, 0.7, 0.9)):
            h = max(3, 22 * hh * (0.3 + 0.7 * t))
            pygame.draw.rect(s, col if i % 2 == 0 else soft, (cx - 12 + i * 7, cy + 11 - h, 4, h))
    elif cid == "bg_light":                              # background lights: a sun with rays
        ui.circle(s, col, (cx, cy), 5, 2)
        for i in range(8):
            a = i * math.pi / 4
            pygame.draw.line(s, soft, (cx + 8 * math.cos(a), cy + 8 * math.sin(a)), (cx + 13 * math.cos(a), cy + 13 * math.sin(a)), 2)
    elif cid == "m_cuts":                                # how often colours and universes are cut: a bolt
        pts = [(cx + 3, cy - 13), (cx - 7, cy + 2), (cx - 1, cy + 2), (cx - 4, cy + 13), (cx + 8, cy - 4), (cx + 1, cy - 4)]
        pygame.draw.polygon(s, col, pts, 2)
    elif cid == "m_round":                               # corners: straight, alternate, all rounded (t is 0, .5 or 1)
        r = 9
        a = r if t >= 0.4 else 0
        b = r if t >= 0.9 else 0
        ui.rect(s, col, (cx - 12, cy - 12, 24, 24), width=2, border_top_left_radius=a, border_bottom_right_radius=a,
                border_top_right_radius=b, border_bottom_left_radius=b)
    elif cid == "m_glass":                               # opacity of the faces over a checkerboard
        for i in range(4):
            for j in range(4):
                if (i + j) % 2 == 0:
                    pygame.draw.rect(s, (70, 76, 100), (cx - 12 + i * 6, cy - 12 + j * 6, 6, 6))
        ov = pygame.Surface((16, 16), pygame.SRCALPHA)
        ov.fill((col[0], col[1], col[2], int(_lerp(45, 255, t))))
        s.blit(ov, (cx - 8, cy - 8))
        _box(s, col, cx - 8, cy - 8, 16, 16, width=1, r=1)
    elif cid == "m_symnone":                             # no mirror at all: a circle struck through
        c = col if on else (66, 72, 98)
        ui.circle(s, c, (cx, cy), 13, 2)
        pygame.draw.line(s, c, (cx - 9, cy + 9), (cx + 9, cy - 9), 2)
    elif cid.startswith("m_sym"):                        # a kaleidoscope cut, lit when it may be used
        k = int(cid[5:])
        c = col if on else (66, 72, 98)
        ui.circle(s, c, (cx, cy), 13, 2)
        if k in SYM_SPOKES:
            n = SYM_SPOKES[k]
            for i in range(n):
                a = -math.pi / 2 + i * 2 * math.pi / n
                pygame.draw.line(s, c, (cx, cy), (cx + 13 * math.cos(a), cy + 13 * math.sin(a)), 2)
        elif k == 0:                                     # four mirrors: a cross
            pygame.draw.line(s, c, (cx - 13, cy), (cx + 13, cy), 2)
            pygame.draw.line(s, c, (cx, cy - 13), (cx, cy + 13), 2)
        elif k == 1:                                     # side mirror: a vertical axis and a shape on each side
            pygame.draw.line(s, c, (cx, cy - 13), (cx, cy + 13), 2)
            pygame.draw.polygon(s, c, [(cx - 3, cy - 5), (cx - 9, cy + 5), (cx - 3, cy + 5)], 1)
            pygame.draw.polygon(s, c, [(cx + 3, cy - 5), (cx + 9, cy + 5), (cx + 3, cy + 5)], 1)
        elif k == 5:                                     # diagonal axis
            pygame.draw.line(s, c, (cx - 9, cy + 9), (cx + 9, cy - 9), 2)
            pygame.draw.polygon(s, c, [(cx - 2, cy - 7), (cx - 8, cy - 7), (cx - 8, cy - 1)], 1)
            pygame.draw.polygon(s, c, [(cx + 2, cy + 7), (cx + 8, cy + 7), (cx + 8, cy + 1)], 1)
        elif k == 6:                                     # vertical mirror: a horizontal axis, one shape above and one below
            pygame.draw.line(s, c, (cx - 13, cy), (cx + 13, cy), 2)
            pygame.draw.polygon(s, c, [(cx - 5, cy - 3), (cx + 5, cy - 3), (cx, cy - 9)], 1)
            pygame.draw.polygon(s, c, [(cx - 5, cy + 3), (cx + 5, cy + 3), (cx, cy + 9)], 1)
