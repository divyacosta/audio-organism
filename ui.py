"""The look of the panels: anti-aliased shapes with the same signatures as pygame.draw (rect with border radii, circle), so a screen drawn with
`ui.rect(...)` instead of `pygame.draw.rect(...)` gets smooth rounded corners and round dots.

pygame.draw has no anti-aliasing, which is why rounded corners and circles looked jagged. Here only the corners (and circles) are AA: they are
rendered once at 8x, scaled down and cached; the straight parts are plain rectangles, so a big card costs the same as a small one.

Design tokens (radii, spacing) live here too, next to the colour tokens of menu.py, so the whole interface can be tuned in one place.
"""
import pygame

# ---- tokens
R_SM, R_MD, R_LG, R_PILL = 8, 10, 14, 99          # corner radii: chips and fields / buttons and rows / cards / pills
SP = (4, 8, 12, 16, 24)                            # spacing scale

_SS = 8                                            # supersampling of the cached corners
_corner_alpha = {}                                 # (radius, ring width) -> white surface whose alpha is the AA quarter (top-left)
_colored = {}                                      # (kind, radius, width, color) -> ready-to-blit surface


def _quarter(r, width):
    """The top-left corner of a rounded rectangle, r x r: filled (width 0) or a ring `width` thick. Alpha carries the anti-aliasing."""
    key = (r, width)
    m = _corner_alpha.get(key)
    if m is None:
        big = pygame.Surface((r * _SS, r * _SS), pygame.SRCALPHA)
        pygame.draw.circle(big, (255, 255, 255, 255), (r * _SS, r * _SS), r * _SS)
        if width > 0 and width < r:
            pygame.draw.circle(big, (0, 0, 0, 0), (r * _SS, r * _SS), (r - width) * _SS)
        m = pygame.transform.smoothscale(big, (r, r))
        _corner_alpha[key] = m
    return m


def _piece(kind, r, width, color, flip):
    """A corner already colored. kind: 'q' quarter. flip = (flip_x, flip_y)."""
    key = (r, width, tuple(color), flip)
    s = _colored.get(key)
    if s is None:
        if len(_colored) > 3000:
            _colored.clear()
        s = _quarter(r, width).copy()
        a = color[3] if len(color) > 3 else 255
        s.fill((color[0], color[1], color[2], a), special_flags=pygame.BLEND_RGBA_MULT)
        if flip[0] or flip[1]:
            s = pygame.transform.flip(s, flip[0], flip[1])
        _colored[key] = s
    return s


def _radii(border_radius, tl, tr, bl, br, w, h):
    base = max(0, border_radius)
    out = [base if v < 0 else v for v in (tl, tr, bl, br)]
    cap = max(0, min(w, h) // 2)
    return [max(0, min(v, cap)) for v in out]


def rect(surf, color, rect, width=0, border_radius=-1, border_top_left_radius=-1, border_top_right_radius=-1,
         border_bottom_left_radius=-1, border_bottom_right_radius=-1):
    """pygame.draw.rect with anti-aliased rounded corners (same arguments)."""
    r = pygame.Rect(rect)
    if r.w <= 0 or r.h <= 0:
        return r
    tl, tr, bl, br = _radii(border_radius, border_top_left_radius, border_top_right_radius, border_bottom_left_radius, border_bottom_right_radius, r.w, r.h)
    if not (tl or tr or bl or br):
        return pygame.draw.rect(surf, color, r, width)
    x0, y0, x1, y1 = r.left, r.top, r.right, r.bottom
    d = pygame.draw.rect
    if width <= 0:
        top, bot = max(tl, tr), max(bl, br)
        d(surf, color, (x0, y0 + top, r.w, r.h - top - bot))                        # the middle, full width
        if top:
            d(surf, color, (x0 + tl, y0, r.w - tl - tr, top))                       # the top band between the corners
            if top > tl:
                d(surf, color, (x0, y0 + tl, tl, top - tl))
            if top > tr:
                d(surf, color, (x1 - tr, y0 + tr, tr, top - tr))
        else:
            d(surf, color, (x0, y0, r.w, 0))
        if bot:
            d(surf, color, (x0 + bl, y1 - bot, r.w - bl - br, bot))
            if bot > bl:
                d(surf, color, (x0, y1 - bot, bl, bot - bl))
            if bot > br:
                d(surf, color, (x1 - br, y1 - bot, br, bot - br))
        for (cr, px, py, fl) in ((tl, x0, y0, (False, False)), (tr, x1 - tr, y0, (True, False)), (bl, x0, y1 - bl, (False, True)), (br, x1 - br, y1 - br, (True, True))):
            if cr:
                surf.blit(_piece("q", cr, 0, color, fl), (px, py))
        return r
    # outline: straight edges as plain rectangles, corners as AA rings
    w_ = min(width, r.w // 2, r.h // 2)
    d(surf, color, (x0 + tl, y0, r.w - tl - tr, w_))
    d(surf, color, (x0 + bl, y1 - w_, r.w - bl - br, w_))
    d(surf, color, (x0, y0 + tl, w_, r.h - tl - bl))
    d(surf, color, (x1 - w_, y0 + tr, w_, r.h - tr - br))
    for (cr, px, py, fl) in ((tl, x0, y0, (False, False)), (tr, x1 - tr, y0, (True, False)), (bl, x0, y1 - bl, (False, True)), (br, x1 - br, y1 - br, (True, True))):
        if cr:
            surf.blit(_piece("q", cr, w_, color, fl), (px, py))
        else:
            ox = px if fl[0] is False else px - w_ + 1
            oy = py if fl[1] is False else py - w_ + 1
            d(surf, color, (px if not fl[0] else px - w_, py if not fl[1] else py - w_, w_, w_))
    return r


_circles = {}


def circle(surf, color, center, radius, width=0, *args, **kw):
    """pygame.draw.circle with an anti-aliased edge (full circles only; the `draw_*` quadrant arguments are ignored)."""
    radius = int(round(radius))
    if radius <= 0:
        return pygame.Rect(center[0], center[1], 0, 0)
    key = (radius, width, tuple(color))
    s = _circles.get(key)
    if s is None:
        if len(_circles) > 800:
            _circles.clear()
        n = radius * 2 + 2
        big = pygame.Surface((n * _SS, n * _SS), pygame.SRCALPHA)
        c = (n * _SS) // 2
        pygame.draw.circle(big, (255, 255, 255, 255), (c, c), radius * _SS)
        if 0 < width < radius:
            pygame.draw.circle(big, (0, 0, 0, 0), (c, c), (radius - width) * _SS)
        s = pygame.transform.smoothscale(big, (n, n))
        a = color[3] if len(color) > 3 else 255
        s.fill((color[0], color[1], color[2], a), special_flags=pygame.BLEND_RGBA_MULT)
        _circles[key] = s
    surf.blit(s, (int(center[0]) - radius - 1, int(center[1]) - radius - 1))
    return pygame.Rect(int(center[0]) - radius, int(center[1]) - radius, radius * 2, radius * 2)


def line(surf, color, a, b, width=1):
    """A line with the plain pygame call (kept here so screens only talk to `ui`)."""
    return pygame.draw.line(surf, color, a, b, width)
