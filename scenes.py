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
  visual        scene_visual (0 = Nenhum: a black screen, 1 = Mandala: the Facetas engine), scene_bg (0 = background from the palette, 1 = black)
  background    bg_light, bg_int, bg_speed (see BG_KEYS)
  reaction      react, strobe, bursts, bloom (see REACT_KEYS)
  colours       scene_palette (0 = the character's own colours, 1.. = an entry of the palette list, see palettes.py)
  camera        camera, cam_*            movement      movement, mv_*, ctrans            shapes     sh_*
"""

SYM_COUNT = 8
SYM_LABELS = ["Espelho 4x", "Espelho lateral", "Radial 6", "Radial 8", "Radial 5", "Diagonal", "Espelho vertical", "Radial 12"]
BASE_NAMES = ["Facetas", "Túnel", "Catedral", "Impacto", "Palco", "Estrela"]       # index = m_base ... see BASE_PROF
BASE_PROF = [0, 1, 2, 3, 4, 5]                                                    # m_base -> profile id of the engine (the same numbers)

# keys that travel with a scene (besides the mandala ones, which are listed here too)
MANDALA_KEYS = ("m_base", "m_psx", "m_psy", "m_pox", "m_poy", "m_decay", "m_thick", "m_funnel", "m_cuts", "m_round", "m_glass") + tuple("m_sym%d" % i for i in range(SYM_COUNT))
IDENTITY_KEYS = ("scene_name", "scene_auto", "scene_genre", "scene_shader", "scene_pref", "scene_palette", "scene_visual", "scene_bg", "scene_preset")
CAMERA_KEYS = ("camera", "cam_orbit", "cam_roll", "cam_shake", "cam_punch", "cam_funnel", "cam_fov_min", "cam_fov_max", "cam_fov_var", "cam_sync")
MOVEMENT_KEYS = ("movement", "mv_speed", "mv_rot", "mv_dir", "mv_pulse", "mv_one", "mv_cuts", "mv_inertia", "ctrans")
SHAPE_KEYS = tuple("sh_%d" % i for i in range(19)) + ("sh_when", "sh_mix", "sh_morph")
REACT_KEYS = ("react", "strobe", "bursts", "bloom")            # how the picture answers the music: reactivity, flashes, quarter-beat bursts, glow
BG_KEYS = ("bg_light", "bg_int", "bg_speed")                  # the background lights: style (0 none, 1 aurora, 2 beams, 3 pulses), intensity %, speed %
SCENE_KEYS = IDENTITY_KEYS + MANDALA_KEYS + CAMERA_KEYS + MOVEMENT_KEYS + SHAPE_KEYS + REACT_KEYS + BG_KEYS

# the six that ship: (name, base, psx, psy, pox, poy, decay, funnel, cuts, round, glass, symmetries, genre, preferred shader)
_STARTERS = [
    ("Facetas",  0, 52, 34, 70, 38, 84,  0, 100, 0, 100, (0, 1, 2, 3, 4, 5, 6), "",       1),
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
         "mv_cuts": 1, "mv_inertia": 1, "ctrans": 0, "sh_when": 0, "sh_mix": 0, "sh_morph": 2,
         "react": 100, "strobe": 2, "bursts": True, "bloom": 60, "bg_light": 0, "bg_int": 100, "bg_speed": 100}
    for i in range(19):
        d["sh_%d" % i] = (i == 0)
    return d


PRESET_NAMES = [t[0] for t in _STARTERS]                      # the mandala presets: Facetas, Estrela, Túnel, Catedral, Impacto, Palco


def preset_values(i):
    """The geometry numbers of mandala preset i (what a preset carries: no colours, shader, camera or movement)."""
    name, base, psx, psy, pox, poy, decay, funnel, cuts, rnd, glass, syms, genre, pref = _STARTERS[i]
    d = dict(m_base=base, m_psx=psx, m_psy=psy, m_pox=pox, m_poy=poy, m_decay=decay, m_thick=100, m_funnel=funnel, m_cuts=cuts,
             m_round=rnd, m_glass=glass, scene_preset=i)
    for k in range(SYM_COUNT):
        d["m_sym%d" % k] = k in syms
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
    s = dict(extras or blank_extras())
    s.update(scene_name=name, scene_auto=True, scene_genre="", scene_shader=0, scene_pref=_STARTERS[i][13], scene_palette=0, scene_visual=1, scene_bg=0)
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


def starter_scenes(extras=None):
    """What a new installation starts with: Facetas and Nenhum."""
    return [mandala_scene(0, extras), none_scene(extras)]


def templates():
    """The scenes the "Nova cena" picker offers: Nenhum and Mandala (the presets of the mandala are chosen inside the scene)."""
    return [mandala_scene(0), none_scene()]


def valid(scene):
    return isinstance(scene, dict) and all(k in scene for k in ("scene_name", "m_base", "m_psx", "m_decay"))


def apply_scene(cfg, scene):
    """Copy a scene's keys into the settings (selecting it)."""
    for k in SCENE_KEYS:
        if k in scene:
            cfg[k] = scene[k]


def store_scene(cfg, scene):
    """Copy the settings' scene keys back into the stored scene (editing it)."""
    for k in SCENE_KEYS:
        if k in cfg:
            scene[k] = cfg[k]


def summary(scene):
    """One line about what a scene is made of, for the list."""
    if scene.get("scene_visual", 1) == 0:
        return "Nenhum · tela preta"
    return "Mandala · " + PRESET_NAMES[preset_of(scene)]
