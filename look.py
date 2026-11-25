"""What turns the director's parameters into a picture: the shader kind, the room colour, the black screen of the scene "Nenhum".
Used by the main window and by the live thumbnails of the scene gallery, so both look the same."""

KIND_TO_STYLE = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}


def apply(rend, params, cur, detail=100):
    """Set the renderer's look from `params` (the director's output) and the scene `cur` that is on screen."""
    eff = params.get("style_id", 1)                                     # the kind of the shader on screen (the scene's own or the automatic pick)
    rend.style = KIND_TO_STYLE.get(eff, 0)
    rend.duo = (eff == 7)
    if eff in (2, 5):                                                    # neon and chrome only read on a dark room: the background stays black
        params["bg"] = (0.0, 0.0, 0.0)
    if eff == 4:                                                         # raio X: a deep blue-black room
        params["bg"] = (0.0, 0.01, 0.025)
    if eff == 6:                                                         # aquarela: the background is paper
        params["bg"] = (0.97, 0.95, 0.91)
    sb = int(cur.get("scene_bg", 0))                                     # the room the scene asks for: 0 the style's own, 1 black, 2 white, 3 a colour of its own
    if sb == 1:
        params["bg"] = (0.0, 0.0, 0.0)
    elif sb == 2:
        params["bg"] = (0.97, 0.97, 0.97)
    elif sb == 3:
        params["bg"] = (cur.get("scene_bgr", 20) / 255.0, cur.get("scene_bgg", 20) / 255.0, cur.get("scene_bgb", 40) / 255.0)
    params["complexity"] = min(params["complexity"], max(0.30, detail / 100.0))        # panel density cap
    vis = int(cur.get("scene_visual", 1)) if cur.get("ly_form", True) else 0         # the Forma principal turned off: nothing in the middle (the scene keeps its visual)
    params["blank"] = vis == 0
    params["visual"] = vis if vis >= 2 else 0                              # a visual other than the Mandala (see generators.wgsl)
    if vis >= 2:
        ups, tiers = params.get("upals"), params.get("tier_uni") or (0, 1, 2)
        if ups:                                                          # the colours of the generators are the ones of the palette in use (the scene's own or the Palco's)
            u = sorted((tuple(c) for c in ups[tiers[0] % len(ups)]), key=lambda c: -(0.30 * c[0] + 0.59 * c[1] + 0.11 * c[2]))     # the two brightest: a generator on dark colours would be invisible
            params["pal"] = (u[0], u[1])
        rend.duo = False                                                 # the duotone (a way to shade the faces of the mandala) would turn a generator into two flat colours
        if sb < 2:
            params["bg"] = (0.0, 0.0, 0.0)                               # it fills the screen by itself: no room colour behind it unless the scene asks for one
    params["gen_p"] = (cur.get("gen_p1", 50), cur.get("gen_p2", 50), cur.get("gen_p3", 50))
    if vis == 9:
        import logo
        rend.set_logo(*logo.make(cur.get("gen_text", ""), cur.get("gen_img", "")))
    overlay(rend, cur)
    if params["blank"]:                                                  # "Nenhum": nothing is drawn, the cheapest black picture
        params["bg"] = (0.0, 0.0, 0.0)
        params["fade"] = 0.0
        params["gain"] = 0.0
        rend.duo = False
        rend.steps = 8
        rend.res = 25
        rend.bloom = 0.0
        rend.flash = 0.0
    return params


def overlay(rend, cur):
    """The Sobreposição of the scene: a text, or the logo (logo.png in Documentos\\AudioOrganism), laid over the finished picture."""
    on = bool(cur.get("ly_over", False))
    rend.ov_on = on
    if not on:
        return
    import logo
    if int(cur.get("ov_kind", 0)) == 1:
        rend.set_overlay(*logo.make("", ""))
    else:
        rend.set_overlay(*logo.make(str(cur.get("ov_text", "")) or " ", ""))
    rend.ov = (int(cur.get("ov_pos", 0)), float(cur.get("ov_size", 10)), float(cur.get("ov_op", 90)) / 100.0, int(cur.get("ov_react", 0)))


def audio(params, an):
    """What the generators need of the sound besides the bands of the director: the spectrum in 32 bands, 64 samples of the wave, the energy and the tension."""
    import numpy as np
    b = np.asarray(an.bands, np.float32)
    n = len(b) // 2 * 2
    b32 = np.power(np.clip(b[:n].reshape(-1, 2).mean(axis=1), 0.0, None), 0.6) * 1.3
    params["bands32"] = np.clip(b32, 0.0, 1.0)
    w = np.asarray(an.buf[-1024:], np.float32)
    if len(w) >= 1024:
        params["wave64"] = np.clip(w[::16] * 4.0, -1.0, 1.0)
    params["energy"] = float(getattr(an, "energy", 0.0))
    params["tension"] = float(getattr(an, "tension", 0.0))
    params["drop"] = float(getattr(an, "drop", 0.0))
