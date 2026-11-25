"""Scene presets: what a scene is, the six that come with the program, and how a scene moves between the settings and its stored copy.

A scene is a dict. Its keys are the SAME names the settings use (cfg), so selecting a scene is "copy these keys into cfg" and editing is
"copy the changed key back". A scene holds:

  identity      scene_name, scene_auto (the Auto mode may pick it), scene_genre (the genre that calls for it: techno, trance, edm, pop or "")
  mandala       m_base (the character: 0 Facetas, 1 Túnel, 2 Catedral, 3 Impacto, 4 Palco, 5 Estrela: it keeps the colour family and the few
                tone details that are not numbers), m_psx m_psy (half size of a panel, % of the unit), m_pox m_poy (offset between layers),
                m_decay (size kept by each layer, %), m_thick (panel thickness, % of the character's own), m_funnel (smallest funnel, %),
                m_cuts (how often colours and universes are cut, %), m_round (0 straight, 1 alternate rounded, 2 all rounded),
                m_glass (opacity of the faces, %: 100 solid, 40 stained glass), m_sym0..m_sym7 (which kaleidoscope cuts may be used)
  shader        scene_shader (0 = automatic by the part of the music, k = the k-th shader preset, see shaderpresets.py), scene_pref (the kind of shader
                the automatic mode favours)
  preset        scene_preset (index of the mandala preset the numbers came from, see PRESET_NAMES; the numbers are then the scene's own to change)
  visual        scene_visual (0 = Nenhum: a black screen, 1 = Mandala: the Facetas engine, 2.. = a generator: see VISUALS), gen_p1..3 (its three settings, %), gen_text, gen_img (the Logo), scene_bg (the room behind: 0 = the style's own / the palette's, 1 = black, 2 = white, 3 = the colour scene_bgr/g/b)
  background    bg_light, bg_int, bg_speed, bg_col (see BG_KEYS)
  reaction      react, strobe, bursts, bloom (see REACT_KEYS)
  colours       scene_palette (0 = the character's own colours, 1.. = an entry of the palette list, see palettes.py)
  camera        camera, cam_*            movement      movement, mv_*, ctrans            shapes     sh_*
"""

import copy

import layers as LY

SYM_COUNT = 8
SYM_LABELS = ["Espelho 4x", "Espelho lateral", "Radial 6", "Radial 8", "Radial 5", "Diagonal", "Espelho vertical", "Radial 12"]
BASE_NAMES = ["Facetas", "Túnel", "Catedral", "Impacto", "Palco", "Estrela"]       # index = m_base ... see BASE_PROF
BASE_PROF = [0, 1, 2, 3, 4, 5]                                                    # m_base -> profile id of the engine (the same numbers)

# keys that travel with a scene (besides the mandala ones, which are listed here too)
MANDALA_KEYS = ("m_base", "m_psx", "m_psy", "m_pox", "m_poy", "m_decay", "m_thick", "m_funnel", "m_cuts", "m_round", "m_glass") + tuple("m_sym%d" % i for i in range(SYM_COUNT)) + ("m_symnone",)
IDENTITY_KEYS = ("scene_name", "scene_auto", "scene_weight", "scene_genre", "scene_shader", "scene_pref", "scene_palette", "scene_visual", "scene_bg", "scene_preset",
                 "gen_p1", "gen_p2", "gen_p3", "gen_text", "gen_img", "scene_bgr", "scene_bgg", "scene_bgb")
CAMERA_KEYS = ("camera", "cam_orbit", "cam_roll", "cam_shake", "cam_punch", "cam_funnel", "cam_fov_min", "cam_fov_max", "cam_fov_var", "cam_sync")
MOVEMENT_KEYS = ("movement", "mv_speed", "mv_rot", "mv_dir", "mv_pulse", "mv_one", "mv_cuts", "mv_inertia", "ctrans", "lay_trans", "scene_fade")
SHAPE_KEYS = tuple("sh_%d" % i for i in range(19)) + ("sh_when", "sh_mix", "sh_morph")
REACT_KEYS = ("react", "react_bass", "react_mid", "react_high", "expo", "strobe", "bursts", "bloom", "fl_mode", "fl_drop", "fl_roll", "fl_len", "fl_start")            # how the picture answers the music: reactivity, flashes, quarter-beat bursts, glow
AUTO_KEYS = ("auto_cam_orbit", "auto_cam_roll", "auto_cam_shake", "auto_cam_punch", "auto_cam_funnel", "auto_cam_fov", "auto_cam_sync", "auto_mv_speed", "auto_mv_rot", "auto_mv_pulse", "auto_mv_cuts", "auto_mv_inertia", "auto_cuts", "auto_vars", "auto_shape")        # what the automatic modes may change (each scene decides)
BG_KEYS = ("bg_light", "bg_int", "bg_speed", "bg_col", "bgc_src", "bgc_dir", "bgc_react", "bgc_trans", "bgc_every", "bgc_cols")                  # the background lights: style (0 none, 1 aurora, 2 beams, 3 pulses), intensity %, speed %
BG_KEYS = BG_KEYS + ("layers",)                  # the stack of effects and backgrounds of the scene (see layers.py); the keys before it are the ones of scenes older than the layers
LAYER_ON_KEYS = ("ly_bg", "ly_lights", "ly_form", "ly_parts", "ly_finish", "ly_over")            # the six layers of a scene, each one on or off (see layers.SLOTS)
ACAB_KEYS = ("img_style", "img_pix", "fin_bright", "fin_contrast", "fin_sat", "fin_gamma", "fin_temp", "fin_dither", "scr_vig")     # the Acabamento: the last look of the picture, the scene's own
OVER_KEYS = ("ov_kind", "ov_text", "ov_pos", "ov_size", "ov_op", "ov_react")                         # the Sobreposição: a text or the logo over everything
MUSIC_KEYS = ("mods", "cycles")                                                                          # what follows the music (see mods.py)
SCENE_KEYS = IDENTITY_KEYS + MANDALA_KEYS + CAMERA_KEYS + MOVEMENT_KEYS + SHAPE_KEYS + REACT_KEYS + BG_KEYS + AUTO_KEYS + LAYER_ON_KEYS + ACAB_KEYS + OVER_KEYS + MUSIC_KEYS
EXTRA_KEYS = CAMERA_KEYS + MOVEMENT_KEYS + SHAPE_KEYS + REACT_KEYS + BG_KEYS + AUTO_KEYS + LAYER_ON_KEYS + ACAB_KEYS + OVER_KEYS     # what a new scene takes from the settings
LAYER_DEFAULTS = dict(ly_bg=True, ly_lights=True, ly_form=True, ly_parts=True, ly_finish=True, ly_over=False,
                      img_style=0, img_pix=6, fin_bright=100, fin_contrast=100, fin_sat=100, fin_gamma=100, fin_temp=2, fin_dither=False, scr_vig=0,
                      ov_kind=0, ov_text="Seu nome", ov_pos=0, ov_size=10, ov_op=90, ov_react=0, mods={}, cycles={})

# the six that ship: (name, base, psx, psy, pox, poy, decay, funnel, cuts, round, glass, symmetries, genre, preferred shader)
_STARTERS = [
    ("Facetas",  0, 52, 34, 70, 38, 84,  0, 100, 0,  20, (0, 1, 6),             "",       1),
    ("Estrela",  5, 92,  5, 50, 26, 88, 35, 100, 2, 100, (4, 2, 3, 5),          "",       2),
    ("Túnel",    1, 95,  8, 42, 22, 89, 55,  35, 0, 100, (3, 2, 4),             "techno", 3),
    ("Catedral", 2, 62, 30, 55, 30, 86, 15,  50, 0,  40, (3, 7),                "trance", 1),
    ("Impacto",  3, 50, 40, 75, 42, 82, 10, 170, 0, 100, (0, 5, 2),             "edm",    1),
    ("Palco",    4, 46, 33, 66, 36, 85,  0,  80, 1, 100, (1, 6, 5),             "pop",    1),
]


def blank_extras():
    """Camera, movement and shape keys of a scene that changes nothing (the defaults of the settings)."""
    d = {"camera": 0, "cam_orbit": 0, "cam_roll": 0, "cam_shake": 0, "cam_punch": 0, "cam_funnel": 2, "cam_fov_min": 90, "cam_fov_max": 90,
         "cam_fov_var": 0, "cam_sync": 0, "movement": 0, "mv_speed": 1, "mv_rot": 2, "mv_dir": 0, "mv_pulse": 0, "mv_one": False,
         "mv_cuts": 1, "mv_inertia": 1, "ctrans": 0, "lay_trans": 2, "scene_fade": 1, "sh_when": 0, "sh_mix": 0, "sh_morph": 2,
         "react": 100, "react_bass": 100, "react_mid": 100, "react_high": 100, "expo": 100, "strobe": 2, "bursts": True, "bloom": 60, "fl_mode": 0, "fl_drop": 2, "fl_roll": True, "fl_len": 1, "fl_start": 1, "bg_light": 0, "bg_int": 100, "bg_speed": 100, "bg_col": 0, "bgc_src": 0, "bgc_dir": 0, "bgc_react": 0, "bgc_trans": 2, "bgc_every": 1,
         "bgc_cols": [[10, 0, 40], [235, 8, 56], [0, 79, 236]], "auto_cam_orbit": True, "auto_cam_roll": True, "auto_cam_shake": True, "auto_cam_punch": True, "auto_cam_funnel": True, "auto_cam_fov": True, "auto_cam_sync": True, "auto_mv_speed": True, "auto_mv_rot": True, "auto_mv_pulse": True, "auto_mv_cuts": True, "auto_mv_inertia": True, "auto_cuts": True, "auto_vars": True, "auto_shape": True,
         "layers": [], "gen_p1": 50, "gen_p2": 50, "gen_p3": 50, "gen_text": "Seu nome", "gen_img": "", "scene_bgr": 20, "scene_bgg": 20, "scene_bgb": 40}
    d.update(copy.deepcopy(LAYER_DEFAULTS))
    for i in range(19):
        d["sh_%d" % i] = (i == 0)
    return d


# the visuals a scene can have: (name, what it is, what its three sliders are, ready-made scene: name, p1, p2, p3, genre, layers)
VISUALS = [
    ("Nenhum", "Só uma tela preta", ()),
    ("Mandala", "O motor de facetas, com os números abaixo", ()),
    ("Túnel", "Voo por um túnel de anéis e painéis que pulsa no bumbo", (("Lados", "Quantos painéis em volta"), ("Velocidade", "Quão rápido o túnel passa"), ("Giro", "Para onde e quanto o túnel gira"))),
    ("Espectro", "Barras que sobem com o som, sobre um piso espelhado", (("Barras", "Quantas barras"), ("Altura", "Quanto as barras sobem"), ("Espelhar", "Acima de 50%, as barras abrem do centro para os lados"))),
    ("Fractal", "Um fractal (conjunto de Julia) que respira com a música", (("Detalhe", "Mais detalhe pesa mais"), ("Zoom", "Quão perto"), ("Variação", "Quanto o desenho muda sozinho"))),
    ("Grade neon", "Sol, montanhas e uma grade até o horizonte (synthwave)", (("Velocidade", "Quão rápido a grade avança"), ("Sol", "Tamanho do sol"), ("Montanhas", "Altura das montanhas"))),
    ("Fluido", "Bolhas que se fundem e se separam com o som", (("Bolhas", "Quantas bolhas"), ("Tamanho", "Tamanho de cada bolha"), ("Velocidade", "Quão rápido elas se movem"))),
    ("Galáxia", "Braços em espiral, núcleo brilhante e estrelas", (("Braços", "Quantos braços da espiral"), ("Estrelas", "Quantidade de estrelas"), ("Giro", "Quão rápido a galáxia gira"))),
    ("Osciloscópio", "O som desenhado como uma linha de laser", (("Forma", "Linha, anel ou duas linhas"), ("Espessura", "Quão grossa é a linha"), ("Ganho", "Quanto a linha balança"))),
    ("Logo / texto", "Seu nome, texto ou imagem no meio, pulsando com a música", (("Tamanho", "Tamanho na tela"), ("Pulso", "Quanto pulsa com a batida"), ("Cor", "0% mantém as cores da imagem; 100% usa as cores da paleta"))),
    ("Acelerador", "Um feixe de luz que se abre em milhares de fios", (("Fios", "Quantos fios no leque"), ("Curva", "Quanto os fios se curvam"), ("Velocidade", "Quão rápido a luz corre nos fios"))),
]
GEN_DEFAULTS = {"gen_p1": 50, "gen_p2": 50, "gen_p3": 50, "gen_text": "Seu nome", "gen_img": "", "scene_bgr": 20, "scene_bgg": 20, "scene_bgb": 40}
GEN_SCENES = [                       # the ready-made scenes of the generators: (visual, name, p1, p2, p3, genre)
    (2, "Vórtice", 55, 55, 50, "techno"), (3, "Espectro", 60, 60, 0, ""), (4, "Fractal", 60, 50, 50, "trance"), (5, "Synthwave", 45, 45, 55, "pop"),
    (6, "Fluido", 55, 50, 40, ""), (7, "Galáxia", 40, 50, 45, "trance"), (8, "Laser", 0, 20, 55, "edm"), (9, "Logo", 45, 50, 0, ""),
    (10, "Acelerador", 50, 40, 50, "edm"),
]

SYMNONE = {0}                                                  # Facetas ships with "Nenhum" on, as the author left it
PRESET_NAMES = [t[0] for t in _STARTERS]                      # the mandala presets: Facetas, Estrela, Túnel, Catedral, Impacto, Palco


def preset_values(i):
    """The geometry numbers of mandala preset i (what a preset carries: no colours, shader, camera or movement)."""
    name, base, psx, psy, pox, poy, decay, funnel, cuts, rnd, glass, syms, genre, pref = _STARTERS[i]
    d = dict(m_base=base, m_psx=psx, m_psy=psy, m_pox=pox, m_poy=poy, m_decay=decay, m_thick=100, m_funnel=funnel, m_cuts=cuts,
             m_round=rnd, m_glass=glass, scene_preset=i)
    for k in range(SYM_COUNT):
        d["m_sym%d" % k] = k in syms
    d["m_symnone"] = i in SYMNONE                                     # presets that ship with "Nenhum" on (no mirror drawn)
    return d


def apply_preset(target, i):
    """Copy mandala preset i into a scene or into the settings."""
    target.update(preset_values(i))


def preset_of(scene):
    """Which preset a stored scene came from: its own mark, else the one with the same name or the same base."""
    i = scene.get("scene_preset")
    if isinstance(i, int) and 0 <= i < len(_STARTERS):
        return i
    for k, t in enumerate(_STARTERS):
        if t[0] == scene.get("scene_name"):
            return k
    for k, t in enumerate(_STARTERS):
        if t[1] == scene.get("m_base"):
            return k
    return 0


def mandala_scene(i=0, extras=None, name="Mandala"):
    """A scene whose visual is a mandala, with preset i. `extras` (camera / movement / shape keys) is copied into it, so nothing changes for
    someone who already had settings; without it the scene starts with the plain defaults."""
    s = copy.deepcopy(dict(extras or blank_extras()))
    for k, v in GEN_DEFAULTS.items():
        s.setdefault(k, v)
    for k, v in LAYER_DEFAULTS.items():
        s.setdefault(k, copy.deepcopy(v))
    s.update(scene_name=name, scene_auto=True, scene_weight=1, scene_genre="", scene_shader=0, scene_pref=_STARTERS[i][13], scene_palette=0, scene_visual=1, scene_bg=0)
    s.update(preset_values(i))
    return s


def none_scene(extras=None):
    """The scene with nothing drawn: a black screen (it keeps the Facetas numbers, so switching its visual to Mandala works at once)."""
    s = mandala_scene(0, extras)
    s.update(scene_name="Nenhum", scene_auto=False, scene_genre="", scene_visual=0)
    return s


def preset_templates():
    """The scenes of the second step of "Nova cena" > Mandala: one per mandala preset."""
    return [mandala_scene(i, name=PRESET_NAMES[i]) for i in range(len(_STARTERS))]


def preset_layers(i):
    """The stack of layers that gives each mandala preset its own look when it comes as a ready-made scene."""
    t = LY.new_layer
    if i == 0:                                                       # Facetas: aurora behind, a little aberration on the kick
        return [dict(t("lights"), style=1, amt=60), dict(t("ca"), amt=15, src=1, famt=60)]
    if i == 1:                                                       # Estrela: a cloud of particles, a trail that changes colour and a soft flare
        return [dict(t("part"), count=2, pmode=0), dict(t("fb"), amt=55, hue=3), dict(t("fl"), amt=30)]
    if i == 2:                                                       # Túnel: the trail pulls into the centre, aberration and fine grain
        return [dict(t("fb"), amt=70, zoom=4, rot=2), dict(t("ca"), amt=25), dict(t("gr"), amt=20, size=2, fps=1)]
    if i == 3:                                                       # Catedral: stars behind, a long blue flare and a filmic tone
        return [dict(t("lights"), style=4, amt=80), dict(t("fl"), amt=45, len=160), dict(t("tone"), mode=1)]
    if i == 4:                                                       # Impacto: aberration that hits with the kick, grain and dark corners
        return [dict(t("edge"), amt=25), dict(t("ca"), amt=40, src=1, famt=80), dict(t("gr"), amt=35)]
    return [dict(t("grad"), gtype=2, amt=80, greact=40), dict(t("lights"), style=2, amt=70), dict(t("fl"), amt=40, col=1)]       # Palco: radial gradient, beams and a warm flare


def preset_scene(i, extras=None):
    """The ready-made scene of mandala preset i: its numbers, its name and its stack of layers."""
    s = mandala_scene(i, extras, name=PRESET_NAMES[i])
    s["layers"] = preset_layers(i)
    return s


def generator_scene(g, extras=None):
    """The ready-made scene of generator g (an entry of GEN_SCENES)."""
    vis, name, p1, p2, p3, genre = g
    s = mandala_scene(0, extras, name=name)
    s.update(scene_visual=vis, gen_p1=p1, gen_p2=p2, gen_p3=p3, scene_genre=genre)
    t = LY.new_layer
    s["layers"] = {2: [dict(t("fb"), amt=40, zoom=3), dict(t("ca"), amt=20, src=1, famt=70)], 3: [dict(t("fl"), amt=30)], 4: [dict(t("tone"), mode=1)],
                   5: [dict(t("gr"), amt=18, size=2, fps=1), dict(t("fl"), amt=35, col=1)], 6: [dict(t("tone"), mode=2)], 7: [dict(t("fl"), amt=30)],
                   8: [dict(t("fb"), amt=60, zoom=0, rot=0), dict(t("ca"), amt=15)], 9: [dict(t("fl"), amt=25)], 10: [dict(t("fl"), amt=30)]}.get(vis, [])
    return s


def starter_scenes(extras=None):
    """What a new installation starts with: the six mandala presets as scenes, each with its own look, the generators and Nenhum."""
    return [preset_scene(i, extras) for i in range(len(_STARTERS))] + [generator_scene(g, extras) for g in GEN_SCENES] + [none_scene(extras)]


def add_missing_generators(scenes, extras=None):
    """For settings of before the generators: the ready-made scenes of the generators are added (before Nenhum, when it is the last one)."""
    have = {s.get("scene_name") for s in scenes}
    at = len(scenes) - 1 if scenes and scenes[-1].get("scene_visual", 1) == 0 else len(scenes)
    n = 0
    for g in GEN_SCENES:
        if g[1] in have:
            continue
        scenes.insert(at, generator_scene(g, extras))
        at += 1
        n += 1
    return n


def add_missing_starters(scenes, extras=None):
    """For settings of before the presets came as scenes: the presets that are not there yet are added (the scenes of the person stay as they are).
    A scene of the Facetas character already counts as the first one. Returns how many were added."""
    have = {s.get("scene_name") for s in scenes}
    added = 0
    at = len(scenes) - 1 if scenes and scenes[-1].get("scene_visual", 1) == 0 else len(scenes)          # before the scene with nothing, when it is the last
    for i in range(len(_STARTERS)):
        if PRESET_NAMES[i] in have or (i == 0 and (have & {"Mandala", "Facetas"})):
            continue
        scenes.insert(at, preset_scene(i, extras))
        at += 1
        added += 1
    return added


def blank_scene(extras=None, name="Nova cena"):
    """The scene of "Nova cena": a mandala with no layers, to be built in the editor of layers."""
    s = mandala_scene(0, extras, name=name)
    s["layers"] = []
    return s


def templates():
    """The scenes the "Nova cena" picker offers: Nenhum and Mandala (the presets of the mandala are chosen inside the scene)."""
    return [mandala_scene(0), none_scene()]


def wizard_bases(extras=None):
    """The looks the three steps of "Nova cena" start from: the ready-made scenes (the six mandalas and the generators), not the black screen."""
    return [s for s in starter_scenes(extras) if s.get("scene_visual", 1) != 0]


def valid(scene):
    return isinstance(scene, dict) and all(k in scene for k in ("scene_name", "m_base", "m_psx", "m_decay"))


def apply_scene(cfg, scene):
    """Copy a scene's keys into the settings (selecting it)."""
    for k in SCENE_KEYS:
        if k in scene:
            cfg[k] = copy.deepcopy(scene[k]) if isinstance(scene[k], (list, dict)) else scene[k]
    cfg["ly_sel"] = min(int(cfg.get("ly_sel", 0)), max(0, len(cfg.get("layers") or []) - 1))
    LY.load_lp(cfg)                                           # the layer being edited goes into the working keys of the editor


def store_scene(cfg, scene):
    """Copy the settings' scene keys back into the stored scene (editing it)."""
    for k in SCENE_KEYS:
        if k in cfg:
            scene[k] = copy.deepcopy(cfg[k]) if isinstance(cfg[k], (list, dict)) else cfg[k]


def summary(scene):
    """One line about what a scene is made of, for the list."""
    v = int(scene.get("scene_visual", 1))
    if v == 0:
        return "Nenhum · tela preta"
    if v >= 2:
        return VISUALS[min(v, len(VISUALS) - 1)][0]
    return "Mandala · " + PRESET_NAMES[preset_of(scene)]
