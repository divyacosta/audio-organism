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
    if cur.get("scene_bg", 0) == 1:                                      # the scene asks for a black room
        params["bg"] = (0.0, 0.0, 0.0)
    params["complexity"] = min(params["complexity"], max(0.30, detail / 100.0))        # panel density cap
    params["blank"] = cur.get("scene_visual", 1) == 0
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
