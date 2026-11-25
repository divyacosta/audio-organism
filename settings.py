"""The settings: the defaults, the file on disk (and what an older file needs to be read today), the tables of options, and the pages (cards of rows) that every
tab of the panel is made of. Nothing here draws or holds the state of a window: menu.py draws these pages and edits the settings they describe.

Tests and tools that redirect the files set `settings.PATH` and `settings.PROFILE_DIR`.
"""
import copy
import json
import os
import time

import palettes as PAL
import layers as LY
import scenes as SC
import mods as MOD
import i18n
import shaderpresets as SP

APPDIR = os.environ.get("VIS_APPDIR") or os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AudioOrganism")      # VIS_APPDIR: tests keep their own settings
PATH = os.path.join(APPDIR, "settings.json")

DEFAULTS = {"vsync": False, "fullscreen": False, "strobe": 2, "bursts": True, "bloom": 60, "react": 100,
            "effect": 0, "backend": 0, "style": 8, "style_v": 6, "camera": 0, "cam_orbit": 0, "cam_roll": 0, "cam_shake": 0, "cam_punch": 0, "cam_funnel": 2,
            "cam_fov_min": 90, "cam_fov_max": 90, "cam_fov_var": 0, "cam_sync": 0,
            "mv_speed": 1, "mv_rot": 2, "mv_dir": 0, "mv_pulse": 0, "mv_one": False, "mv_cuts": 1, "mv_inertia": 1, "movement": 0,
            # what the automatic modes may control (aba Auto)
            "auto_cam_orbit": True, "auto_cam_roll": True, "auto_cam_shake": True, "auto_cam_punch": True, "auto_cam_funnel": True,
            "auto_cam_fov": True, "auto_cam_sync": True, "auto_mv_speed": True, "auto_mv_rot": True, "auto_mv_pulse": True, "auto_mv_cuts": True,
            "auto_mv_inertia": True, "auto_cuts": True, "auto_vars": True, "auto_shape": True,
            "sh_when": 0, "sh_mix": 0, "sh_morph": 2, "ctrans": 0, "lay_trans": 2, "scene_fade": 1,
            "sh_0": True, "sh_2": False, "sh_16": False, "sh_1": False, "sh_3": False, "sh_4": False, "sh_15": False, "sh_9": False, "sh_10": False, "sh_14": False, "sh_5": False, "sh_6": False, "sh_7": False, "sh_8": False, "sh_17": False, "sh_11": False, "sh_12": False, "sh_13": False, "sh_18": False,
            # graphics (see PRESETS): render scale %, ray steps, ray-traced shadow / reflection / occlusion quality, lighting mode,
            # bloom levels, edge AA, panel density %, dynamic resolution and its FPS target
            "preset": 1, "res": 80, "steps": 60, "bloomq": 2, "aa_mode": 0, "detail": 75,
            "dynres": True, "fps_out": 60, "mblur": 0, "mblur_fps": 24, "auto_update": True,
            # more performance options: sharpening, bloom resolution, ray distance, render rate, lowest dynamic scale, panel refresh, GPU choice
            "img_style": 0, "img_pix": 6, "fx_glass": True, "fx_bloom": True, "fx_trail": True, "fx_parts": True, "fx_mblur": True, "scr_aspect": 0, "scr_zoom": 100, "scr_mirror": 0, "scr_vig": 0, "fin_bright": 100, "fin_contrast": 100, "fin_sat": 100, "fin_gamma": 100, "fin_temp": 2, "fin_dither": False, "safe_flash": 0, "safe_motion": 0,
            "sharp": 0, "bloomres": 0, "dist": 1, "rrate": 0, "dynmin": 40, "gpu": 0, "panel_view": 2, "abuf": 1024, "adev": "", "monitor": 0, "react_bass": 100, "react_mid": 100, "react_high": 100, "expo": 100, "scene_weight": 1, "fl_mode": 0, "fl_drop": 2, "fl_roll": True, "fl_len": 1, "fl_start": 1}

_S0 = SC.starter_scenes()[0]
DEFAULTS.update({k: _S0[k] for k in SC.MANDALA_KEYS + SC.IDENTITY_KEYS})        # the working copy of the scene being edited (starts as the first)
DEFAULTS.update(mods={}, cycles={}, lang="")                     # lang "": the language of Windows (see i18n.py)
DEFAULTS.update(ly_bg=True, ly_lights=True, ly_form=True, ly_parts=True, ly_finish=True, ly_over=False, ov_kind=0, ov_text="Seu nome", ov_pos=0, ov_size=10, ov_op=90, ov_react=0)
DEFAULTS.update(scene_when=2, scene_every=30, scene_now=False, scene_wait=0, bg_light=0, bg_int=100, bg_speed=100, bg_col=0, bgc_src=0, bgc_dir=0, bgc_react=0, bgc_trans=2, bgc_every=1,
                bgc_cols=[[10, 0, 40], [235, 8, 56], [0, 79, 236]], bgc_item=0, bgc_r=10, bgc_g=0, bgc_b=40)                          # how a scene change happens (see neon_director.update)
DEFAULTS["scene_sec"] = 0                                                         # section of the scene editor (Visual, Fundo, Cores, ...)
DEFAULTS["scenes"] = SC.starter_scenes()                                          # the scene presets (see scenes.py)
DEFAULTS["scene_edit"] = 0                                                        # index of the scene being edited
DEFAULTS["shaders"] = SP.factory()                                              # the shader presets (see shaderpresets.py)
DEFAULTS.update(shd_v=1, shd_edit=0, shd_name="3D", shd_kind=1, shd_p1=100, shd_p2=100, shd_p3=100, shd_auto=True, shd_duo=0, shd_item=0, shd_r=10, shd_g=0, shd_b=40)
DEFAULTS["palettes"] = PAL.factory()                                              # the palette presets (see palettes.py)
DEFAULTS.update(pal_edit=0, pal_item=0, pal_name="Neon", pal_r=0, pal_g=0, pal_b=0)   # the palette / swatch being edited (working copy)

# graphics presets; any manual change of one of these options switches the preset to "Personalizado"
FIN_KEYS = ("img_style", "img_pix", "fx_glass", "fx_bloom", "fx_trail", "fx_parts", "fx_mblur", "scr_aspect", "scr_zoom", "scr_mirror", "scr_vig", "fin_bright", "fin_contrast", "fin_sat", "fin_gamma", "fin_temp", "fin_dither", "safe_flash", "safe_motion")     # the last passes over the finished picture and the comfort limits (Sistema > Imagem); they stay out of the quality presets
GFX_KEYS = ("res", "steps", "bloomq", "aa_mode", "detail", "mblur", "mblur_fps", "sharp", "bloomres", "dist")
PRESETS = [
    ("Baixo",  dict(res=60,  steps=48,  bloomq=1, aa_mode=0, detail=55,  mblur=0, mblur_fps=24, sharp=1, bloomres=1, dist=0)),
    ("Médio",  dict(res=80,  steps=60,  bloomq=2, aa_mode=0, detail=75,  mblur=0, mblur_fps=24, sharp=0, bloomres=0, dist=1)),
    ("Alto",   dict(res=100, steps=72,  bloomq=3, aa_mode=0, detail=100, mblur=0, mblur_fps=24, sharp=0, bloomres=0, dist=1)),
    ("Ultra",  dict(res=100, steps=110, bloomq=4, aa_mode=0, detail=100, mblur=0, mblur_fps=24, sharp=0, bloomres=0, dist=2)),
]
CUSTOM = len(PRESETS)


# camera presets: 0..3 copy their values into the manual controls, 4 = automatic (the director picks one by the music), 5 = manual
CAM_KEYS = ("cam_orbit", "cam_roll", "cam_shake", "cam_punch", "cam_funnel", "cam_fov_min", "cam_fov_max", "cam_fov_var", "cam_sync")
CAM_PRESETS = [
    ("Fixo",      dict(cam_orbit=0, cam_roll=0, cam_shake=0, cam_punch=0, cam_funnel=2, cam_fov_min=90, cam_fov_max=90,  cam_fov_var=0, cam_sync=0)),
    ("Cinema",    dict(cam_orbit=2, cam_roll=0, cam_shake=0, cam_punch=0, cam_funnel=1, cam_fov_min=60, cam_fov_max=80,  cam_fov_var=1, cam_sync=2)),
    ("Clipe",     dict(cam_orbit=1, cam_roll=1, cam_shake=2, cam_punch=2, cam_funnel=3, cam_fov_min=80, cam_fov_max=115, cam_fov_var=2, cam_sync=1)),
    ("Hipnótico", dict(cam_orbit=1, cam_roll=2, cam_shake=0, cam_punch=0, cam_funnel=3, cam_fov_min=85, cam_fov_max=105, cam_fov_var=1, cam_sync=0)),
]
CAM_AUTO, CAM_MANUAL = 4, 5


# movement presets (what moves inside the scene): 0..4 copy their values into the manual controls, 5 = manual
MV_KEYS = ("mv_speed", "mv_rot", "mv_dir", "mv_pulse", "mv_one", "mv_cuts", "mv_inertia")
MV_PRESETS = [
    ("Padrão",       dict(mv_speed=1, mv_rot=2, mv_dir=0, mv_pulse=0, mv_one=False, mv_cuts=1, mv_inertia=1)),
    ("Calmo",        dict(mv_speed=0, mv_rot=1, mv_dir=0, mv_pulse=0, mv_one=False, mv_cuts=0, mv_inertia=2)),
    ("Hipnótico",    dict(mv_speed=1, mv_rot=2, mv_dir=2, mv_pulse=1, mv_one=False, mv_cuts=0, mv_inertia=2)),
    ("Nervoso",      dict(mv_speed=2, mv_rot=3, mv_dir=2, mv_pulse=3, mv_one=False, mv_cuts=2, mv_inertia=0)),
    ("Pela música",  dict(mv_speed=3, mv_rot=2, mv_dir=2, mv_pulse=2, mv_one=True, mv_cuts=1, mv_inertia=1)),
]
MV_AUTO = len(MV_PRESETS)             # the director picks one by the music
MV_MANUAL = MV_AUTO + 1


def _phone_url():
    import stream
    return f"{stream.local_ip()}:{stream.PORT}"

def match_movement(cfg):
    for i, (_, vals) in enumerate(MV_PRESETS):
        if all(cfg.get(k) == v for k, v in vals.items()):
            return i
    return MV_MANUAL


def match_camera(cfg):
    for i, (_, vals) in enumerate(CAM_PRESETS):
        if all(cfg.get(k) == v for k, v in vals.items()):
            return i
    return CAM_MANUAL


def match_preset(cfg):
    for i, (_, vals) in enumerate(PRESETS):
        if all(cfg.get(k) == v for k, v in vals.items()):
            return i
    return CUSTOM


def fresh():
    return copy.deepcopy(DEFAULTS)


def load_palette_edit(cfg):
    """Copy the palette being edited (and its selected swatch) into the working keys of the Cores tab."""
    pal = cfg["palettes"][cfg["pal_edit"]]
    cfg["pal_name"] = pal["name"]
    its = PAL.items(pal)
    cfg["pal_item"] = max(0, min(int(cfg.get("pal_item", 0)), len(its) - 1))
    cfg["pal_r"], cfg["pal_g"], cfg["pal_b"] = its[cfg["pal_item"]][1]


def load_shader_edit(cfg):
    """Copy the shader preset being edited into the working keys of the Shaders tab."""
    sh = cfg["shaders"][cfg["shd_edit"]]
    cfg.update(shd_name=sh["name"], shd_kind=sh["kind"], shd_p1=int(sh["p1"]), shd_p2=int(sh["p2"]), shd_p3=int(sh["p3"]), shd_auto=bool(sh.get("auto", True)),
               shd_duo=int(sh.get("duo_mode", 0)))
    cfg["shd_item"] = max(0, min(int(cfg.get("shd_item", 0)), 1))
    cfg["shd_r"], cfg["shd_g"], cfg["shd_b"] = (sh.get("duo_dark") if cfg["shd_item"] == 0 else sh.get("duo_light")) or [0, 0, 0]


def load_cfg(path=None):
    cfg = fresh()
    data_style_v = 6
    data = {}
    try:
        with open(path or PATH, encoding="utf-8") as f:
            data = json.load(f)
        data_style_v = data.get("style_v", 1) if isinstance(data.get("style_v", 1), int) else 1
        for k, v in data.items():
            if k in cfg and type(v) is type(cfg[k]):
                cfg[k] = v
        if "fps_out" not in data:                                  # older settings had a cap and a target: the output FPS is one number now
            old = data.get("fps_cap") or data.get("fps_target") or 60
            cfg["fps_out"] = min((v for _, v in FPS_OPTS), key=lambda v: abs(v - old))
        cfg["res"] = min(cfg["res"], 100)
        if "aa_mode" not in data and "aa" in data:                 # older settings: the on/off edge switch
            cfg["aa_mode"] = 1 if data["aa"] else 0
        if int(data.get("panel_fps_v", 1)) < 2 and cfg.get("panel_fps") == 0:   # the old default redrew the panel with every frame and halved the output FPS
            cfg["panel_fps"] = 30
        cfg["panel_fps_v"] = 2
    except Exception:
        pass
    # scene presets: the stored list, or the six that ship (with the camera / movement / shapes the person already had)
    extras = {k: cfg[k] for k in SC.EXTRA_KEYS if k in cfg}             # the Acabamento the person had (global before) goes into every scene: nothing changes on screen
    lst = data.get("scenes") if isinstance(data, dict) else None
    if isinstance(lst, list) and lst and all(SC.valid(x) for x in lst):
        base_ = SC.mandala_scene(0, extras)
        for sc_ in lst:
            LY.migrate(sc_)                                                   # effects, gradient and lights of older scenes become layers
            sc_.setdefault("scene_preset", SC.preset_of(sc_))
            for k, v in base_.items():
                sc_.setdefault(k, v)
        if not any(sc_.get("scene_visual", 1) == 0 for sc_ in lst):          # the scene with nothing drawn is always available
            lst.append(SC.none_scene(extras))
        cfg["scenes"] = lst
    else:
        cfg["scenes"] = SC.starter_scenes(extras)
    if isinstance(data, dict) and int(data.get("starter_v", 1)) < 2 and isinstance(lst, list) and lst and all(SC.valid(x) for x in lst):
        SC.add_missing_starters(cfg["scenes"], extras)                             # the presets that were only in the picker come as scenes of the gallery
    if isinstance(data, dict) and int(data.get("starter_v", 1)) < 4 and isinstance(lst, list) and lst and all(SC.valid(x) for x in lst):
        SC.add_missing_generators(cfg["scenes"], extras)                           # the new visuals come as scenes of the gallery, once
    cfg["starter_v"] = 4
    sl = data.get("shaders") if isinstance(data, dict) else None
    cfg["shaders"] = sl if (isinstance(sl, list) and sl and all(SP.valid(x) for x in sl)) else SP.factory()
    for sh_ in cfg["shaders"]:
        for k, v in SP.make(sh_["kind"]).items():
            sh_.setdefault(k, v)
    cfg["shd_edit"] = max(0, min(int(cfg.get("shd_edit", 0)), len(cfg["shaders"]) - 1))
    load_shader_edit(cfg)
    if data.get("shd_v") != 1 if isinstance(data, dict) else True:       # older scenes: 8 meant "automatic", 1..7 a fixed kind (the same order as the presets)
        for sc_ in (cfg["scenes"] if isinstance(cfg.get("scenes"), list) else []):
            if sc_.get("scene_shader") == 8 or sc_.get("scene_shader", 0) > len(cfg["shaders"]):
                sc_["scene_shader"] = 0
    pl = data.get("palettes") if isinstance(data, dict) else None
    cfg["palettes"] = pl if (isinstance(pl, list) and pl and all(PAL.valid(x) for x in pl)) else PAL.factory()
    for p in cfg["palettes"]:
        p["name"] = PAL.RENAMED.get(p["name"], p["name"])
    cfg["pal_edit"] = max(0, min(int(cfg.get("pal_edit", 0)), len(cfg["palettes"]) - 1))
    load_palette_edit(cfg)
    cfg["scene_edit"] = max(0, min(int(cfg.get("scene_edit", 0)), len(cfg["scenes"]) - 1))
    if 1 <= cfg["effect"] <= len(cfg["scenes"]):                  # a scene picked in the list is the one being edited
        cfg["scene_edit"] = cfg["effect"] - 1
    SC.apply_scene(cfg, cfg["scenes"][cfg["scene_edit"]])
    if cfg["effect"] > len(cfg["scenes"]):
        cfg["effect"] = 0
    if data_style_v < 6:                 # the style list changed: back to "scene default"
        cfg["style"] = 8
    cfg["style_v"] = 6
    cfg["scene_now"] = False
    cfg["fullscreen"] = False        # never start full screen: the control window would be hidden behind it
    cfg["preset"] = match_preset(cfg)
    asx = data.get("auto_sets") if isinstance(data, dict) else None
    if isinstance(asx, dict):
        for kind_, parts_ in cfg["auto_sets"].items():
            for pk_, vals_ in parts_.items():
                got_ = (asx.get(kind_) or {}).get(pk_) or {}
                vals_.update({k: v for k, v in got_.items() if k in vals_ and type(v) is type(vals_[k])})
    cfg["search"] = ""
    cfg["live"] = False                                                             # a show never starts with the edits going straight to the picture
    cfg["sys_item"] = 0                                                            # the pages of Sistema changed: it opens on the first one
    load_ae(cfg)
    if cfg["camera"] != CAM_AUTO:
        cfg["camera"] = match_camera(cfg)
    if cfg["movement"] != MV_AUTO:
        cfg["movement"] = match_movement(cfg)
    return cfg


def save_cfg(cfg):
    try:
        os.makedirs(APPDIR, exist_ok=True)
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
    except Exception:
        pass


FPS_FREE = 246                                   # the last step of the Fluidez slider: no cap at all (240 is the last number, then "Sem limite")
FPS_OPTS = [("24", 24), ("30", 30), ("60", 60), ("90", 90), ("120", 120), ("144", 144), ("240", 240)]
TARGET_OPTS = [("30", 30), ("60", 60), ("90", 90), ("120", 120), ("144", 144)]
STROBE_OPTS = [("Desligado", 0), ("Suave", 1), ("Completo", 2)]
QUAL4_OPTS = [("Desligado", 0), ("Baixa", 1), ("Média", 2), ("Alta", 3)]
STYLE_OPTS = [("Normal", 0), ("Anime", 1)]
LIGHT_OPTS = [("Rápida", 0), ("Ray tracing", 1)]
AA_OPTS = [("Desligado", 0), ("Bordas", 1), ("FXAA", 2), ("MSAA 2x", 3), ("MSAA 4x", 4), ("MSAA 8x", 5), ("TAA", 6)]
BLOOM_OPTS = [("Desligado", 0), ("Mínimo", 1), ("Baixo", 2), ("Médio", 3), ("Alto", 4)]
PRESET_OPTS = [(n, i) for i, (n, _) in enumerate(PRESETS)] + [("Personalizado", CUSTOM)]
BACKEND_OPTS = [("Auto", 0), ("Vulkan", 1), ("Direct3D 12", 2)]

SCENES = [
    ("CENA", [
        dict(id="effect", kind="radio", value=0, label="Automático",
             help="Escolhe a cena pelo gênero detectado e muda pela música"),
        dict(id="effect", kind="radio", value=1, label="Facetas",
             help="Painéis espelhados em 3 universos de cor"),
        dict(id="effect", kind="radio", value=2, label="Estrela",
             help="Bastões arredondados que formam estrelas; aceita todos os estilos"),
        dict(id="effect", kind="radio", value=3, label="Túnel  ·  techno",
             help="Costelas finas em cinza e preto, uma cor de destaque"),
        dict(id="effect", kind="radio", value=4, label="Catedral  ·  trance",
             help="Vitrais translúcidos em azul, violeta e ouro"),
        dict(id="effect", kind="radio", value=5, label="Impacto  ·  EDM",
             help="Painéis grossos e saturados; a câmera dá um soco no kick"),
        dict(id="effect", kind="radio", value=6, label="Palco  ·  pop",
             help="Painéis arredondados em pastel, contorno de tinta"),
    ]),
]
GRAPHICS = [
    ("ATALHO DE QUALIDADE", [
        dict(id="preset", kind="seg", label="Qualidade gráfica", opts=PRESET_OPTS,
             help=lambda c: "Se travar, use Baixo ou Médio" if c["preset"] != CUSTOM else "Ajuste abaixo"),
    ]),
    ("TELA", [
        dict(id="fullscreen", kind="toggle", label="Tela cheia", chip="F",
             help="Duplo clique na imagem também alterna"),
        dict(id="vsync", kind="toggle", label="Evitar cortes na imagem (VSync)", chip="V",
             help="Ligado: a imagem não 'rasga', mas não passa da fluidez do monitor"),
    ]),
    ("DESEMPENHO", [
        dict(id="res", kind="slider", label="Nitidez da imagem", lo=25, hi=100, step=5, unit="%",
             help="Menos nitidez, mais fluida"),
        dict(id="fps_out", kind="slider", label="Fluidez (FPS)", lo=24, hi=FPS_FREE, step=6, unit=" fps", top=(FPS_FREE, "Sem limite"),
             help=lambda c: "O que o programa tenta manter" + (" · limitada pelo monitor" if c["vsync"] else "")),
        dict(id="dynres", kind="toggle", label="Ajuste automático de nitidez",
             help="Se a imagem começar a travar, o programa reduz a nitidez sozinho"),
        dict(id="detail", kind="slider", label="Quantidade de detalhes", lo=30, hi=100, step=5, unit="%",
             help="Menos detalhes, mais leve"),
        dict(id="dynmin", kind="slider", label="Nitidez mínima do ajuste automático", lo=25, hi=90, step=5, unit="%",
             help="O mínimo que o ajuste automático pode chegar", enabled=lambda c: c["dynres"]),
        dict(id="dist", kind="seg", label="Alcance da imagem", opts=[("Curta", 0), ("Normal", 1), ("Longa", 2)],
             help=lambda c: ["Corta o fundo da imagem: mais leve", "Imagem completa", "Mostra ainda mais fundo"][c["dist"]]),
        dict(id="rrate", kind="seg", label="Desenhar todos os quadros?", opts=[("Total", 0), ("Metade", 1), ("Um terço", 2)],
             help=lambda c: ["Sim: o mais fluido", "Metade: a placa de vídeo trabalha menos", "Um terço: o mais leve, mas fica mais picado"][c["rrate"]]),
        dict(id="steps", kind="slider", label="Qualidade das bordas", lo=24, hi=160, step=8, unit="",
             help="Mais alto = bordas mais certinhas, mas pesa mais"),
    ]),
    ("ILUMINAÇÃO", [
    ]),
    ("IMAGEM", [
        dict(id="bloomq", kind="seg", label="Suavidade do brilho", opts=BLOOM_OPTS,
             help="Mais alto, mais macio"),
        dict(id="bloomres", kind="seg", label="Peso do brilho", opts=[("Metade", 0), ("Quarto", 1), ("Oitavo", 2)],
             help="Oitavo é o mais leve para o computador"),
        dict(id="bloom", kind="slider", label="Brilho das luzes", lo=0, hi=200, step=10, unit="%",
             help="Quanto as luzes brilham"),
        dict(id="mblur", kind="slider", label="Borrão de movimento", lo=0, hi=720, step=15, unit="°",
             help="0 desligado  ·  180° como no cinema"),
        dict(id="mblur_fps", kind="seg", label="Velocidade de referência do borrão", opts=[("24", 24), ("30", 30), ("48", 48), ("60", 60)],
             help=lambda c: f"Obturador aberto por {c['mblur'] / 360.0 / c['mblur_fps'] * 1000:.0f} ms ({c['mblur']}° a {c['mblur_fps']} quadros)" if c["mblur"] else "Ligue o borrão de movimento para usar",
             enabled=lambda c: c["mblur"] > 0),
        dict(id="aa_mode", kind="seg", label="Serrilhado", opts=AA_OPTS,
             help=lambda c: ["Sem suavização", "Nas bordas",
                             "Filtro sobre a imagem pronta", "2 amostras por pixel nas bordas",
                             "4 amostras por pixel nas bordas", "8 amostras nas bordas: o mais pesado",
                             "Mistura vários quadros com deslocamento: bordas limpas, pode deixar leve rastro"][c["aa_mode"]]),
        dict(id="sharp", kind="seg", label="Nitidez", opts=[("Desligada", 0), ("Leve", 1), ("Média", 2), ("Forte", 3)],
             help="Detalhes mais marcados"),
        dict(id="fx_glass", kind="toggle", label="Faces transparentes (vidro)",
             help="Desligado: todas as faces ficam opacas, o que pesa bem menos"),
        dict(id="fx_bloom", kind="toggle", label="Halo de luz", help="Desligado: sem o halo de luz, mais leve"),
        dict(id="fx_trail", kind="toggle", label="Rastro das camadas", help="Desligado: ignora as camadas de rastro (feedback)"),
        dict(id="fx_parts", kind="toggle", label="Partículas das camadas", help="Desligado: ignora as camadas de partículas"),

        dict(id="fx_none", kind="action", label="Todos os efeitos pesados", btn=lambda c: "Desligar todos" if any(c[k] for k in ("fx_glass", "fx_bloom", "fx_trail", "fx_parts")) else "Ligar todos", help="Os cinco acima de uma vez"),
        dict(id="img_style", kind="seg", label="Estilo da imagem", opts=[("Normal", 0), ("Chapado", 1), ("Linhas", 2), ("Pixelado", 3)],
             help=lambda c: ["A imagem como a cena desenha", "Poucas cores lisas, sem degradês", "Só os contornos, na cor da imagem, sobre preto", "Blocos grandes de cor, como um jogo antigo"][c["img_style"]]),
        dict(id="img_pix", kind="slider", label="Tamanho dos pixels", lo=2, hi=16, step=1, unit=" px",
             help="Quanto maior, mais quadrados", enabled=lambda c: c["img_style"] == 3),
        dict(id="scr_aspect", kind="seg", label="Formato da tela", opts=[("Da janela", 0), ("16:9", 1), ("21:9", 2), ("4:3", 3), ("1:1", 4), ("9:16", 5)],
             help="Barras pretas no formato escolhido"),
        dict(id="scr_zoom", kind="slider", label="Aproximar", lo=100, hi=150, step=5, unit="%",
             help="Corta as bordas (projetores que perdem as pontas)"),
        dict(id="scr_mirror", kind="seg", label="Espelhar a tela", opts=[("Não", 0), ("Horizontal", 1), ("Vertical", 2), ("Ambos", 3)],
             help="Projeção por trás ou invertida"),
        dict(id="scr_vig", kind="slider", label="Cantos escuros", lo=0, hi=100, step=5, unit="%",
             help="Escurece os cantos da imagem"),
        dict(id="fin_bright", kind="slider", label="Claridade final", lo=50, hi=150, step=5, unit="%",
             help="Clareia ou escurece tudo  ·  100% não muda"),
        dict(id="fin_contrast", kind="slider", label="Contraste", lo=50, hi=150, step=5, unit="%",
             help="Distância entre claros e escuros  ·  100% não muda"),
        dict(id="fin_sat", kind="slider", label="Cores mais vivas", lo=0, hi=200, step=10, unit="%",
             help="0% é preto e branco  ·  100% não muda"),
        dict(id="fin_gamma", kind="slider", label="Tons médios", lo=50, hi=150, step=5, unit="%",
             help="Abaixo de 100% clareia as sombras, acima escurece"),
        dict(id="fin_temp", kind="seg", label="Temperatura", opts=[("Fria", 0), ("Meio fria", 1), ("Normal", 2), ("Meio quente", 3), ("Quente", 4)],
             help="Mais azul ou mais laranja"),
        dict(id="fin_dither", kind="toggle", label="Evitar faixas nos degradês",
             help="Um grão mínimo tira as faixas visíveis em fundos escuros e projetores"),
        dict(id="safe_flash", kind="seg", label="Limitar flashes", opts=[("Normal", 0), ("Suave", 1), ("Mínimo", 2)],
             help=lambda c: ["Flashes como o programa faz", "Flashes mais fracos: bom para plateias", "Quase sem flashes: para quem tem sensibilidade a luz"][c["safe_flash"]]),
        dict(id="safe_motion", kind="seg", label="Limitar movimento da câmera", opts=[("Normal", 0), ("Reduzido", 1), ("Mínimo", 2)],
             help=lambda c: ["Tremor e giro como a cena pede", "Menos tremor, soco e giro", "Quase sem tremor, soco e giro: para quem enjoa"][c["safe_motion"]]),
    ]),
]
STYLES = [
    ("ESTILO", [
        dict(id="style", kind="radio", value=8, label="Automático",
             help="O estilo muda com a parte da música: suave na calma, brilhante nos drops"),
        dict(id="style", kind="radio", value=0, label="Padrão da cena",
             help="Cada cena usa o estilo que combina com ela"),
        dict(id="style", kind="radio", value=1, label="3D",
             help="Volumes com luz e sombra, câmera em perspectiva"),
        dict(id="style", kind="radio", value=2, label="Neon",
             help="Facetas escuras com o contorno brilhando, como tubos de neon"),
        dict(id="style", kind="radio", value=3, label="Holograma",
             help="Gradiente em cada faceta, linhas finas e bordas de luz"),
        dict(id="style", kind="radio", value=4, label="Raio X",
             help="Película azul e branca: só densidade, bordas e brilho de contorno"),
        dict(id="style", kind="radio", value=5, label="Cromado",
             help="Metal polido que reflete um estúdio colorido (ray tracing: reflete os vizinhos)"),
        dict(id="style", kind="radio", value=6, label="Aquarela",
             help="Pigmento sobre papel, com borda molhada e grão"),
        dict(id="style", kind="radio", value=7, label="Duotom",
             help="A imagem toda em duas cores, que trocam junto com as cores da música"),
    ]),
]
SETTINGS = [
    ("MÚSICA E LUZ", [
        dict(id="react", kind="slider", label="Reatividade ao som", lo=25, hi=200, step=25, unit="%",
             help="Quanto reage à música"),
    ]),
    ("SISTEMA", [
        dict(id="backend", kind="seg", label="Motor de vídeo", opts=BACKEND_OPTS,
             help="Deixe em Auto  ·  reinicie"),
        dict(id="gpu", kind="seg", label="Qual placa de vídeo usar", opts=[("Alto desempenho", 0), ("Economia", 1)],
             help="Alto: placa dedicada  ·  reinicie"),
        dict(id="abuf", kind="seg", label="Atraso do som", opts=[("5 ms", 256), ("11 ms", 512), ("21 ms", 1024), ("43 ms", 2048), ("85 ms", 4096)],
             help="Menor: mais junto  ·  maior: sem falhas"),
        dict(id="auto_update", kind="toggle", label="Procurar atualização ao abrir",
             help="Só avisa que existe versão nova; nada é baixado sem você clicar"),
    ]),
]
CAM_OPTS = [(n, i) for i, (n, _) in enumerate(CAM_PRESETS)] + [("Auto", CAM_AUTO), ("Manual", CAM_MANUAL)]
def _cam_on(g):
    return lambda c: c["camera"] != CAM_AUTO or not c["auto_cam_" + g]          # editable unless the Auto tab hands this parameter to Auto


def _mv_on(g):
    return lambda c: c["movement"] != MV_AUTO or not c["auto_mv_" + g]


CAMERA = [
    ("PREDEFINIÇÃO", [
        dict(id="camera", kind="seg", label="Câmera", opts=CAM_OPTS,
             help=lambda c: "Muda pela música" if c["camera"] == CAM_AUTO else ("Ajustado por você" if c["camera"] == CAM_MANUAL else "Escolha um")),
    ]),
    ("MOVIMENTO", [
        dict(id="cam_orbit", kind="seg", label="Órbita", opts=[("Parada", 0), ("Lenta", 1), ("Média", 2), ("Ampla", 3)],
             help="A câmera passeia ao redor da imagem", enabled=_cam_on("orbit")),
        dict(id="cam_roll", kind="seg", label="Giro", opts=[("Parado", 0), ("Balanço", 1), ("Contínuo", 2)],
             help="Inclina de lado a lado ou gira", enabled=_cam_on("roll")),
        dict(id="cam_shake", kind="seg", label="Tremor na batida", opts=[("Nenhum", 0), ("Leve", 1), ("Forte", 2)],
             help="A câmera treme a cada batida forte (bumbo)", enabled=_cam_on("shake")),
        dict(id="cam_punch", kind="seg", label="Soco na batida", opts=[("Nenhum", 0), ("Leve", 1), ("Forte", 2)],
             help="A câmera avança um pouco a cada batida", enabled=_cam_on("punch")),
        dict(id="cam_funnel", kind="seg", label="Funil", opts=[("Desligado", 0), ("Suave", 1), ("Normal", 2), ("Forte", 3)],
             help="Nos build-ups e drops", enabled=_cam_on("funnel")),
    ]),
    ("RITMO", [
        dict(id="cam_sync", kind="seg", label="Sincronia com o ritmo", opts=[("Livre", 0), ("No compasso", 1), ("Na frase", 2)],
             help=lambda c: ("Os movimentos seguem o tempo, não o relógio" if c["cam_sync"] else "Os movimentos têm ritmo próprio"), enabled=_cam_on("sync")),
    ]),
    ("LENTE", [
        dict(id="cam_fov_min", kind="slider", label="Abertura mínima da lente", lo=30, hi=140, step=5, unit="°",
             help="Lente mais fechada: o ângulo nunca fica abaixo disto", enabled=_cam_on("fov")),
        dict(id="cam_fov_max", kind="slider", label="Abertura máxima da lente", lo=30, hi=140, step=5, unit="°",
             help="Lente mais aberta: o ângulo nunca passa disto", enabled=_cam_on("fov")),
        dict(id="cam_fov_var", kind="seg", label="Lente respira", opts=[("Fixo", 0), ("Respira", 1), ("Pela música", 2)],
             help=lambda c: ("Fica na média entre mínimo e máximo" if c["cam_fov_var"] == 0 else
                             "Vai e volta devagar entre mínimo e máximo" if c["cam_fov_var"] == 1 else
                             "Abre com a energia, o build-up e os drops"),
             enabled=lambda c: _cam_on("fov")(c) and c["cam_fov_min"] != c["cam_fov_max"]),
    ]),
]


SHAPES = [
    ("TROCA DE FORMA", [
        dict(id="sh_when", kind="seg", label="Quando trocar", opts=[("Nunca", 0), ("Na frase", 1), ("A cada compasso", 2), ("Auto", 3)],
             help=lambda c: ["As formas ficam como estão", "Na virada da frase de 8 compassos", "Na batida 1 de cada compasso", "Pela música: frase e drops"][c["sh_when"]]),
        dict(id="sh_mix", kind="seg", label="Distribuição", opts=[("Uma por camada", 0), ("Todas iguais", 1)],
             help=lambda c: "Cada camada usa uma forma da lista" if c["sh_mix"] == 0 else "Todas as camadas usam a mesma forma"),
    ]),
    ("PAINÉIS E CAIXAS", [
        dict(id="sh_0", kind="toggle", label="Painéis (padrão)", help="Retângulos e triângulos finos, como sempre foram"),
        dict(id="sh_2", kind="toggle", label="Cubo", help="Seis faces iguais, arestas vivas"),
        dict(id="sh_16", kind="toggle", label="Cuboide", help="Caixa retangular, mais longa que larga"),
    ]),
    ("REDONDAS", [
        dict(id="sh_1", kind="toggle", label="Esfera", help="Totalmente redonda, só o contorno marca a borda"),
        dict(id="sh_3", kind="toggle", label="Cilindro", help="Lata: duas tampas planas e lado curvo"),
        dict(id="sh_4", kind="toggle", label="Cone", help="Ponta para cima, base redonda"),
        dict(id="sh_15", kind="toggle", label="Cone truncado", help="Cone com a ponta cortada"),
        dict(id="sh_9", kind="toggle", label="Toro", help="Rosca com o buraco no meio"),
        dict(id="sh_10", kind="toggle", label="Anel", help="Aro grosso, de frente para a câmera"),
        dict(id="sh_14", kind="toggle", label="Meia-esfera", help="Cúpula com a base plana"),
    ]),
    ("PIRÂMIDES E PRISMAS", [
        dict(id="sh_5", kind="toggle", label="Pirâmide quadrada", help="Base quadrada e quatro faces"),
        dict(id="sh_6", kind="toggle", label="Pirâmide hexagonal", help="Base de seis lados"),
        dict(id="sh_7", kind="toggle", label="Prisma triangular", help="Barra com seção de triângulo"),
        dict(id="sh_8", kind="toggle", label="Prisma hexagonal", help="Barra com seção de hexágono"),
        dict(id="sh_17", kind="toggle", label="Prisma pentagrâmico", help="Barra com seção de estrela de cinco pontas"),
    ]),
    ("POLIEDROS", [
        dict(id="sh_11", kind="toggle", label="Octaedro", help="Oito faces triangulares, dois diamantes colados"),
        dict(id="sh_12", kind="toggle", label="Dodecaedro", help="Doze faces pentagonais"),
        dict(id="sh_13", kind="toggle", label="Icosaedro", help="Vinte faces triangulares"),
        dict(id="sh_18", kind="toggle", label="Buckyball", help="Bola de futebol: hexágonos e pentágonos"),
    ]),
]
MV_OPTS = [(n, i) for i, (n, _) in enumerate(MV_PRESETS)] + [("Auto", MV_AUTO), ("Manual", MV_MANUAL)]
MOVEMENT = [
    ("PREDEFINIÇÃO", [
        dict(id="movement", kind="seg", label="Modo", opts=MV_OPTS,
             help=lambda c: "Muda pela música" if c["movement"] == MV_AUTO else ("Ajustado por você" if c["movement"] == MV_MANUAL else "Escolha um")),
    ]),
    ("VELOCIDADE", [
        dict(id="mv_speed", kind="seg", label="Velocidade geral", opts=[("Lenta", 0), ("Normal", 1), ("Rápida", 2), ("Pela música", 3)],
             help="Ritmo do fluxo e da rotação", enabled=lambda c: _mv_on("speed")(c)),
        dict(id="mv_inertia", kind="seg", label="Inércia", opts=[("Seca", 0), ("Normal", 1), ("Fluida", 2)],
             help=lambda c: ("Responde na hora, nervoso" if c["mv_inertia"] == 0 else "Equilibrada" if c["mv_inertia"] == 1 else "Suaviza tudo, como em câmera lenta"), enabled=lambda c: _mv_on("inertia")(c)),
    ]),
    ("CAMADAS", [
        dict(id="mv_rot", kind="seg", label="Rotação", opts=[("Parada", 0), ("Lenta", 1), ("Média", 2), ("Rápida", 3)],
             help="Giro das camadas", enabled=lambda c: _mv_on("rot")(c)),
        dict(id="mv_dir", kind="seg", label="Direção", opts=[("Horário", 0), ("Anti-horário", 1), ("Alternada", 2)],
             help="Alternada: vizinhas giram ao contrário", enabled=lambda c: (_mv_on("rot")(c)) and c["mv_rot"] > 0),
    ]),
    ("PULSO", [
        dict(id="mv_pulse", kind="seg", label="Pulsa com a batida", opts=[("Nenhum", 0), ("Leve", 1), ("Médio", 2), ("Forte", 3)],
             help="As camadas crescem na batida", enabled=lambda c: _mv_on("pulse")(c)),
        dict(id="mv_one", kind="toggle", label="Pulsar só na batida 1",
             help="Só a primeira batida do compasso faz a imagem pulsar", enabled=lambda c: (_mv_on("pulse")(c)) and c["mv_pulse"] > 0),
    ]),
    ("TRANSIÇÕES", [
        dict(id="sh_morph", kind="seg", label="Forma vira outra", opts=[("Seco", 0), ("Rápida", 1), ("Suave", 2), ("Lenta", 3)],
             help=lambda c: ["A forma troca de uma vez", "Em 0,35 s", "Em 0,9 s", "Em 2 s"][c["sh_morph"]]),
        dict(id="ctrans", kind="seg", label="Cor vira outra", opts=[("Seco", 0), ("Rápida", 1), ("Suave", 2), ("Lenta", 3), ("No tempo", 4)],
             help=lambda c: ["A cor troca de uma vez", "Em 0,25 s", "Em 0,8 s", "Em 1,8 s", "Dura duas batidas"][c["ctrans"]]),
        dict(id="lay_trans", kind="seg", label="Camadas entram e saem", opts=[("Seco", 0), ("Rápida", 1), ("Suave", 2)],
             help=lambda c: ["Somem e aparecem de uma vez", "Encolhem e crescem em menos de 1 s", "Encolhem e crescem em ~2 s"][c["lay_trans"]]),
        dict(id="scene_fade", kind="seg", label="Troca de cena", opts=[("Seco", 0), ("Rápida", 1), ("Suave", 2)],
             help=lambda c: ["Corte direto, sem escurecer", "Escurece em 0,1 s e volta em 0,25 s", "Escurece em 0,25 s e volta em 0,5 s"][c["scene_fade"]]),
    ]),
    ("RITMO DAS TROCAS", [
        dict(id="mv_cuts", kind="seg", label="Trocas na batida", opts=[("Raras", 0), ("Normais", 1), ("Frequentes", 2)],
             help="Quantas trocas no ritmo", enabled=lambda c: _mv_on("cuts")(c)),
    ]),
]
_ROWS = {r["id"]: r for _, rs in GRAPHICS + SETTINGS for r in rs if r["kind"] != "radio"}


def _card(title, *ids):
    return (title, [_ROWS[i] for i in ids])


# five tabs, one purpose each: what is drawn / how the camera moves / how the picture looks / how heavy it is / the program itself
LIVE_H = 540                       # height of the live tab's content (drawn by the control window, see deck.py)
GENRE_OPTS = [("Nenhum", ""), ("techno", "techno"), ("trance", "trance"), ("EDM", "edm"), ("pop", "pop")]
SHADER_OPTS = [("Automático", 8), ("3D", 1), ("Neon", 2), ("Holograma", 3), ("Raio X", 4), ("Cromado", 5), ("Aquarela", 6), ("Duotom", 7)]


def auto_rows(kind):
    """The toggles of "what the Automático may change". They only matter while the camera / movement is on Auto, and they belong to the scene."""
    if kind == "cam":
        pairs = (("auto_cam_orbit", "Órbita"), ("auto_cam_roll", "Giro"), ("auto_cam_shake", "Tremor"), ("auto_cam_punch", "Soco"),
                 ("auto_cam_funnel", "Funil"), ("auto_cam_fov", "FOV"), ("auto_cam_sync", "Sincronia"))
        mode, val = "camera", CAM_AUTO
    elif kind == "mv":
        pairs = (("auto_mv_speed", "Velocidade"), ("auto_mv_rot", "Rotação"), ("auto_mv_pulse", "Pulso"), ("auto_mv_cuts", "Trocas na batida"),
                 ("auto_mv_inertia", "Inércia"))
        mode, val = "movement", MV_AUTO
    else:
        return [dict(id="auto_cuts", kind="toggle", label="Trocar as cores na batida", help="O Automático muda as cores nos cortes e nas frases"),
                dict(id="auto_vars", kind="toggle", label="Cor diferente por elemento", help="O Automático varia a cor de cada camada"),
                dict(id="auto_shape", kind="toggle", label="Trocar as formas", help="Troca as formas na frase e nos drops")]
    return [dict(id=k, kind="toggle", label=lab, help=lambda c, k=k: "O Automático muda isto com a música" if c[k] else "Fica no valor que você escolheu",
                 enabled=lambda c, m=mode, v=val: c[m] == v) for k, lab in pairs]


def band_rows():
    """How the picture answers the music: one overall gain and one for each band."""
    return [_ROWS["react"]] + [dict(id=k, kind="slider", label=lab, lo=25, hi=200, step=5, unit="%", help="Só esta faixa de frequência  ·  duplo clique restaura")
                               for k, lab in (("react_bass", "Graves"), ("react_mid", "Médios"), ("react_high", "Agudos"))]


# ------------------------------------------------------------------ what the Automatico does in each part of the music (editable)
AE_CAM_PARTS = (("Calmo", "1"), ("Intenso", "2"), ("Normal", "3"))
AE_MV_PARTS = (("Calmo", "calm"), ("Ritmo", "groove"), ("Pico", "high"), ("Build-up", "build"))
PROFILE_DIR = os.path.join(APPDIR, "perfis")


def auto_sets_factory():
    import neon_director as ND
    return {"cam": {str(k): dict(v) for k, v in ND.CAM_AUTO_SETS.items()}, "mv": {k: dict(v) for k, v in ND.MV_AUTO_SETS.items()}}


_AS0 = auto_sets_factory()
DEFAULTS.update(panel_fps=30, panel_fps_v=2, link_riser=False, link_vocal=False, remote_osc=False, remote_midi=False, phone_view=False, search="", ui_tab=0, live=False, profile=1, ae_kind=0, ae_part=0, auto_sets=auto_sets_factory())
DEFAULTS.update(LY.LP_DEFAULTS)
DEFAULTS["starter_v"] = 4
DEFAULTS.update(ed_item=0, ed_sub=0, ed_page=False, ed_tab=0, sc_filter=0, lib=-1, pal_open=False, sys_item=0, ear_open=True, tour_done=False, tour_marks=0, osd=True, advanced=False, macro_energy=100, macro_speed=100, macro_pal=0, detail_open=False)                                                  # the item of the editor of a scene that is open, and the sub-section of the mandala                                                          # 2: the mandala presets come as scenes of the gallery
DEFAULTS.update(layers=[], ly_sel=0, ly_add=-1, ly_tpl=-1)                    # the stack of layers of the scene being edited and the working keys of the layer selected (see layers.py)
DEFAULTS.update({"ae_" + k: v for k, v in {**_AS0["cam"]["1"], **_AS0["mv"]["calm"]}.items()})


def profile_path(n):
    return os.path.join(PROFILE_DIR, f"perfil{int(n)}.json")


def ae_current(cfg):
    """(kind, part key) the Automatico editor of Ajustes is on."""
    if int(cfg.get("ae_kind", 0)) == 0:
        return "cam", AE_CAM_PARTS[max(0, min(len(AE_CAM_PARTS) - 1, int(cfg.get("ae_part", 0))))][1]
    return "mv", AE_MV_PARTS[max(0, min(len(AE_MV_PARTS) - 1, int(cfg.get("ae_part", 0))))][1]


def load_ae(cfg):
    """Copy the values of the part being edited into the working keys (ae_...)."""
    kind, part = ae_current(cfg)
    base = auto_sets_factory()[kind][part]
    s = cfg["auto_sets"].setdefault(kind, {}).setdefault(part, {})
    for k, v in base.items():
        s.setdefault(k, v)
        cfg["ae_" + k] = s[k]


def ae_rows(cfg):
    cam = int(cfg.get("ae_kind", 0)) == 0
    parts = AE_CAM_PARTS if cam else AE_MV_PARTS
    keys = CAM_KEYS if cam else MV_KEYS
    rows = [dict(id="ae_kind", kind="seg", label="Editar", opts=[("Câmera", 0), ("Movimento", 1)], help="O que o modo Automático faz em cada parte da música"),
            dict(id="ae_part", kind="seg", label="Parte da música", opts=[(n, i) for i, (n, _) in enumerate(parts)],
                 help="Calmo, Normal ou Intenso (build-up e drop)" if cam else "Calmo, ritmo normal, pico de energia ou build-up")]
    for _, rs in (CAMERA if cam else MOVEMENT):
        for r in rs:
            if r["id"] in keys:
                r2 = dict(r, id="ae_" + r["id"], help=r["help"] if isinstance(r["help"], str) else "")
                r2.pop("enabled", None)
                rows.append(r2)
    rows.append(dict(id="ae_reset", kind="action", label="Restaurar esta parte", btn="Restaurar", help="Volta aos valores de fábrica desta parte"))
    return rows


SYS_ITEMS = [("Imagem", "Resolução, brilho, suavização e medição"),
             ("Áudio", "De onde vem o som que a imagem segue"),
             ("Automático", "Quais cenas entram e quando trocam"),
             ("Perfis e controle", "Perfis salvos e controle por OSC ou MIDI"),
             ("Aplicativo", "Motor de vídeo e atualizações"),
             ("Tela", "Tela cheia, monitor e dicas na tela")]          # one name per page, short enough for the row of choices of a narrow window: it is the name everywhere
SYS_IMAGE = 0
SYS_ORDER = [0, 1, 5, 2, 3, 4]                                                   # the order the pages are listed in (the numbers stay as they were saved)


def search_rows(cfg, q):
    """Every setting of the program whose name or help has the text typed in the search field (the help line says where it lives). It also finds what the
    simple mode hides (tagged "Avançado"): a result you cannot reach is better than a search that says "Nada encontrado"."""
    q = q.lower().strip()
    cands = []
    full = dict(cfg, advanced=True)
    for k in range(len(SYS_ITEMS)):
        shown = {r["id"] for _, rs in sys_cards(cfg, k) for r in rs}
        for _, rs in sys_cards(full, k):
            cands += [("Sistema · " + SYS_ITEMS[k][0] + ("" if r["id"] in shown else " · Avançado"), f"sys:{k}", r) for r in rs if not r["id"].startswith("ae_")]
    for item, sub in ED_VIEWS:
        if item < 0:
            continue
        for _, rs in scene_rows(ed_view(cfg, item, sub), "editor")[2:]:
            cands += [("Estúdio · " + ED_ITEMS[item][1].capitalize() + " (cena aberta)", f"ed:{item}", r) for r in rs]
    out, seen = [], set()
    for where, dest, r in cands:
        if r["kind"] not in ("seg", "toggle", "slider") or r["id"] in seen or r["id"] in ("scene_sec", "sys_item") or not r.get("label") or r["id"].startswith("sc_auto:"):
            continue                                                               # a row with no name (a bare row of chips) is no result
        h = r.get("help", "")
        if callable(h):
            try:
                h = h(cfg)
            except Exception:
                h = ""
        if q in f"{r.get('label', '')} {h} {where}".lower():
            seen.add(r["id"])
            out.append(dict(r, help=where, _goto=dest))
        if len(out) >= 14:
            break
    return out


def search_cards(cfg):
    """What takes the place of the page while a word is typed in the search field: the settings that have it, each saying where it lives, and under each
    place a button that goes there."""
    found = search_rows(cfg, str(cfg.get("search", "")))
    if not found:
        return [("RESULTADOS  ·  0", [dict(id="search_none", kind="note", label="Nada encontrado", help="Tente outra palavra")])]
    cards, places = [], {}
    for r in found:
        places.setdefault(r["_goto"], []).append(r)
    for i, (dest, rows) in enumerate(places.items()):
        where = rows[0]["help"].replace(" (cena aberta)", "")
        rows = rows + [dict(id="goto:" + dest, kind="action", label="Abrir esta página", btn="Ir →", help="")]
        cards.append((f"RESULTADOS  ·  {len(found)}" if i == 0 else "", rows))
    return cards


def sys_cards(cfg, k, devices=(), monitors=1, menu=None):
    """The cards of page k of Sistema (SYS_ITEMS). The audio devices and the monitors are asked of the system when the program opens, so the rows are built here;
    `menu` lends the live text, the version and the update button to the rows that show them."""
    m = menu
    adv = bool(cfg.get("advanced", False))
    if k == 0:
        detail = adv or cfg.get("preset") == CUSTOM                              # "Personalizado" opens the options of the picture, in the simple mode too
        return (list(GFX_CARDS) if detail else list(GFX_CARDS[:1])) + list(OUT_CARDS) + [("DESEMPENHO", [
            dict(id="bench", kind="action", label="Medir o desempenho", btn="Medir (10 s)",
                 help=lambda c: (m.live if m is not None and m.live else "Anda a imagem por 10 segundos e mostra o FPS médio")),
            dict(id="reset", kind="action", label="Restaurar a imagem", btn="Restaurar", help="Volta ao padrão esta página"),
        ])]
    if k in (1, 5):
        adev = [dict(id="adev", kind="radio", value="", label="Padrão do Windows", help="O que estiver tocando na saída padrão")] + [
            dict(id="adev", kind="radio", value=n, label=n.replace(" [Loopback]", ""), help="Só o som desta saída") for n in list(devices)[:6]]
        tela = [_ROWS["fullscreen"], dict(id="osd", kind="toggle", label="Dicas na tela cheia", help="Por alguns segundos: as teclas e o nome da cena que você troca"),
                _ROWS["vsync"],
                dict(id="panel_fps", kind="seg", label="FPS do painel", opts=[("10", 10), ("15", 15), ("24", 24), ("30", 30), ("60", 60), ("Da imagem", 0)],
                     help=lambda c: "A cada quadro" if c["panel_fps"] == 0 else f"{c['panel_fps']} vezes por segundo"),
                dict(id="monitor", kind="seg", label="Monitor da imagem", opts=[("Onde está", 0)] + [(str(i + 1), i + 1) for i in range(max(1, min(monitors, 4)))],
                     help="Move a janela de imagem (e a tela cheia) para este monitor")]
        if k == 5:
            return [("TELA GRANDE", tela), SCREEN_CARD]
        note = dict(id="adev_note", kind="note", label="O programa ouve o som do computador: escolha a saída da música", help="")
        return [("ENTRADA DE ÁUDIO", [note] + adev + [_ROWS["abuf"]]),            # the sound first: it is what "Sem som" of the Palco brings people here for
                ("O QUE O PROGRAMA OUVE", [dict(id="ear_view", kind="ear", label="", help="")])]          # the analysis: to check the beat and the bands before changing the input
    if k == 2:
        musica = [dict(id="link_riser", kind="toggle", label="Perceber a subida antes do drop", help="Quando a música vai subindo, a imagem esquenta junto (strobe, câmera)"),
                  dict(id="link_vocal", kind="toggle", label="Voz acalma os flashes", help="Quando alguém está cantando, os flashes ficam mais fracos")]
        return auto_cards(cfg) + [("A MÚSICA CONTROLA A CENA", musica)] + ([("O QUE O AUTOMÁTICO FAZ", ae_rows(cfg))] if adv else [])
    if k == 3:
        perfis = [dict(id="profile", kind="seg", label="Perfil", opts=[("1", 1), ("2", 2), ("3", 3)],
                       help=lambda c: "Salvo" if os.path.exists(profile_path(c["profile"])) else "Vazio  ·  Salvar guarda tudo o que está configurado"),
                  dict(id="profile_save", kind="action", label="Salvar neste perfil", btn="Salvar", help="Guarda tudo o que está configurado agora"),
                  dict(id="profile_load", kind="action", label="Carregar este perfil", btn="Carregar", help="Volta tudo para o que estava salvo",
                       enabled=lambda c: os.path.exists(profile_path(c["profile"])))]
        externo = [dict(id="remote_osc", kind="toggle", label="Controle pela rede (OSC)", help="Só neste computador  ·  porta 9000"),
                   dict(id="remote_midi", kind="toggle", label="Controle por MIDI (teclado ou pad)", help="As notas 60 a 68 tocam as cenas 1 a 9  ·  as outras estão no README")]
        celular = [dict(id="phone_view", kind="toggle", label="Ver no celular",
                        help=lambda c: (f"Abra no navegador do celular: {_phone_url()}" if c.get("phone_view") else "A imagem ao vivo e botões de cena no navegador  ·  mesma rede Wi-Fi"))]
        return [("PERFIS", perfis), ("VER NO CELULAR", celular)] + ([("CONTROLE EXTERNO", externo)] if adv else [])
    ver = lambda c: (m.info if m is not None and m.info else "Procura uma versão nova agora")
    lang = ("IDIOMA", [dict(id="lang", kind="seg", label="Idioma", opts=[(n, c) for n, c in i18n.LANGS], help="Começa pelo idioma do Windows")])
    return [lang] + ([("MOTOR DE VÍDEO", [_ROWS["backend"], _ROWS["gpu"]])] if adv else []) + [
            ("ATUALIZAÇÃO", [_ROWS["auto_update"],
                              dict(id="update_check", kind="action", label="Verificar atualização", btn="Verificar", help=ver),
                              dict(id="update_apply", kind="action", label="Instalar a atualização", btn=lambda c: (m.upd_label if m is not None and m.upd_label else "Atualizar"),
                                   help=lambda c: ("Novidades: " + m.notes) if m is not None and m.upd_label and m.notes else "Aparece quando houver uma versão nova",
                                   enabled=lambda c: bool(m is not None and m.upd_label), primary=True)]),
            ("SESSÃO", [_quit_row(m), dict(id="saved_note", kind="note", label="As configurações são salvas automaticamente", help="")])]


def _quit_row(m):
    return dict(id="quit", kind="action", label="Sair do programa", help="Toque duas vezes  ·  tudo fica salvo",
                btn=lambda c: "Confirmar?" if m is not None and m.quit_armed > time.perf_counter() else "Sair", danger=True)


def sys_layout(cfg, k, wide, devices=(), monitors=1, menu=None):
    """Sistema as (cards, columns): the search field on top, then the categories, then the page (or, while something is typed in the field, the results). In a wide window
    the field and the categories are a list on the left and the page is on the right; in a narrow one the categories are one row of choices over the page."""
    q = str(cfg.get("search", "")).strip()
    page = search_cards(cfg) if q else sys_cards(cfg, k, devices, monitors, menu)
    find = ("", [dict(id="search", kind="text", label="Buscar", placeholder="brilho, cor, strobe…", help="Ctrl+F")])
    if wide:
        nav = ("SISTEMA", [dict(id="sys_item", kind="radio", value=i, label=SYS_ITEMS[i][0], help=SYS_ITEMS[i][1]) for i in SYS_ORDER])
        foot = ("", [_quit_row(menu)])                                            # leaving the program is always at hand, under the pages
        page = [c for c in page if c[0] != "SESSÃO"]
        return [find, nav, foot] + page, ["L", "L", "L"] + ["R"] * len(page)
    nav = ("SISTEMA" if q else SYS_ITEMS[k][0].upper(), [dict(id="sys_item", kind="seg", label="", opts=[(SYS_ITEMS[i][0], i) for i in SYS_ORDER], help="")])
    return [find, nav] + page, []


def flash_rows():
    """The card of the flashes: the strobe of the build-ups, the flash of the drop, the quarter-beat bursts, their length and how they are laid on the picture."""
    on = lambda c: c["strobe"] > 0
    return [
        dict(id="strobe", kind="seg", label="Strobe no build-up", chip="S", opts=STROBE_OPTS,
             help=lambda c: ["Sem strobe e sem rajadas", "No máximo uma piscada por batida", "Mais rápido com a tensão"][c["strobe"]]),
        dict(id="fl_start", kind="seg", label="Strobe começa", opts=[("Cedo", 0), ("Normal", 1), ("Tarde", 2)],
             help="Quanta tensão a música precisa ter", enabled=on),
        dict(id="fl_roll", kind="toggle", label="Flash nas viradas de caixa", help="Um flash curto a cada batida rápida de caixa (roll)", enabled=on),
        dict(id="fl_drop", kind="seg", label="Flash do drop", opts=[("Sem", 0), ("Suave", 1), ("Forte", 2)],
             help=lambda c: ["Nenhum flash quando o drop cai", "Flash médio quando o drop cai", "Flash inteiro quando o drop cai"][c["fl_drop"]]),
        dict(id="bursts", kind="toggle", label="Rajadas rápidas de flash",
             help=lambda c: "Piscadas rápidas ocasionais no ritmo" if c["strobe"] == 2 else "Disponível só com o strobe em Completo",
             enabled=lambda c: c["strobe"] == 2),
        dict(id="fl_len", kind="seg", label="Duração dos flashes", opts=[("Curta", 0), ("Normal", 1), ("Longa", 2)],
             help=lambda c: ["Somem na metade do tempo", "Como sempre foi", "Ficam o dobro do tempo"][c["fl_len"]]),
        dict(id="fl_mode", kind="seg", label="Efeito do flash", opts=[("Inverter", 0), ("Clarão", 1)],
             help=lambda c: ["A imagem inverte por um instante (negativo)", "Um clarão branco somado à imagem"][c["fl_mode"]]),
    ]


ED_VIEWS = [(-1, 0)] + [(0, s) for s in (0, 2, 3, 4)] + [(k, 0) for k in (6, 7, 8, 9, 10, 11, 12)]       # every screen of the editor: (item, sub-section of the mandala); -1 is the overview


def ed_view(cfg, item, sub):
    """cfg with the editor on the screen (item, sub): the keys that say which one."""
    return dict(cfg, ed_item=max(item, 0), ed_sub=sub, ed_page=item >= 0)
SEC_OPTS = [("Cena", 0), ("Visual", 1), ("Camadas", 2), ("Cores", 3), ("Shader", 4), ("Câmera", 5), ("Movim.", 6), ("Formas", 7)]


ED_SUBS = [("Modelo", 0), ("Estilo", 2), ("Simetrias", 3), ("Formas", 4)]                 # inside the Aparência tab (the colours have a tab of their own)
ED_TABS = [("Aparência", 0), ("Cores", 1), ("Câmera", 2), ("Movimento", 3), ("Música", 4), ("Camadas", 5), ("Cena", 6)]      # the parts of a scene, one tab each


def ed_tab_of(cfg):
    """The tab that shows the screen (ed_item, ed_sub) of the editor."""
    item = int(cfg.get("ed_item", 0))
    if item == 2 and not cfg.get("advanced"):                                      # the simple mode shows the camera and the movement in one tab
        return 2
    return (1 if int(cfg.get("ed_sub", 0)) == 1 else 0) if item == 0 else item + 1


def ed_tab_apply(cfg, tab):
    """Open a tab: the keys that say which screen of the editor it is."""
    if tab == 1:                                                                   # the colours are in the settings of the scene now
        cfg["ed_item"] = 6
    elif tab == 0:
        cfg["ed_item"] = 0
        cfg["ed_sub"] = 0 if int(cfg.get("ed_sub", 0)) == 1 else int(cfg.get("ed_sub", 0))
    else:
        cfg["ed_item"] = tab - 1
    cfg["ed_page"] = True
    cfg["ed_tab"] = tab
CAM_DESC = ["Parada, de frente", "Passeia devagar, com zoom suave", "Treme e dá socos no bumbo, como clipe", "Gira devagar, quase sem parar"]
MV_DESC = ["O de sempre", "Devagar e macio", "Gira e pulsa em ondas longas", "Rápido, com trocas bruscas", "Acelera e freia com a música"]


def _preset_row(row, desc):
    """A row of presets with a sentence for each one (the simple mode shows only this)."""
    auto, manual = (CAM_AUTO, CAM_MANUAL) if row["id"] == "camera" else (MV_AUTO, MV_MANUAL)
    return dict(row, help=lambda c, r=row["id"]: "Muda pela música" if c[r] == auto else ("Ajustado no modo Avançado" if c[r] == manual else desc[c[r]]))
ED_ITEMS = (("vis", "FORMA"), ("beh", "CÂMERA"), ("beh", "MOVIMENTO"), ("beh", "MÚSICA"), ("lay", "CAMADA"), ("sc", "CENA"),
            ("sc", "CENA"), ("lay", "FUNDO"), ("lay", "LUZES"), ("lay", "PARTÍCULAS"), ("lay", "ACABAMENTO"), ("lay", "SOBREPOSIÇÃO"), ("sc", "LIGAÇÕES"))
SLOT_ITEM = {"bg": 7, "lights": 8, "form": 0, "parts": 9, "finish": 10, "over": 11}         # the page of each of the six layers
ITEM_SLOT = {v: k for k, v in SLOT_ITEM.items()}
STACK_ORDER = ("over", "finish", "parts", "form", "lights", "bg")                           # the stack, top first (the way it is drawn: the last one is behind)


def layer_item(cfg):
    """The page where the selected layer of the stack is edited (the layer of the six its kind belongs to)."""
    layers = cfg.get("layers") or []
    i = int(cfg.get("ly_sel", 0))
    if not 0 <= i < len(layers):
        return 0
    return SLOT_ITEM.get(LY.SLOT_OF.get(layers[i].get("t"), "finish"), 10)


def _item_text(cfg, k):
    """What an item of the editor says about itself: (name, state in a few words)."""
    scn = cfg.get("scenes") or []
    if k == 0:
        if cfg.get("scene_visual", 1) == 0:
            return "Nenhum", "só uma tela preta"
        v = int(cfg.get("scene_visual", 1))
        if v >= 2:
            return SC.VISUALS[min(v, len(SC.VISUALS) - 1)][0], SC.VISUALS[min(v, len(SC.VISUALS) - 1)][1]
        shs = cfg.get("shaders") or []
        sid = int(cfg.get("scene_shader", 0))
        shn = "shader automático" if sid == 0 or sid > len(shs) else shs[sid - 1]["name"]
        return "Mandala · " + SC.PRESET_NAMES[SC.preset_of(cfg)], shn
    if k == 1:
        return "Câmera", next((n for n, v in CAM_OPTS if v == cfg.get("camera", 0)), "manual")
    if k == 2:
        return "Movimento", next((n for n, v in MV_OPTS if v == cfg.get("movement", 0)), "manual")
    if k == 3:
        return "Música", f"reação {cfg.get('react', 100)}%  ·  strobe " + ("desligado", "leve", "completo")[max(0, min(2, int(cfg.get("strobe", 2))))]
    if k == 12:
        n = len(cfg.get("mods") or {}) + len(cfg.get("cycles") or {})
        return "Segue a música", ("nada segue a música" if n == 0 else (f"{n} coisa segue a música" if n == 1 else f"{n} coisas seguem a música"))
    if k == 6:
        pals = cfg.get("palettes") or []
        pi = int(cfg.get("scene_palette", 0))
        cam = next((n for n, v in CAM_OPTS if v == cfg.get("camera", 0)), "manual")
        mov = next((n for n, v in MV_OPTS if v == cfg.get("movement", 0)), "manual")
        return "Ajustes da cena", "  ·  ".join(((pals[pi - 1]["name"] if 0 < pi <= len(pals) else "cores do modelo"), "câmera " + cam.lower(), "ritmo " + mov.lower()))
    if k in ITEM_SLOT and k != 0:
        slot = ITEM_SLOT[k]
        name = next(n for s, n, _ in LY.SLOTS if s == slot)
        if not LY.slot_on(cfg, slot):
            return name, "desligada"
        if slot == "over":
            return name, ("logo" if int(cfg.get("ov_kind", 0)) == 1 else "“" + str(cfg.get("ov_text", "")) + "”")
        ls = [LY.TYPES[l["t"]]["label"] for l in (cfg.get("layers") or []) if LY.SLOT_OF.get(l.get("t")) == slot and l.get("on", True)]
        if slot == "bg":
            ls = [("fundo " + ("do estilo", "preto", "branco", "cor própria")[int(cfg.get("scene_bg", 0)) % 4])] + ls
        if slot == "finish":
            ls = [("Normal", "Chapado", "Linhas", "Pixelado")[int(cfg.get("img_style", 0)) % 4]] + ls
        return name, "  ·  ".join(ls) if ls else "vazia"
    return "Propriedades", cfg.get("scene_name", "") + ("  ·  fora do Automático" if not cfg.get("scene_auto", True) else "")


# the three big controls of the Palco, valid for every scene: how strongly the picture answers the music, how fast it moves, which colours it wears
MACRO_ENERGY = [("Calma", 35), ("Suave", 70), ("Normal", 100), ("Forte", 140), ("Máxima", 190)]
MACRO_SPEED = [("Lenta", 40), ("Calma", 70), ("Normal", 100), ("Rápida", 150), ("Turbo", 230)]


def macro_index(table, value):
    """Which step of a table is the nearest to the stored value."""
    return min(range(len(table)), key=lambda i: abs(table[i][1] - value))


WIDE_MIN = 900                                                               # from this width the Estúdio shows the scenes and the stack on the left and the item on the right
WHEN_OPTS = [("Agora", 0), ("No compasso", 1), ("Na frase", 2), ("Pela música", 3), ("A cada N s", 4)]


def scene_sub(cfg, sc):
    """What a scene is made of, in a few words (under its name in the list)."""
    shs = cfg.get("shaders") or []
    sid = int(sc.get("scene_shader", 0))
    if sc.get("scene_visual", 1) == 0:
        ls = LY.lights_style(sc)
        return "Nenhum visual" + ("  ·  " + ("", "Aurora", "Feixes", "Pulsos", "Estrelas", "Faixas", "Lasers", "Feixe")[ls % 8] if ls else "")
    if int(sc.get("scene_visual", 1)) >= 2:
        return SC.VISUALS[min(int(sc["scene_visual"]), len(SC.VISUALS) - 1)][0]
    pn = SC.PRESET_NAMES[SC.preset_of(sc)]
    shn = "Shader auto" if sid == 0 or sid > len(shs) else shs[sid - 1]["name"]
    return ("Mandala" if pn == sc.get("scene_name") else "Mandala " + pn) + "  ·  " + shn


def scene_list_cards(cfg):
    """The scenes as a list (the Estúdio when it is wide): click one to edit it, play it, duplicate it, delete it."""
    scn = cfg.get("scenes") or []
    flt = int(cfg.get("sc_filter", 0))
    keep = lambda sc: flt == 0 or (flt == 1) == (int(sc.get("scene_visual", 1)) == 1)
    rows = [dict(id="sc_filter", kind="seg", label="Mostrar", opts=[("Todas", 0), ("Mandalas", 1), ("Outras", 2)], help=f"{len(scn)} cenas")] if len(scn) > 8 else []
    rows += [dict(id=f"sc_{i}", kind="scene", idx=i, label=sc.get("scene_name", "?"), help=scene_sub(cfg, sc)) for i, sc in enumerate(scn) if keep(sc)]
    rows.append(dict(id="scene_add", kind="action", label="Criar uma cena", btn="+ Nova cena", help="Em 3 passos", primary=False))
    return [("CENAS", rows)]


def auto_cards(cfg=None):
    """The Automático page (Sistema, opened by the Opções button next to "Troca automática" in the Palco): whether the program changes the scene by itself, when,
    and which scenes it may bring. Whether a click on a scene waits for the beat is a choice of the advanced mode."""
    adv = bool((cfg or {}).get("advanced", False))
    scn = (cfg or {}).get("scenes") or []
    return [("TROCA AUTOMÁTICA", [
        dict(id="autoall", kind="toggle", label="Troca automática", get=lambda c: c["effect"] == 0,
             help=lambda c: "O programa escolhe a próxima cena pela música" if c["effect"] == 0 else "Uma cena fica fixa no ar  ·  ligue para voltar ao Automático"),
        dict(id="scene_when", kind="dd", label="Quando troca sozinha", opts=WHEN_OPTS,
             help=lambda c: ["Troca no mesmo instante", "Espera o próximo compasso", "Espera a próxima frase", "Espera um evento da música", "Troca num tempo fixo"][int(c["scene_when"]) % 5]),
        dict(id="scene_every", kind="dd", label="A cada", opts=[(f"{v} s", v) for v in (15, 30, 60, 120)], help="Só no modo A cada N s",
             enabled=lambda c: int(c["scene_when"]) == 4),
    ] + ([dict(id="scene_wait", kind="seg", label="Ao clicar numa cena", opts=[("Na hora", 0), ("No momento", 1)],
               help=lambda c: "A cena clicada espera o momento escolhido acima" if c.get("scene_wait") else "A cena clicada entra na hora")] if adv else [])),
        ("CENAS NO AUTOMÁTICO", [dict(id="sc_auto_note", kind="note", label="Marque as cenas que o Automático pode trazer",
                                      help=lambda c: "" if any(s.get("scene_auto", True) for s in c["scenes"]) else "Nenhuma está marcada: o Automático fica na cena que está no ar")]
         + [dict(id=f"sc_auto:{i}", kind="toggle", flow=True, label=sc.get("scene_name", "?"), get=(lambda c, i=i: bool(c["scenes"][i].get("scene_auto", True))),
                 help=scene_sub(cfg, sc)) for i, sc in enumerate(scn)])]


def library_cards():
    """The library of scenes as a file (the Estúdio)."""
    return [("BIBLIOTECA", [
        dict(id="lib", kind="dd", label="Arquivo", placeholder="Exportar, importar…", opts=[("Exportar (Documentos)", 0), ("Importar", 1), ("Voltar às de fábrica", 2)],
             help=""),
    ])]


def scene_layout(cfg, view="gallery", wide=False):
    """The Estúdio as (cards, columns). The gallery is drawn by the control window. The editor of one scene has two levels: the OVERVIEW (a bar with Salvar / Descartar / Galeria
    and the stack of the scene: the mandala, the behaviours, the layers and the properties) and, when an item is clicked, its own PAGE with everything to set in it and a way back.
    In a wide window both are on the screen: the scenes and the stack on the left (columns "L"), the page of the item on the right ("R"), the bar over both ("F")."""
    if view != "editor":
        return [], []
    name = cfg.get("scene_name", "?")
    adv = bool(cfg.get("advanced", False))
    item = int(cfg.get("ed_item", 0))
    has_layers = bool(cfg.get("layers"))
    if item in (1, 2, 3, 5) or (item == 0 and int(cfg.get("ed_sub", 0)) == 1):   # (the old tabs) are all in the settings of the scene now
        item = 6
    if item == 4:
        item = layer_item(cfg)
    left, right = stack_cards(cfg, item), []
    closed = int(cfg.get("ed_item", 0)) < 0                                      # the accordion with every item folded
    # ---- the page of the item (the right column when the window is wide)
    if closed:
        item = -1
    if item in ITEM_SLOT and not LY.slot_on(cfg, ITEM_SLOT[item]):
        right.append(("", [dict(id="layer_on:" + ITEM_SLOT[item], kind="action", label="Esta camada está desligada", btn="Ligar", help="Os ajustes ficam guardados")]))
    if item == 0:
        right += mandala_rows(dict(cfg, ed_sub=0 if int(cfg.get("ed_sub", 0)) == 1 else cfg.get("ed_sub", 0)))
    elif item == 6:
        right += scene_settings_cards(cfg, adv)
    elif item in (7, 8, 9, 10):
        right += slot_cards(cfg, ITEM_SLOT[item], adv)
    elif item == 11:
        right += layer_cards(cfg, adv, has_layers)[-1:]
    elif item == 12:
        right += links_cards(cfg)
    elif item == -1:
        pass
    elif item == 1:
        right += (CAMERA + [("O AUTOMÁTICO ESCOLHE", auto_rows("cam"))]) if adv else [("CÂMERA", [_preset_row(CAMERA[0][1][0], CAM_DESC)]),
                                                                                 ("RITMO DA CENA", [_preset_row(MOVEMENT[0][1][0], MV_DESC)])]
    elif item == 2:
        right += (MOVEMENT + [("O AUTOMÁTICO ESCOLHE", auto_rows("mv")), ("TROCAS AUTOMÁTICAS", auto_rows("sw")[:2])]) if adv else MOVEMENT[:1]
    elif item == 3:
        bloom = ("BRILHO", [_ROWS["bloom"], dict(id="expo", kind="slider", label="Exposição", lo=50, hi=200, step=10, unit="%",
                                                 help="Quanto a imagem clareia")])
        right += [("SOM", band_rows()), ("PISCADAS", flash_rows()), bloom] if adv else [("SOM", band_rows()[:1]), ("PISCADAS", flash_rows()[:1]), bloom]
    elif item == 4:
        right += layer_cards(cfg, adv, has_layers)
    else:
        right.append(("PROPRIEDADES DA CENA", [
            dict(id="scene_name", kind="text", label="Nome", help="Clique e digite  ·  Enter confirma"),
            dict(id="scene_auto_note", kind="note", label=lambda c: "Entra no Automático" if c["scene_auto"] else "Fora do Automático: só toca se você mandar", help="Marque ou desmarque em Sistema > Automático"),
            dict(id="goto:sys:2", kind="action", label="Mudar no Automático", btn="Abrir", help="Sistema > Automático"),
            dict(id="scene_weight", kind="seg", label="Com que frequência", opts=[("Rara", 0), ("Normal", 1), ("Frequente", 2)],
                 help="O quanto o Automático gosta desta cena", enabled=lambda c: c["scene_auto"]),
            dict(id="scene_genre", kind="seg", label="Gênero", opts=GENRE_OPTS, help="O Automático prefere com este estilo"),
            dict(id="undo", kind="action", label="Desfazer", btn="Desfazer", help="Volta a última mudança  ·  Ctrl+Z"),
            dict(id="scene_more", kind="note", label="Duplicar e apagar ficam no ••• da cena, na lista", help=""),
        ]))
    return _accordion(left, right, item), []                                     # (Salvar, Descartar and Galeria are in the strip over the editor)                             # one column, in every width: the page of an item opens right under its row


def _accordion(stack, page, item):
    """The stack cards with the page of the open item inserted under its row (the rows after it go on in a card of their own)."""
    out = []
    for title, rows in stack:
        k = next((i for i, r in enumerate(rows) if r.get("item") == item), -1)
        if k < 0:
            out.append((title, rows))
            continue
        out.append(("§" + title, rows[:k + 1]))                                  # "§": drawn inside one container with the page of the open item
        out += [("§§" + t, r) for t, r in page]                                  # "§§": a part of the page, inset and tinted
        if k + 1 < len(rows):
            out.append(("§", rows[k + 1:]))
        page = []
    return out + page


def stack_cards(cfg, item):
    """The left of the editor: back to all the scenes, the settings of the scene, and the six layers top first, each one with its switch."""
    rows = []
    for slot in STACK_ORDER:
        k = SLOT_ITEM[slot]
        name, state = _item_text(cfg, k)
        if k == 0:
            name, state = "Forma principal", name
        rows.append(dict(id=f"stk_{slot}", kind="item", item=k, tag=str(STACK_ORDER[::-1].index(slot) + 1), group="lay", label=name, help=state, sw="ly_" + slot))
    n6, s6 = _item_text(cfg, 6)
    n12, s12 = _item_text(cfg, 12)
    return [("CENA", [dict(id="stk_scene", kind="item", item=6, tag="C", group="sc", label=n6, help=s6),
                      dict(id="stk_links", kind="item", item=12, tag="L", group="sc", label=n12, help=s12)]), ("CAMADAS  ·  DE CIMA PARA BAIXO", rows)]


def links_cards(cfg):
    """The Ligações page: every number that moves with the music and every choice that alternates, with a way to stop each one."""
    mods, cyc = cfg.get("mods") or {}, cfg.get("cycles") or {}
    rows = [dict(id="unmod:" + k, kind="action", label="Música: " + NAMES.get(k, k), btn="Fixar", help=MOD.label(k, m)) for k, m in mods.items()]
    rows += [dict(id="uncyc:" + k, kind="action", label="Alterna: " + NAMES.get(k, k), btn="Uma só",
                  help=f"{len(c_['opts'])} escolhas  ·  troca a cada {MOD.WHEN[int(c_['when']) % len(MOD.WHEN)][0].lower()}") for k, c_ in cyc.items()]
    if not rows:
        rows = [dict(id="links_none", kind="note", label="Nada segue a música ainda", help="Toque em Fixo ao lado de um número, ou em Uma só ao lado de uma escolha")]
    return [("O QUE A MÚSICA CONTROLA NESTA CENA", rows)]


def scene_settings_cards(cfg, adv):
    """The settings of the whole scene (they move every layer at once): the colours, the camera and the rhythm, the music and the properties."""
    cards = [c for c in mandala_rows(dict(cfg, ed_sub=1)) if c[0] != "FUNDO"]
    if adv:
        cards += CAMERA + [("O AUTOMÁTICO ESCOLHE · CÂMERA", auto_rows("cam"))] + MOVEMENT + [("O AUTOMÁTICO ESCOLHE · MOVIMENTO", auto_rows("mv")), ("TROCAS AUTOMÁTICAS", auto_rows("sw")[:2])]
    else:
        cards += [("CÂMERA", [_preset_row(CAMERA[0][1][0], CAM_DESC)]), ("RITMO DA CENA", [_preset_row(MOVEMENT[0][1][0], MV_DESC)])]
    bloom = ("BRILHO", [_ROWS["bloom"], dict(id="expo", kind="slider", label="Exposição", lo=50, hi=200, step=10, unit="%", help="Quanto a imagem clareia")])
    cards += [("SOM", band_rows()), ("PISCADAS", flash_rows()), bloom] if adv else [("SOM", band_rows()[:1]), ("PISCADAS", flash_rows()[:1]), bloom]
    cards.append(("PROPRIEDADES DA CENA", [
        dict(id="scene_name", kind="text", label="Nome", help="Clique e digite  ·  Enter confirma"),
        dict(id="scene_auto_note", kind="note", label=lambda c: "Entra no Automático" if c["scene_auto"] else "Fora do Automático: só toca se você mandar", help="Marque ou desmarque em Sistema > Automático"),
            dict(id="goto:sys:2", kind="action", label="Mudar no Automático", btn="Abrir", help="Sistema > Automático"),
        dict(id="scene_weight", kind="seg", label="Com que frequência", opts=[("Rara", 0), ("Normal", 1), ("Frequente", 2)],
             help="O quanto o Automático gosta desta cena", enabled=lambda c: c["scene_auto"]),
        dict(id="scene_genre", kind="seg", label="Gênero", opts=GENRE_OPTS, help="O Automático prefere com este estilo"),
        dict(id="undo", kind="action", label="Desfazer", btn="Desfazer", help="Volta a última mudança  ·  Ctrl+Z"),
        dict(id="scene_more", kind="note", label="Duplicar e apagar ficam no ••• da cena, na galeria", help=""),
    ]))
    return cards


def slot_cards(cfg, slot, adv):
    """The page of one of the layers Fundo, Luzes, Partículas e rastro and Acabamento: what it has (with the one selected open below) and its own settings."""
    out = []
    if slot == "bg":
        bgr = [dict(id="scene_bg", kind="seg", label="Cor do fundo", opts=[("Do estilo", 0), ("Preto", 1), ("Branco", 2), ("Escolher", 3)],
                    help=lambda c: ["O fundo do estilo da cena", "Preto", "Branco", "Uma cor sua: ajuste abaixo"][int(c["scene_bg"]) % 4])]
        if int(cfg.get("scene_bg", 0)) == 3:
            bgr += [dict(id=k, kind="slider", label=lab, lo=0, hi=255, step=5, unit="", help="Da cor do fundo  ·  duplo clique restaura") for k, lab in (("scene_bgr", "Vermelho"), ("scene_bgg", "Verde"), ("scene_bgb", "Azul"))]
        out.append(("COR DO FUNDO", bgr))
    title = {"bg": "GRADIENTES", "lights": "LUZES", "parts": "PARTÍCULAS E RASTRO", "finish": "EFEITOS DE LENTE E TOM"}[slot]
    out.append((title, LY.list_items(cfg, slot)))
    layers = cfg.get("layers") or []
    i = int(cfg.get("ly_sel", 0))
    if 0 <= i < len(layers) and LY.SLOT_OF.get(layers[i].get("t")) == slot:
        out += LY.detail_cards(cfg)
    if slot == "finish":
        out += layer_cards(cfg, adv, bool(layers))[-2:-1]
    return out


def layer_cards(cfg, adv, has_layers):
    """The Camadas tab: the six layers of the scene (each one on or off), the effects of the stack, the Acabamento and the Sobreposição."""
    slots = [dict(id="ly_" + k, kind="toggle", label=name, help=help) for k, name, help in LY.SLOTS]
    out = [("CAMADAS DA CENA", slots)]
    if adv or has_layers:
        out += [("EFEITOS E FUNDOS", LY.list_items(cfg))] + LY.detail_cards(cfg)
    fin = lambda c: bool(c.get("ly_finish", True))
    acab = [dict(_ROWS[k], enabled=fin) for k in ("img_style", "img_pix", "fin_bright", "fin_contrast", "fin_sat", "fin_gamma", "fin_temp", "scr_vig", "fin_dither")]
    acab[1] = dict(acab[1], enabled=lambda c: fin(c) and c["img_style"] == 3)
    out.append(("ACABAMENTO", acab))
    ov = lambda c: bool(c.get("ly_over", False))
    out.append(("TEXTO E LOGO", [
        dict(id="ov_kind", kind="seg", label="O que mostra", opts=[("Texto", 0), ("Logo", 1)], enabled=ov,
             help=lambda c: "O texto abaixo" if c["ov_kind"] == 0 else "logo.png em Documentos\\AudioOrganism"),
        dict(id="ov_text", kind="text", label="Texto", help="Clique e digite", enabled=lambda c: ov(c) and c["ov_kind"] == 0),
        dict(id="ov_pos", kind="seg", label="Onde", opts=[("Canto", 0), ("Centro", 1), ("Embaixo", 2)], help="Em que parte da tela", enabled=ov),
        dict(id="ov_size", kind="slider", label="Tamanho", lo=4, hi=40, step=1, unit="%", help="Altura na tela", enabled=ov),
        dict(id="ov_op", kind="slider", label="Opacidade", lo=10, hi=100, step=5, unit="%", help="Quanto aparece", enabled=ov),
        dict(id="ov_react", kind="seg", label="Reage a", opts=[("Nada", 0), ("Batida", 1), ("Energia", 2)], help="O que faz ele pulsar", enabled=ov),
    ]))
    return out


def scene_rows(cfg, view="gallery", wide=False):
    return scene_layout(cfg, view, wide)[0]


def mandala_rows(cfg):
    """The Aparência and Cores tabs: Modelo, Estilo, Simetrias and Formas (the mandala), and the colours."""
    sub = int(cfg.get("ed_sub", 0))
    adv = bool(cfg.get("advanced", False))
    vis = int(cfg.get("scene_visual", 1))
    subs = (ED_SUBS if adv else [o for o in ED_SUBS if o[1] in (0, 2, 3)]) if vis == 1 else []       # only the mandala has shaders, mirrors and shapes; the shapes are advanced
    if sub not in [v for _, v in subs] + [1]:
        sub = 0
    cards = [("", [dict(id="ed_sub", kind="seg", label="", opts=subs, help="")])] if len(subs) > 1 and sub != 1 else []
    if sub == 0:
        cards.append(("O QUE APARECE", [dict(id="scene_visual", kind="dd", label="Tipo de imagem", opts=[(n, i) for i, (n, _, _) in enumerate(SC.VISUALS)],
                                             help=lambda c: SC.VISUALS[max(0, min(int(c["scene_visual"]), len(SC.VISUALS) - 1))][1])]))
        if vis >= 2:
            names = SC.VISUALS[min(vis, len(SC.VISUALS) - 1)][2]
            rows = []
            if vis == 9:
                rows += [dict(id="gen_text", kind="text", label="Texto", help="O que aparece no meio da tela  ·  clique e digite"),
                         dict(id="gen_pick", kind="action", label="Imagem", btn="Escolher…", help=lambda c: (os.path.basename(c.get("gen_img", "")) or "Sem imagem: vale o texto") if c.get("gen_img") else "Opcional: um logo (PNG com fundo transparente fica melhor)"),
                         dict(id="gen_clear", kind="action", label="Tirar a imagem", btn="Tirar", help="Volta a mostrar o texto", enabled=lambda c: bool(c.get("gen_img")))]
            for i, (lab, hp) in enumerate(names):
                rows.append(dict(id="gen_p%d" % (i + 1), kind="slider", label=lab, lo=0, hi=100, step=5, unit="%", help=hp + "  ·  duplo clique restaura"))
            cards.append(("AJUSTES  ·  " + SC.VISUALS[min(vis, len(SC.VISUALS) - 1)][0].upper(), rows))
        if vis == 1:
            cards += [
                ("MODELO DA MANDALA", [dict(id="scene_preset", kind="radio", tile=("preset", i), value=i, label=n, help="") for i, n in enumerate(SC.PRESET_NAMES)]),
                ("FORMA", [] if not adv else [
                    dict(id="m_base", kind="seg", label="Base de cores", opts=[(n, i) for i, n in enumerate(SC.BASE_NAMES)],
                         help="As cores do modelo"),
                    dict(id="m_psx", kind="slider", label="Largura do painel", lo=20, hi=100, step=2, unit="%", help="Metade da largura de cada painel"),
                    dict(id="m_psy", kind="slider", label="Altura do painel", lo=3, hi=60, step=1, unit="%", help="Metade da altura de cada painel"),
                    dict(id="m_pox", kind="slider", label="Afastamento horizontal", lo=10, hi=100, step=2, unit="%", help="Distância de cada camada ao centro"),
                    dict(id="m_poy", kind="slider", label="Afastamento vertical", lo=5, hi=60, step=2, unit="%", help="Quanto cada camada sobe ou desce"),
                    dict(id="m_decay", kind="slider", label="Encolhimento por camada", lo=60, hi=96, step=1, unit="%", help="Tamanho da próxima camada"),
                    dict(id="m_thick", kind="slider", label="Espessura", lo=30, hi=300, step=10, unit="%", help="Quão grossas são as faces"),
                    dict(id="m_funnel", kind="slider", label="Profundidade mínima do túnel", lo=0, hi=100, step=5, unit="%", help="O túnel nunca fecha abaixo disto"),
                    dict(id="m_round", kind="seg", label="Cantos", opts=[("Retos", 0), ("Alternados", 1), ("Arredondados", 2)],
                         help="Alternados: um painel sim, outro não"),
                    dict(id="m_glass", kind="slider", label="Vidro das faces (opacidade)", lo=20, hi=100, step=5, unit="%", help="100% sólido, 40% vitral"),
                ]),
            ]
    elif sub == 1:
        bgr = [dict(id="scene_bg", kind="seg", label="Cor do fundo", opts=[("Do estilo", 0), ("Preto", 1), ("Branco", 2), ("Escolher", 3)],
                    help=lambda c: ["O fundo do estilo da cena", "Preto", "Branco", "Uma cor sua: ajuste abaixo"][int(c["scene_bg"]) % 4])]
        if int(cfg.get("scene_bg", 0)) == 3:
            bgr += [dict(id=k, kind="slider", label=lab, lo=0, hi=255, step=5, unit="", help="Da cor do fundo  ·  duplo clique restaura") for k, lab in (("scene_bgr", "Vermelho"), ("scene_bgg", "Verde"), ("scene_bgb", "Azul"))]
        cards += [("FUNDO", bgr)]
        crs = color_rows(cfg)
        ed_btn = dict(id="pal_open", kind="action", label="Editar as cores da paleta", btn="Fechar" if cfg.get("pal_open") else "Editar cores",
                      help="Renomear, duplicar, apagar e mexer em cada cor")
        cards += crs[:1] + [("", [ed_btn])] + (crs[1:] if cfg.get("pal_open") else [])
    elif sub == 2:
        if adv:
            cards += [("AUTOMÁTICO", [dict(id="scene_pref", kind="seg", label="Favorecido", opts=[(SP.KIND_NAMES[k], k) for k in SP.ORDER], help="",
                                           enabled=lambda c: c["scene_shader"] == 0)])]
            cards += shader_rows(cfg)
        else:
            cards += shader_rows(cfg)[:1]                                           # just the choice: Automático or one of the styles
    elif sub == 3:
        cards.append(("SIMETRIAS  ·  O PREVIEW MOSTRA O SETOR REAL E OS ESPELHOS", [dict(id="m_symnone", kind="toggle", label="Nenhum", help="Uma camada sem espelho, como é desenhada")]
                      + [dict(id="m_sym%d" % i, kind="toggle", label=SC.SYM_LABELS[i], help="O Automático pode usar este espelho") for i in range(SC.SYM_COUNT)]))
    else:
        cards += SHAPES + [("TROCAS AUTOMÁTICAS", auto_rows("sw")[2:])]
    cards = [c for c in cards if c[1]]
    if len(cards) > 1 and cards[0][0] == "" and cards[0][1][0]["id"] == "ed_sub":           # the sub-tabs open the first card instead of a card of their own
        cards = [(cards[1][0], cards[0][1] + cards[1][1])] + cards[2:]
    return cards

def shader_rows(cfg):
    """The Shaders tab: which shader the scene uses, the list, and the editor of the selected preset (the three numbers are named by the kind)."""
    shs = cfg.get("shaders") or DEFAULTS["shaders"]
    radios = [dict(id="scene_shader", kind="radio", value=0, label="Automático",
                   help="Muda pelas partes da música, entre os estilos que o Automático pode escolher")]
    for i, sh in enumerate(shs):
        radios.append(dict(id="scene_shader", kind="radio", value=i + 1, label=sh["name"], help=("" if sh["name"] == SP.KIND_NAMES[sh["kind"]] else SP.KIND_NAMES[sh["kind"]]) + ("" if sh.get("auto", True) else (" · " if sh["name"] != SP.KIND_NAMES[sh["kind"]] else "") + "fora do Auto")))
    ed = cfg.get("shd_edit", 0)
    sh = shs[ed] if 0 <= ed < len(shs) else shs[0]
    kind = sh["kind"]
    rows = [dict(id="shd_name", kind="text", label="Nome", help="Clique e digite  ·  Enter confirma"),
            dict(id="shd_kind", kind="seg", label="Tipo", opts=[(SP.KIND_NAMES[k], k) for k in SP.ORDER], help=""),
            dict(id="shd_auto", kind="toggle", label="Pode ser escolhido pelo Automático", help="Sem isto o Automático nunca usa este estilo")]
    for key, lab in zip(("shd_p1", "shd_p2", "shd_p3"), SP.labels(kind)):
        if lab:
            rows.append(dict(id=key, kind="slider", label=lab[0], lo=20, hi=300, step=10, unit="%", help=lab[1]))
    if kind == 7:
        rows.append(dict(id="shd_duo", kind="seg", label="Cores do duotom", opts=[("Da paleta", 0), ("Fixas", 1)], help="De onde vêm a cor escura e a clara"))
        if cfg.get("shd_duo", 0) == 1:
            rows.append(dict(id="shd_item", kind="swatches", label="Cor", help="Escura e clara", items=[sh["duo_dark"], sh["duo_light"]]))
            for key, lab in (("shd_r", "Vermelho"), ("shd_g", "Verde"), ("shd_b", "Azul")):
                rows.append(dict(id=key, kind="slider", label=lab, lo=0, hi=255, step=5, unit="", help="Da cor selecionada"))
    return [("ESTILO DA CENA", radios), ("LISTA", [
        dict(id="shd_new", kind="action", label="Novo shader", btn="Duplicar", help="Cria uma cópia do shader selecionado para você mexer"),
        dict(id="shd_delete", kind="action", label="Apagar shader", btn="Apagar", help="As cenas dele voltam ao Automático",
             enabled=lambda c: len(c.get("shaders", [])) > 1),
        dict(id="shd_factory", kind="action", label="Shaders de fábrica", btn="Restaurar", help="Volta aos sete shaders que vêm com o programa"),
    ]), (f"EDITANDO  ·  {sh['name'].upper()}", rows)]


def color_rows(cfg):
    """The Cores tab: which palette the scene uses, the list of palettes, and the editor of the selected palette."""
    pls = cfg.get("palettes") or DEFAULTS["palettes"]
    radios = [dict(id="scene_palette", kind="radio", tile=("pal", 0), value=0, label="Cores do modelo", help="As cores que vêm com o modelo da cena")]
    for i, pl in enumerate(pls):
        radios.append(dict(id="scene_palette", kind="radio", tile=("pal", i + 1), value=i + 1, label=pl["name"], help=f"{len(pl['colors'])} cores · {len(pl['bgs'])} fundos"))
    ed = cfg.get("pal_edit", 0)
    pal = pls[ed] if 0 <= ed < len(pls) else pls[0]
    its = PAL.items(pal)
    return [("PALETA DA CENA", radios), ("LISTA", [
        dict(id="pal_new", kind="action", label="Nova paleta", btn="Duplicar", help="Cria uma cópia da paleta selecionada para você mexer"),
        dict(id="pal_delete", kind="action", label="Apagar paleta", btn="Apagar", help="As cenas dela voltam às do modelo",
             enabled=lambda c: len(c.get("palettes", [])) > 1),
        dict(id="pal_factory", kind="action", label="Paletas de fábrica", btn="Restaurar", help="Volta às seis paletas que vêm com o programa"),
    ]), (f"EDITANDO  ·  {pal['name'].upper()}", [
        dict(id="pal_name", kind="text", label="Nome", help="Clique e digite  ·  Enter confirma"),
        dict(id="pal_item", kind="swatches", label="Cor selecionada", help="Clique numa cor", items=[c for _, c in its]),
        dict(id="pal_r", kind="slider", label="Vermelho", lo=0, hi=255, step=5, unit="", help="Da cor selecionada"),
        dict(id="pal_g", kind="slider", label="Verde", lo=0, hi=255, step=5, unit="", help="Da cor selecionada"),
        dict(id="pal_b", kind="slider", label="Azul", lo=0, hi=255, step=5, unit="", help="Da cor selecionada"),
        dict(id="pal_add", kind="action", label="Adicionar cor", btn="Adicionar", help="Mais uma cor para a paleta sortear"),
        dict(id="pal_add_bg", kind="action", label="Adicionar fundo", btn="Adicionar", help="Mais um fundo possível"),
        dict(id="pal_remove", kind="action", label="Remover a selecionada", btn="Remover", help="Tira a cor ou o fundo selecionado (fica pelo menos um de cada)",
             enabled=lambda c: True),
    ])]


GFX_CARDS = [_card("ATALHO DE QUALIDADE", "preset"), _card("NITIDEZ E FLUIDEZ", "res", "dynres", "fps_out", "dynmin", "rrate"),
             _card("QUANTIDADE DE DETALHES", "detail", "steps", "dist"), _card("BRILHO", "bloomq", "bloomres"),
             _card("NITIDEZ", "sharp"),
             _card("EFEITOS PESADOS", "fx_glass", "fx_bloom", "fx_trail", "fx_parts", "fx_none")]
OUT_CARDS = []                                   # the comfort limits and the finish live in each scene now (Estúdio), not in the system page
SCREEN_CARD = _card("FORMATO", "scr_aspect", "scr_zoom", "scr_mirror")
TABS = [
    ("Palco", []),
    ("Estúdio", scene_rows(DEFAULTS)),
    ("Sistema", sys_layout(DEFAULTS, 0, False)[0]),
]
TAB_LIVE, TAB_SCENES, TAB_SYS = 0, 1, 2
PV_H = 184
NAMES = {"scene_bgr": "Vermelho do fundo", "scene_bgg": "Verde do fundo", "scene_bgb": "Azul do fundo", "gen_p1": "Ajuste 1", "gen_p2": "Ajuste 2", "gen_p3": "Ajuste 3", "gen_text": "Texto", "gen_img": "Imagem", "scene_visual": "Tipo de imagem", "fullscreen": "Tela cheia", "vsync": "VSync", "fps_cap": "Limite de FPS", "strobe": "Flashes",
         "bursts": "Rajadas", "bloom": "Brilho das luzes", "react": "Reatividade", "effect": "Cena", "res": "Resolução",
         "backend": "Backend", "preset": "Qualidade", "steps": "Precisão das bordas", "shadows": "Sombras", "reflect": "Reflexos",
         "ao": "Oclusão", "bloomq": "Brilho", "aa_mode": "Suavização", "sharp": "Nitidez", "bloomres": "Resolução do brilho", "dist": "Profundidade", "bounce": "Reflexos em cadeia", "rrate": "Quadros desenhados", "dynmin": "Escala mínima", "gpu": "Placa de vídeo", "panel_hz": "Painel", "panel_view": "Monitor do painel", "panel_fps": "FPS do painel", "fx_tone": "Mapa de tons", "fx_look": "Predefinição de lente", "fx_ca_atk": "Ataque", "fx_ca_rel": "Soltura", "fx_ca_thr": "Limiar", "fx_ca_gain": "Sensibilidade", "fx_ca_inv": "Inverter", "fx_ca_curve": "Curva", "fx_ca_mix": "Mistura", "fx_ca_blur": "Desfoque do efeito", "fx_edge_atk": "Ataque", "fx_edge_rel": "Soltura", "fx_edge_thr": "Limiar", "fx_edge_gain": "Sensibilidade", "fx_edge_inv": "Inverter", "fx_edge_curve": "Curva", "fx_edge_mix": "Mistura", "fx_fl_atk": "Ataque", "fx_fl_rel": "Soltura", "fx_fl_thr": "Limiar", "fx_fl_gain": "Sensibilidade", "fx_fl_inv": "Inverter", "fx_fl_curve": "Curva", "fx_fl_mix": "Mistura", "fx_fl_blur": "Desfoque do efeito", "fx_gr_atk": "Ataque", "fx_gr_rel": "Soltura", "fx_gr_thr": "Limiar", "fx_gr_gain": "Sensibilidade", "fx_gr_inv": "Inverter", "fx_gr_curve": "Curva", "fx_gr_mix": "Mistura", "fx_gr_blur": "Desfoque do efeito", "fx_fb_src": "segue", "fx_fb_amt": "Quanto segue", "fx_fb_atk": "Ataque", "fx_fb_rel": "Soltura", "fx_fb_thr": "Limiar", "fx_fb_gain": "Sensibilidade", "fx_fb_inv": "Inverter", "fx_fb_curve": "Curva", "fx_fb_mix": "Mistura", "fx_fb_blur": "Desfoque do efeito", "fx_ca_dir": "Direção da aberração", "fx_ca_start": "Início da aberração", "fx_ca_src": "Aberração segue", "fx_ca_amt": "Quanto segue", "fx_edge_r": "Centro nítido", "fx_edge_shape": "Formato do desfoque", "fx_edge_src": "Desfoque segue", "fx_edge_amt": "Quanto segue", "fx_fl_len": "Comprimento do raio", "fx_fl_col": "Cor do reflexo", "fx_fl_n": "Fantasmas", "fx_fl_src": "Reflexo segue", "fx_fl_amt": "Quanto segue", "fx_gr_size": "Tamanho do grão", "fx_gr_where": "Onde pesa o grão", "fx_gr_color": "Cor do grão", "fx_gr_fps": "Ritmo do grão", "fx_gr_src": "Grão segue", "fx_gr_amt": "Quanto segue", "fx_fb": "Rastro", "fx_fbzoom": "Zoom do rastro", "fx_fbrot": "Giro do rastro", "fx_fbhue": "Cor do rastro", "fx_ca": "Aberração cromática", "fx_edge": "Desfoque nas bordas", "fx_flare": "Reflexo de lente", "fx_grain": "Grão de filme", "fx_part": "Partículas", "fx_pmode": "Movimento das partículas", "fx_psize": "Tamanho das partículas", "abuf": "Buffer de áudio", "detail": "Densidade", "rt": "Iluminação",
         "style": "Estilo", "camera": "Câmera", "cam_orbit": "Órbita", "cam_roll": "Giro", "cam_shake": "Tremor", "cam_punch": "Soco", "cam_funnel": "Funil", "cam_fov_min": "FOV mínimo", "cam_fov_max": "FOV máximo", "cam_fov_var": "Variação do FOV", "cam_sync": "Sincronia", "sh_when": "Troca de forma", "sh_mix": "Distribuição", "sh_morph": "Forma vira outra", "ctrans": "Cor vira outra", "lay_trans": "Camadas entram e saem", "scene_fade": "Troca de cena", "strobe": "Strobe no build-up", "adev": "Entrada de áudio", "link_riser": "Riser antecipa o build-up", "link_vocal": "Voz acalma os flashes", "remote_osc": "OSC", "remote_midi": "MIDI", "phone_view": "Ver no celular", "monitor": "Monitor da imagem", "react_bass": "Graves", "react_mid": "Médios", "react_high": "Agudos", "expo": "Exposição", "scene_weight": "Chance no sorteio", "fl_start": "Strobe começa", "fl_roll": "Flash nos rolls", "fl_drop": "Flash do drop", "fl_len": "Duração dos flashes", "fl_mode": "Efeito do flash", "auto_shape": "Auto: formas", "sh_0": "Painéis (padrão)", "sh_2": "Cubo", "sh_16": "Cuboide", "sh_1": "Esfera", "sh_3": "Cilindro", "sh_4": "Cone", "sh_15": "Cone truncado", "sh_9": "Toro", "sh_10": "Anel", "sh_14": "Meia-esfera", "sh_5": "Pirâmide quadrada", "sh_6": "Pirâmide hexagonal", "sh_7": "Prisma triangular", "sh_8": "Prisma hexagonal", "sh_17": "Prisma pentagrâmico", "sh_11": "Octaedro", "sh_12": "Dodecaedro", "sh_13": "Icosaedro", "sh_18": "Buckyball", "auto_cam_orbit": "Auto: órbita", "auto_cam_roll": "Auto: giro", "auto_cam_shake": "Auto: tremor", "auto_cam_punch": "Auto: soco", "auto_cam_funnel": "Auto: funil", "auto_cam_fov": "Auto: FOV", "auto_cam_sync": "Auto: sincronia", "auto_mv_speed": "Auto: velocidade", "auto_mv_rot": "Auto: rotação", "auto_mv_pulse": "Auto: pulso", "auto_mv_cuts": "Auto: cortes", "auto_mv_inertia": "Auto: inércia", "auto_cuts": "Auto: cortes de cor", "auto_vars": "Auto: cor por elemento",  "movement": "Movimento", "mv_speed": "Velocidade", "mv_inertia": "Inércia", "mv_rot": "Rotação", "mv_dir": "Direção", "mv_pulse": "Pulso", "mv_one": "Pulso só na batida 1", "mv_cuts": "Trocas na batida", "mblur": "Obturador", "auto_update": "Verificação de atualização", "mblur_fps": "Quadros de referência", "dynres": "Resolução dinâmica", "fps_out": "FPS de saída", "scene_palette": "Paleta", "shd_name": "Nome do shader", "shd_kind": "Tipo", "shd_p1": "Ajuste 1", "shd_p2": "Ajuste 2", "shd_p3": "Ajuste 3", "shd_auto": "Entra no sorteio de shaders", "shd_duo": "Cores do duotom", "shd_item": "Cor", "shd_r": "Vermelho", "shd_g": "Verde", "shd_b": "Azul", "pal_name": "Nome da paleta", "pal_item": "Cor selecionada", "pal_r": "Vermelho", "pal_g": "Verde", "pal_b": "Azul", "m_sym0": "Espelho 4x", "m_sym1": "Espelho lateral", "m_sym2": "Radial 6", "m_sym3": "Radial 8", "m_sym4": "Radial 5", "m_sym5": "Diagonal", "m_sym6": "Espelho vertical", "m_sym7": "Radial 12", "m_symnone": "Nenhum", "scene_name": "Nome", "scene_visual": "Tipo de imagem", "scene_bg": "Fundo", "scene_sec": "Seção", "bg_light": "Luzes de fundo", "bg_int": "Intensidade das luzes", "bg_col": "Cor das luzes", "bgc_src": "Cores do fundo", "bgc_dir": "Direção do fundo", "bgc_react": "Pulso do fundo", "bgc_trans": "Transição do fundo", "bgc_every": "Frequência do fundo", "bgc_item": "Cor do fundo", "bgc_r": "Vermelho", "bgc_g": "Verde", "bgc_b": "Azul", "bg_speed": "Velocidade das luzes", "scene_pref": "Shader favorecido", "scene_when": "Trocar de cena", "scene_every": "A cada", "scene_preset": "Preset", "scene_auto": "Entra no sorteio", "scene_genre": "Gênero", "scene_shader": "Shader", "m_base": "Base de cores", "m_psx": "Largura", "m_psy": "Altura", "m_pox": "Afastamento horizontal", "m_poy": "Afastamento vertical", "m_decay": "Encolhimento", "m_thick": "Espessura", "m_funnel": "Funil mínimo", "m_cuts": "Cortes", "m_round": "Cantos", "m_glass": "Vidro das faces"}
