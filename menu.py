"""Settings panel (mouse + keyboard) and persistent settings.

Design: six tabs (Cenas, Câmera, Movimento, Imagem, Gráficos, Ajustes), grouped in cards. Every option has a label, a one-line explanation and a
clearly stateful control: toggle, segmented choice or slider. Disabled controls say why. Keyboard focus is
always visible. Changes apply instantly and show a short confirmation.
"""
import json
import os
import time

import copy

import pygame

import palettes as PAL
import ui
import scenes as SC
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
            "auto_mv_inertia": True, "auto_scene": True, "auto_style": True, "auto_cuts": True, "auto_vars": True, "auto_shape": True,
            "sh_when": 0, "sh_mix": 0, "sh_morph": 2, "ctrans": 0,
            "sh_0": True, "sh_2": False, "sh_16": False, "sh_1": False, "sh_3": False, "sh_4": False, "sh_15": False, "sh_9": False, "sh_10": False, "sh_14": False, "sh_5": False, "sh_6": False, "sh_7": False, "sh_8": False, "sh_17": False, "sh_11": False, "sh_12": False, "sh_13": False, "sh_18": False,
            # graphics (see PRESETS): render scale %, ray steps, ray-traced shadow / reflection / occlusion quality, lighting mode,
            # bloom levels, edge AA, panel density %, dynamic resolution and its FPS target
            "preset": 1, "res": 80, "steps": 60, "bloomq": 2, "aa_mode": 1, "detail": 75,
            "dynres": True, "fps_out": 60, "mblur": 90, "mblur_fps": 24, "auto_update": True,
            # more performance options: sharpening, bloom resolution, ray distance, render rate, lowest dynamic scale, panel refresh, GPU choice
            "sharp": 0, "bloomres": 0, "dist": 1, "rrate": 0, "dynmin": 40, "gpu": 0, "panel_view": 2, "wave_blend": 0}

_S0 = SC.starter_scenes()[0]
DEFAULTS.update({k: _S0[k] for k in SC.MANDALA_KEYS + SC.IDENTITY_KEYS})        # the working copy of the scene being edited (starts as the first)
DEFAULTS.update(scene_when=2, scene_every=30, scene_now=False, bg_light=0, bg_int=100, bg_speed=100)                          # how a scene change happens (see neon_director.update)
DEFAULTS["scene_sec"] = 0                                                         # section of the scene editor (Visual, Fundo, Cores, ...)
DEFAULTS["scenes"] = SC.starter_scenes()                                          # the scene presets (see scenes.py)
DEFAULTS["scene_edit"] = 0                                                        # index of the scene being edited
DEFAULTS["shaders"] = SP.factory()                                              # the shader presets (see shaderpresets.py)
DEFAULTS.update(shd_v=1, shd_edit=0, shd_name="3D", shd_kind=1, shd_p1=100, shd_p2=100, shd_p3=100, shd_auto=True, shd_duo=0, shd_item=0, shd_r=10, shd_g=0, shd_b=40)
DEFAULTS["palettes"] = PAL.factory()                                              # the palette presets (see palettes.py)
DEFAULTS.update(pal_edit=0, pal_item=0, pal_name="Neon", pal_r=0, pal_g=0, pal_b=0)   # the palette / swatch being edited (working copy)

# graphics presets; any manual change of one of these options switches the preset to "Personalizado"
GFX_KEYS = ("res", "steps", "bloomq", "aa_mode", "detail", "mblur", "mblur_fps", "sharp", "bloomres", "dist")
PRESETS = [
    ("Baixo",  dict(res=60,  steps=48,  bloomq=1, aa_mode=0, detail=55,  mblur=0, mblur_fps=24, sharp=1, bloomres=1, dist=0)),
    ("Médio",  dict(res=80,  steps=60,  bloomq=2, aa_mode=1, detail=75,  mblur=90, mblur_fps=24, sharp=0, bloomres=0, dist=1)),
    ("Alto",   dict(res=100, steps=72,  bloomq=3, aa_mode=3, detail=100, mblur=180, mblur_fps=24, sharp=0, bloomres=0, dist=1)),
    ("Ultra",  dict(res=100, steps=110, bloomq=4, aa_mode=4, detail=100, mblur=270, mblur_fps=24, sharp=0, bloomres=0, dist=2)),
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


def load_cfg():
    cfg = fresh()
    data_style_v = 6
    data = {}
    try:
        with open(PATH, encoding="utf-8") as f:
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
    except Exception:
        pass
    # scene presets: the stored list, or the six that ship (with the camera / movement / shapes the person already had)
    extras = {k: cfg[k] for k in SC.CAMERA_KEYS + SC.MOVEMENT_KEYS + SC.SHAPE_KEYS + SC.REACT_KEYS + SC.BG_KEYS if k in cfg}
    lst = data.get("scenes") if isinstance(data, dict) else None
    if isinstance(lst, list) and lst and all(SC.valid(x) for x in lst):
        base_ = SC.mandala_scene(0, extras)
        for sc_ in lst:
            sc_.setdefault("scene_preset", SC.preset_of(sc_))
            for k, v in base_.items():
                sc_.setdefault(k, v)
        if not any(sc_.get("scene_visual", 1) == 0 for sc_ in lst):          # the scene with nothing drawn is always available
            lst.append(SC.none_scene(extras))
        cfg["scenes"] = lst
    else:
        cfg["scenes"] = SC.starter_scenes(extras)
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


# ------------------------------------------------------------------ design tokens
BG = (10, 9, 22)
SURFACE = (20, 18, 42)
SURFACE2 = (32, 30, 62)
BORDER = (52, 48, 96)
TEXT = (238, 240, 255)
DIM = (160, 168, 208)          # >= 4.5:1 on SURFACE
ACCENT = (255, 90, 210)
ACCENT2 = (80, 220, 255)
OK = (110, 235, 170)
DANGER = (255, 120, 150)
ON_ACCENT = (24, 8, 32)


def dimmed(c, f=0.45):
    return tuple(int(BG[i] + (c[i] - BG[i]) * f) for i in range(3))


FPS_OPTS = [("24", 24), ("30", 30), ("60", 60), ("90", 90), ("120", 120), ("144", 144), ("240", 240)]
TARGET_OPTS = [("30", 30), ("60", 60), ("90", 90), ("120", 120), ("144", 144)]
STROBE_OPTS = [("Desligado", 0), ("Suave", 1), ("Completo", 2)]
QUAL4_OPTS = [("Desligado", 0), ("Baixa", 1), ("Média", 2), ("Alta", 3)]
STYLE_OPTS = [("Normal", 0), ("Anime", 1)]
LIGHT_OPTS = [("Rápida", 0), ("Ray tracing", 1)]
AA_OPTS = [("Desligado", 0), ("Bordas", 1), ("FXAA", 2), ("MSAA 2x", 3), ("MSAA 4x", 4), ("MSAA 8x", 5)]
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
    ("PREDEFINIÇÃO", [
        dict(id="preset", kind="seg", label="Qualidade gráfica", opts=PRESET_OPTS,
             help=lambda c: "Ajusta várias opções de uma vez" if c["preset"] != CUSTOM else "Opções alteradas por você"),
    ]),
    ("TELA", [
        dict(id="fullscreen", kind="toggle", label="Tela cheia", chip="F",
             help="Duplo clique na imagem também alterna"),
        dict(id="vsync", kind="toggle", label="Sincronia vertical (VSync)", chip="V",
             help="Ligado: imagem sem rasgos, limitada ao monitor"),
    ]),
    ("DESEMPENHO", [
        dict(id="res", kind="slider", label="Escala de resolução", lo=25, hi=100, step=5, unit="%",
             help="Menor = muito mais FPS, imagem mais suave  ·  duplo clique restaura"),
        dict(id="fps_out", kind="seg", label="FPS de saída", opts=FPS_OPTS,
             help=lambda c: "Limite e meta da resolução dinâmica" + (" · VSync" if c["vsync"] else "")),
        dict(id="dynres", kind="toggle", label="Resolução dinâmica",
             help="Baixa a resolução sozinha quando o FPS cai do alvo"),
        dict(id="detail", kind="slider", label="Densidade de painéis", lo=30, hi=100, step=5, unit="%",
             help="Menos camadas na cena: mais FPS  ·  duplo clique restaura"),
        dict(id="dynmin", kind="slider", label="Escala mínima (dinâmica)", lo=25, hi=90, step=5, unit="%",
             help="Até onde a resolução dinâmica pode descer", enabled=lambda c: c["dynres"]),
        dict(id="dist", kind="seg", label="Distância de render", opts=[("Curta", 0), ("Normal", 1), ("Longa", 2)],
             help=lambda c: ["Corta as camadas mais fundas: mais leve", "Todas as camadas", "Raios vão mais longe"][c["dist"]]),
        dict(id="rrate", kind="seg", label="Taxa de renderização", opts=[("Total", 0), ("Metade", 1), ("Um terço", 2)],
             help=lambda c: ["Desenha todos os quadros", "1 quadro a cada 2: GPU pela metade", "1 a cada 3: o mais leve, mais picado"][c["rrate"]]),
        dict(id="steps", kind="slider", label="Passos do raio", lo=24, hi=160, step=8, unit="",
             help="Mais passos = bordas mais corretas, mais peso"),
    ]),
    ("ILUMINAÇÃO", [
    ]),
    ("IMAGEM", [
        dict(id="bloomq", kind="seg", label="Qualidade do brilho", opts=BLOOM_OPTS,
             help="Camadas do halo: mais = mais suave"),
        dict(id="bloomres", kind="seg", label="Resolução do brilho", opts=[("Metade", 0), ("Quarto", 1), ("Oitavo", 2)],
             help="Base do halo: menor = mais leve"),
        dict(id="bloom", kind="slider", label="Intensidade do brilho", lo=0, hi=200, step=10, unit="%",
             help="Força do halo  ·  duplo clique restaura"),
        dict(id="mblur", kind="slider", label="Motion blur: ângulo do obturador", lo=0, hi=720, step=15, unit="°",
             help="0° desligado  ·  180° cinema  ·  360° aberto"),
        dict(id="mblur_fps", kind="seg", label="Quadros de referência do blur", opts=[("24", 24), ("30", 30), ("48", 48), ("60", 60)],
             help=lambda c: f"Obturador aberto por {c['mblur'] / 360.0 / c['mblur_fps'] * 1000:.0f} ms ({c['mblur']}° a {c['mblur_fps']} quadros)" if c["mblur"] else "Ligue o blur para usar",
             enabled=lambda c: c["mblur"] > 0),
        dict(id="aa_mode", kind="seg", label="Modo", opts=AA_OPTS,
             help=lambda c: ["Sem suavização", "Cobertura nas bordas",
                             "Filtro sobre a imagem pronta", "2 amostras por pixel nas bordas",
                             "4 amostras por pixel nas bordas", "8 amostras nas bordas: o mais pesado"][c["aa_mode"]]),
        dict(id="sharp", kind="seg", label="Nitidez", opts=[("Desligada", 0), ("Leve", 1), ("Média", 2), ("Forte", 3)],
             help="Realça detalhes: ajuda em resolução baixa"),
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
        dict(id="strobe", kind="seg", label="Flashes e strobe", chip="S", opts=STROBE_OPTS,
             help="Completo pisca rápido, no ritmo da música"),
        dict(id="bursts", kind="toggle", label="Rajadas de 1/4 de tempo",
             help=lambda c: "Piscadas rápidas ocasionais no ritmo" if c["strobe"] == 2 else "Disponível só em Flashes: Completo",
             enabled=lambda c: c["strobe"] == 2),
        dict(id="react", kind="slider", label="Reatividade ao som", lo=25, hi=200, step=25, unit="%",
             help="Quanto a imagem reage à música  ·  duplo clique restaura"),
    ]),
    ("SISTEMA", [
        dict(id="backend", kind="seg", label="Backend gráfico", opts=BACKEND_OPTS,
             help="Vulkan ou Direct3D 12  ·  vale após reiniciar"),
        dict(id="gpu", kind="seg", label="Placa de vídeo", opts=[("Alto desempenho", 0), ("Economia", 1)],
             help="Após reiniciar; Economia = GPU integrada"),
        dict(id="wave_blend", kind="seg", label="Onda do Ao vivo", opts=[("Transparente", 0), ("Sólida", 1)],
             help=lambda c: "Camadas misturadas: dá para ver o que está atrás" if c["wave_blend"] == 0 else "Camadas sólidas, uma sobre a outra"),
        dict(id="auto_update", kind="toggle", label="Verificar atualizações ao abrir",
             help="Consulta o GitHub em segundo plano; só baixa se você clicar em Atualizar"),
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
             help=lambda c: "Muda pela música" if c["camera"] == CAM_AUTO else ("Ajustado por você" if c["camera"] == CAM_MANUAL else "Preenche os controles")),
    ]),
    ("MOVIMENTO", [
        dict(id="cam_orbit", kind="seg", label="Órbita", opts=[("Parada", 0), ("Lenta", 1), ("Média", 2), ("Ampla", 3)],
             help="A câmera passeia ao redor da imagem", enabled=_cam_on("orbit")),
        dict(id="cam_roll", kind="seg", label="Giro", opts=[("Parado", 0), ("Balanço", 1), ("Contínuo", 2)],
             help="Inclina de lado a lado ou gira", enabled=_cam_on("roll")),
        dict(id="cam_shake", kind="seg", label="Tremor no kick", opts=[("Nenhum", 0), ("Leve", 1), ("Forte", 2)],
             help="A câmera treme a cada batida", enabled=_cam_on("shake")),
        dict(id="cam_punch", kind="seg", label="Soco no kick", opts=[("Nenhum", 0), ("Leve", 1), ("Forte", 2)],
             help="A câmera avança um pouco a cada batida", enabled=_cam_on("punch")),
        dict(id="cam_funnel", kind="seg", label="Funil", opts=[("Desligado", 0), ("Suave", 1), ("Normal", 2), ("Forte", 3)],
             help="Entra nas camadas em build-ups e drops", enabled=_cam_on("funnel")),
    ]),
    ("RITMO", [
        dict(id="cam_sync", kind="seg", label="Sincronia com o ritmo", opts=[("Livre", 0), ("No compasso", 1), ("Na frase", 2)],
             help=lambda c: ("Os movimentos seguem o tempo, não o relógio" if c["cam_sync"] else "Os movimentos têm ritmo próprio"), enabled=_cam_on("sync")),
    ]),
    ("LENTE", [
        dict(id="cam_fov_min", kind="slider", label="FOV mínimo", lo=30, hi=140, step=5, unit="°",
             help="Lente mais fechada: o ângulo nunca fica abaixo disto", enabled=_cam_on("fov")),
        dict(id="cam_fov_max", kind="slider", label="FOV máximo", lo=30, hi=140, step=5, unit="°",
             help="Lente mais aberta: o ângulo nunca passa disto", enabled=_cam_on("fov")),
        dict(id="cam_fov_var", kind="seg", label="Variação do FOV", opts=[("Fixo", 0), ("Respira", 1), ("Pela música", 2)],
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
        dict(id="sh_morph", kind="seg", label="Transformação", opts=[("Corte seco", 0), ("Rápida", 1), ("Suave", 2), ("Lenta", 3)],
             help=lambda c: ["A forma troca de uma vez", "A forma vira outra em 0,35 s", "A forma vira outra em 0,9 s", "A forma vira outra em 2 s"][c["sh_morph"]]),
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
             help=lambda c: "Muda pela música" if c["movement"] == MV_AUTO else ("Ajustado por você" if c["movement"] == MV_MANUAL else "Preenche os controles")),
    ]),
    ("VELOCIDADE", [
        dict(id="mv_speed", kind="seg", label="Velocidade geral", opts=[("Lenta", 0), ("Normal", 1), ("Rápida", 2), ("Pela música", 3)],
             help="Ritmo do fluxo e da rotação", enabled=lambda c: _mv_on("speed")(c)),
        dict(id="mv_inertia", kind="seg", label="Inércia", opts=[("Seca", 0), ("Normal", 1), ("Fluida", 2)],
             help=lambda c: ("Responde na hora, nervoso" if c["mv_inertia"] == 0 else "Equilibrada" if c["mv_inertia"] == 1 else "Suaviza tudo, como em câmera lenta"), enabled=lambda c: _mv_on("inertia")(c)),
    ]),
    ("CAMADAS", [
        dict(id="mv_rot", kind="seg", label="Rotação", opts=[("Parada", 0), ("Lenta", 1), ("Média", 2), ("Rápida", 3)],
             help="Velocidade com que as camadas giram", enabled=lambda c: _mv_on("rot")(c)),
        dict(id="mv_dir", kind="seg", label="Direção", opts=[("Horário", 0), ("Anti-horário", 1), ("Alternada", 2)],
             help="Alternada: vizinhas giram ao contrário", enabled=lambda c: (_mv_on("rot")(c)) and c["mv_rot"] > 0),
    ]),
    ("PULSO E TROCAS", [
        dict(id="mv_pulse", kind="seg", label="Pulso no kick", opts=[("Nenhum", 0), ("Leve", 1), ("Médio", 2), ("Forte", 3)],
             help="As camadas respiram (crescem) a cada batida", enabled=lambda c: _mv_on("pulse")(c)),
        dict(id="mv_one", kind="toggle", label="Pulsar só na batida 1",
             help="Só a primeira batida do compasso faz a imagem pulsar", enabled=lambda c: (_mv_on("pulse")(c)) and c["mv_pulse"] > 0),
        dict(id="ctrans", kind="seg", label="Transição de cor", opts=[("Corte", 0), ("Rápida", 1), ("Suave", 2), ("Lenta", 3), ("No tempo", 4)],
             help=lambda c: ["A cor troca de uma vez", "Uma cor vira a outra em 0,25 s", "Uma cor vira a outra em 0,8 s", "Uma cor vira a outra em 1,8 s",
                             "Dura duas batidas do compasso"][c["ctrans"]]),
        dict(id="mv_cuts", kind="seg", label="Frequência dos cortes", opts=[("Raros", 0), ("Normais", 1), ("Frequentes", 2)],
             help="Trocas de cor e universo na batida", enabled=lambda c: _mv_on("cuts")(c)),
    ]),
]
_ROWS = {r["id"]: r for _, rs in GRAPHICS + SETTINGS for r in rs if r["kind"] != "radio"}


def _card(title, *ids):
    return (title, [_ROWS[i] for i in ids])


# five tabs, one purpose each: what is drawn / how the camera moves / how the picture looks / how heavy it is / the program itself
LIVE_H = 540                       # height of the live tab's content (drawn by the control window, see deck.py)
GENRE_OPTS = [("Nenhum", ""), ("techno", "techno"), ("trance", "trance"), ("EDM", "edm"), ("pop", "pop")]
SHADER_OPTS = [("Automático", 8), ("3D", 1), ("Neon", 2), ("Holograma", 3), ("Raio X", 4), ("Cromado", 5), ("Aquarela", 6), ("Duotom", 7)]


SEC_OPTS = [("Cena", 0), ("Visual", 1), ("Fundo", 2), ("Cores", 3), ("Shader", 4), ("Câmera", 5), ("Movim.", 6), ("Formas", 7)]


def scene_rows(cfg, view="gallery"):
    """The Cenas tab. The gallery (and the picker of a new scene) is drawn by the control window; the editor of one scene is made of rows:
    a header with the way back and the section selector, then one section at a time (Cena, Visual, Fundo, Cores, Shader, Câmera, Movimento,
    Formas). Rebuilt whenever the scene changes."""
    if view != "editor":
        return []
    scn = cfg.get("scenes") or DEFAULTS["scenes"]
    ed = cfg.get("scene_edit", 0)
    name = scn[ed]["scene_name"] if 0 <= ed < len(scn) else "?"
    cards = [(f"CENA  ·  {name.upper()}", [
        dict(id="scene_back", kind="action", label="Voltar às cenas", btn="‹ Galeria", help="Mostra todas as cenas no ar  ·  Esc também volta"),
        dict(id="scene_sec", kind="seg", label="", opts=SEC_OPTS, help=""),
    ])]
    sec = cfg.get("scene_sec", 0)
    if sec == 0:
        cards.append(("IDENTIDADE", [
            dict(id="scene_name", kind="text", label="Nome", help="Clique e digite  ·  Enter confirma"),
            dict(id="scene_auto", kind="toggle", label="Entra no Auto", help="O modo Automático pode escolher esta cena"),
            dict(id="scene_genre", kind="seg", label="Gênero", opts=GENRE_OPTS, help="Chama esta cena no Automático"),
            dict(id="scene_new", kind="action", label="Duplicar cena", btn="Duplicar", help="Uma cópia para você mexer"),
            dict(id="scene_delete", kind="action", label="Apagar cena", btn="Apagar", help="Tira esta cena do ar (fica pelo menos uma)",
                 enabled=lambda c: len(c.get("scenes", [])) > 1),
        ]))
    elif sec == 1:
        cards.append(("VISUAL", [dict(id="scene_visual", kind="seg", label="O que aparece", opts=[("Nenhum", 0), ("Mandala", 1)],
                                      help=lambda c: "Só uma tela preta" if c["scene_visual"] == 0 else "O motor de facetas, com os números abaixo")]))
        if cfg.get("scene_visual", 1) == 1:
            cards += [
                ("PRESET DA MANDALA", [dict(id="scene_preset", kind="seg", label="Preset", opts=[(n, i) for i, n in enumerate(SC.PRESET_NAMES)],
                                            help="Copia os números")]),
                ("MANDALA", [
                    dict(id="m_base", kind="seg", label="Caráter", opts=[(n, i) for i, n in enumerate(SC.BASE_NAMES)],
                         help="A base de cores e de tom"),
                    dict(id="m_psx", kind="slider", label="Largura do painel", lo=20, hi=100, step=2, unit="%", help="Metade da largura de cada painel"),
                    dict(id="m_psy", kind="slider", label="Altura do painel", lo=3, hi=60, step=1, unit="%", help="Metade da altura de cada painel"),
                    dict(id="m_pox", kind="slider", label="Afastamento horizontal", lo=10, hi=100, step=2, unit="%", help="Quanto cada camada se afasta do centro"),
                    dict(id="m_poy", kind="slider", label="Afastamento vertical", lo=5, hi=60, step=2, unit="%", help="Quanto cada camada sobe ou desce"),
                    dict(id="m_decay", kind="slider", label="Encolhimento por camada", lo=60, hi=96, step=1, unit="%", help="Quanto do tamanho a próxima camada mantém"),
                    dict(id="m_thick", kind="slider", label="Espessura", lo=30, hi=300, step=10, unit="%", help="Em relação à espessura do caráter"),
                    dict(id="m_funnel", kind="slider", label="Funil mínimo", lo=0, hi=100, step=5, unit="%", help="O funil nunca fecha abaixo disto"),
                    dict(id="m_cuts", kind="slider", label="Frequência dos cortes", lo=20, hi=250, step=10, unit="%", help="Trocas de cor e universo na batida"),
                    dict(id="m_round", kind="seg", label="Cantos", opts=[("Retos", 0), ("Alternados", 1), ("Arredondados", 2)],
                         help="Alternados: um painel sim, outro não"),
                    dict(id="m_glass", kind="slider", label="Opacidade das faces", lo=20, hi=100, step=5, unit="%", help="100% sólido, 40% vitral"),
                ]),
                ("SIMETRIAS", [dict(id="m_sym%d" % i, kind="toggle", label=SC.SYM_LABELS[i], help="Esta dobra de caleidoscópio pode ser usada") for i in range(SC.SYM_COUNT)]),
            ]
        cards += [_card("SOM E LUZ", "react", "strobe", "bursts"), _card("BRILHO", "bloom")]          # how the picture answers the music
    elif sec == 2:
        cards.append(("FUNDO", [dict(id="scene_bg", kind="seg", label="Cor do fundo", opts=[("Da paleta", 0), ("Preto", 1)],
                                     help=lambda c: "Usa os fundos da paleta da cena" if c["scene_bg"] == 0 else "Sempre preto")]))
        cards.append(("LUZES DE FUNDO", [
            dict(id="bg_light", kind="seg", label="Luzes", opts=[("Nenhuma", 0), ("Aurora", 1), ("Feixes", 2), ("Pulsos", 3)],
                 help=lambda c: ["Sem luzes", "Faixas de luz que ondulam", "Raios que giram", "Anéis que saem no ritmo"][c["bg_light"]]),
            dict(id="bg_int", kind="slider", label="Intensidade", lo=10, hi=300, step=10, unit="%", help="Com as cores da paleta da cena", enabled=lambda c: c["bg_light"] > 0),
            dict(id="bg_speed", kind="slider", label="Velocidade", lo=20, hi=300, step=10, unit="%", help="Quão rápido as luzes se movem", enabled=lambda c: c["bg_light"] > 0),
        ]))
    elif sec == 3:
        cards += color_rows(cfg)                                  # the palette of the scene, the list of palettes and the editor of the selected one
    elif sec == 4:
        cards += [("AUTOMÁTICO", [dict(id="scene_pref", kind="seg", label="Favorecido", opts=[(SP.KIND_NAMES[k], k) for k in SP.ORDER], help="",
                                       enabled=lambda c: c["scene_shader"] == 0)])]
        cards += shader_rows(cfg)                                 # the shader of the scene, the list of shaders and the editor of the selected one
    elif sec == 5:
        cards += CAMERA
    elif sec == 6:
        cards += MOVEMENT
    else:
        cards += SHAPES
    return cards


def shader_rows(cfg):
    """The Shaders tab: which shader the scene uses, the list, and the editor of the selected preset (the three numbers are named by the kind)."""
    shs = cfg.get("shaders") or DEFAULTS["shaders"]
    radios = [dict(id="scene_shader", kind="radio", value=0, label="Automático",
                   help="Muda pelas partes da música, entre os shaders marcados com Entra no Auto")]
    for i, sh in enumerate(shs):
        radios.append(dict(id="scene_shader", kind="radio", value=i + 1, label=sh["name"], help=("" if sh["name"] == SP.KIND_NAMES[sh["kind"]] else SP.KIND_NAMES[sh["kind"]]) + ("" if sh.get("auto", True) else (" · " if sh["name"] != SP.KIND_NAMES[sh["kind"]] else "") + "fora do Auto")))
    ed = cfg.get("shd_edit", 0)
    sh = shs[ed] if 0 <= ed < len(shs) else shs[0]
    kind = sh["kind"]
    rows = [dict(id="shd_name", kind="text", label="Nome", help="Clique e digite  ·  Enter confirma"),
            dict(id="shd_kind", kind="seg", label="Tipo", opts=[(SP.KIND_NAMES[k], k) for k in SP.ORDER], help=""),
            dict(id="shd_auto", kind="toggle", label="Entra no Auto", help="O modo Automático pode escolher este shader")]
    for key, lab in zip(("shd_p1", "shd_p2", "shd_p3"), SP.labels(kind)):
        if lab:
            rows.append(dict(id=key, kind="slider", label=lab[0], lo=20, hi=300, step=10, unit="%", help=lab[1] + "  ·  100% é como sempre foi"))
    if kind == 7:
        rows.append(dict(id="shd_duo", kind="seg", label="Cores do duotom", opts=[("Da paleta", 0), ("Fixas", 1)], help="De onde vêm a cor escura e a clara"))
        if cfg.get("shd_duo", 0) == 1:
            rows.append(dict(id="shd_item", kind="swatches", label="Cor", help="Escura e clara", items=[sh["duo_dark"], sh["duo_light"]]))
            for key, lab in (("shd_r", "Vermelho"), ("shd_g", "Verde"), ("shd_b", "Azul")):
                rows.append(dict(id=key, kind="slider", label=lab, lo=0, hi=255, step=5, unit="", help="Da cor selecionada"))
    return [("SHADER DA CENA", radios), ("LISTA", [
        dict(id="shd_new", kind="action", label="Novo shader", btn="Duplicar", help="Cria uma cópia do shader selecionado para você mexer"),
        dict(id="shd_delete", kind="action", label="Apagar shader", btn="Apagar", help="Remove o shader selecionado (as cenas que o usavam voltam ao Automático)",
             enabled=lambda c: len(c.get("shaders", [])) > 1),
        dict(id="shd_factory", kind="action", label="Shaders de fábrica", btn="Restaurar", help="Volta aos sete shaders que vêm com o programa"),
    ]), (f"EDITANDO  ·  {sh['name'].upper()}", rows)]


def color_rows(cfg):
    """The Cores tab: which palette the scene uses, the list of palettes, and the editor of the selected palette."""
    pls = cfg.get("palettes") or DEFAULTS["palettes"]
    radios = [dict(id="scene_palette", kind="radio", value=0, label="Do caráter", help="As cores próprias do caráter da cena (como sempre foram)")]
    for i, pl in enumerate(pls):
        radios.append(dict(id="scene_palette", kind="radio", value=i + 1, label=pl["name"], help=f"{len(pl['colors'])} cores · {len(pl['bgs'])} fundos"))
    ed = cfg.get("pal_edit", 0)
    pal = pls[ed] if 0 <= ed < len(pls) else pls[0]
    its = PAL.items(pal)
    return [("PALETA DA CENA", radios), ("LISTA", [
        dict(id="pal_new", kind="action", label="Nova paleta", btn="Duplicar", help="Cria uma cópia da paleta selecionada para você mexer"),
        dict(id="pal_delete", kind="action", label="Apagar paleta", btn="Apagar", help="Remove a paleta selecionada (as cenas que a usavam voltam às cores do caráter)",
             enabled=lambda c: len(c.get("palettes", [])) > 1),
        dict(id="pal_factory", kind="action", label="Paletas de fábrica", btn="Restaurar", help="Volta às seis paletas que vêm com o programa"),
    ]), (f"EDITANDO  ·  {pal['name'].upper()}", [
        dict(id="pal_name", kind="text", label="Nome", help="Clique e digite  ·  Enter confirma"),
        dict(id="pal_item", kind="swatches", label="Cor selecionada", help="Fundos primeiro, depois as cores da paleta", items=[c for _, c in its]),
        dict(id="pal_r", kind="slider", label="Vermelho", lo=0, hi=255, step=5, unit="", help="Da cor selecionada"),
        dict(id="pal_g", kind="slider", label="Verde", lo=0, hi=255, step=5, unit="", help="Da cor selecionada"),
        dict(id="pal_b", kind="slider", label="Azul", lo=0, hi=255, step=5, unit="", help="Da cor selecionada"),
        dict(id="pal_add", kind="action", label="Adicionar cor", btn="Adicionar", help="Mais uma cor para a paleta sortear"),
        dict(id="pal_add_bg", kind="action", label="Adicionar fundo", btn="Adicionar", help="Mais um fundo possível"),
        dict(id="pal_remove", kind="action", label="Remover a selecionada", btn="Remover", help="Tira a cor ou o fundo selecionado (fica pelo menos um de cada)",
             enabled=lambda c: True),
    ])]


TABS = [
    ("Ao vivo", []),
    ("Cenas", scene_rows(DEFAULTS)),
    ("Gráficos", [_card("PREDEFINIÇÃO", "preset"), _card("RESOLUÇÃO E FPS", "res", "dynres", "fps_out", "dynmin", "rrate"),
                  _card("RAIOS E CAMADAS", "detail", "steps", "dist"), _card("BRILHO", "bloomq", "bloomres"),
                  _card("MOTION BLUR", "mblur", "mblur_fps"), _card("SUAVIZAÇÃO", "aa_mode", "sharp")]),
    ("Ajustes", [_card("TELA", "fullscreen", "vsync"), _card("SISTEMA", "backend", "gpu", "wave_blend", "auto_update")]),
]
TAB_SCENES = 1
TAB_LIVE = 0
PV_TABS = ("Cenas", "Gráficos")        # the tabs that show the live thumbnail under the tab bar
PV_H = 184
TAB_PERF = [n for n, _ in TABS].index("Gráficos")
TAB_SET = [n for n, _ in TABS].index("Ajustes")
NAMES = {"fullscreen": "Tela cheia", "vsync": "VSync", "fps_cap": "Limite de FPS", "strobe": "Flashes",
         "bursts": "Rajadas", "bloom": "Intensidade do brilho", "react": "Reatividade", "effect": "Cena", "res": "Resolução",
         "backend": "Backend", "preset": "Qualidade", "steps": "Passos do raio", "shadows": "Sombras", "reflect": "Reflexos",
         "ao": "Oclusão", "bloomq": "Brilho", "aa_mode": "Suavização", "sharp": "Nitidez", "bloomres": "Resolução do brilho", "dist": "Distância", "bounce": "Reflexos em cadeia", "rrate": "Taxa de renderização", "dynmin": "Escala mínima", "gpu": "Placa de vídeo", "panel_hz": "Painel", "panel_view": "Monitor do painel", "wave_blend": "Onda do Ao vivo", "detail": "Densidade", "rt": "Iluminação",
         "style": "Estilo", "camera": "Câmera", "cam_orbit": "Órbita", "cam_roll": "Giro", "cam_shake": "Tremor", "cam_punch": "Soco", "cam_funnel": "Funil", "cam_fov_min": "FOV mínimo", "cam_fov_max": "FOV máximo", "cam_fov_var": "Variação do FOV", "cam_sync": "Sincronia", "sh_when": "Troca de forma", "sh_mix": "Distribuição", "sh_morph": "Transformação", "ctrans": "Transição de cor", "auto_shape": "Auto: formas", "sh_0": "Painéis (padrão)", "sh_2": "Cubo", "sh_16": "Cuboide", "sh_1": "Esfera", "sh_3": "Cilindro", "sh_4": "Cone", "sh_15": "Cone truncado", "sh_9": "Toro", "sh_10": "Anel", "sh_14": "Meia-esfera", "sh_5": "Pirâmide quadrada", "sh_6": "Pirâmide hexagonal", "sh_7": "Prisma triangular", "sh_8": "Prisma hexagonal", "sh_17": "Prisma pentagrâmico", "sh_11": "Octaedro", "sh_12": "Dodecaedro", "sh_13": "Icosaedro", "sh_18": "Buckyball", "auto_cam_orbit": "Auto: órbita", "auto_cam_roll": "Auto: giro", "auto_cam_shake": "Auto: tremor", "auto_cam_punch": "Auto: soco", "auto_cam_funnel": "Auto: funil", "auto_cam_fov": "Auto: FOV", "auto_cam_sync": "Auto: sincronia", "auto_mv_speed": "Auto: velocidade", "auto_mv_rot": "Auto: rotação", "auto_mv_pulse": "Auto: pulso", "auto_mv_cuts": "Auto: cortes", "auto_mv_inertia": "Auto: inércia", "auto_scene": "Auto: cena", "auto_style": "Auto: estilo", "auto_cuts": "Auto: cortes de cor", "auto_vars": "Auto: cor por elemento",  "movement": "Movimento", "mv_speed": "Velocidade", "mv_inertia": "Inércia", "mv_rot": "Rotação", "mv_dir": "Direção", "mv_pulse": "Pulso", "mv_one": "Pulso só na batida 1", "mv_cuts": "Cortes", "mblur": "Obturador", "auto_update": "Verificação de atualização", "mblur_fps": "Quadros de referência", "dynres": "Resolução dinâmica", "fps_out": "FPS de saída", "scene_palette": "Paleta", "shd_name": "Nome do shader", "shd_kind": "Tipo", "shd_p1": "Ajuste 1", "shd_p2": "Ajuste 2", "shd_p3": "Ajuste 3", "shd_auto": "Entra no Auto", "shd_duo": "Cores do duotom", "shd_item": "Cor", "shd_r": "Vermelho", "shd_g": "Verde", "shd_b": "Azul", "pal_name": "Nome da paleta", "pal_item": "Cor selecionada", "pal_r": "Vermelho", "pal_g": "Verde", "pal_b": "Azul", "m_sym0": "Espelho 4x", "m_sym1": "Espelho lateral", "m_sym2": "Radial 6", "m_sym3": "Radial 8", "m_sym4": "Radial 5", "m_sym5": "Diagonal", "m_sym6": "Espelho vertical", "m_sym7": "Radial 12", "scene_name": "Nome", "scene_visual": "Visual", "scene_bg": "Fundo", "scene_sec": "Seção", "bg_light": "Luzes de fundo", "bg_int": "Intensidade das luzes", "bg_speed": "Velocidade das luzes", "scene_pref": "Shader favorecido", "scene_when": "Trocar de cena", "scene_every": "A cada", "scene_preset": "Preset", "scene_auto": "Entra no Auto", "scene_genre": "Gênero", "scene_shader": "Shader", "m_base": "Caráter", "m_psx": "Largura", "m_psy": "Altura", "m_pox": "Afastamento horizontal", "m_poy": "Afastamento vertical", "m_decay": "Encolhimento", "m_thick": "Espessura", "m_funnel": "Funil mínimo", "m_cuts": "Cortes", "m_round": "Cantos", "m_glass": "Opacidade"}


class Menu:
    W = 640
    HEAD = 44
    ROW = 52
    GAP = 12
    FOOT = 90

    def __init__(self, cfg):
        self.cfg = cfg
        self.dirty = False
        self.dirty_t = 0.0
        self.need = True
        self.f = pygame.font.SysFont("segoeui", 15)
        self.fb = pygame.font.SysFont("segoeui", 15, bold=True)
        self.f_s = pygame.font.SysFont("segoeui", 12)
        self.f_sb = pygame.font.SysFont("segoeui", 12, bold=True)
        self.title = pygame.font.SysFont("segoeui", 22, bold=True)
        self.ftab = pygame.font.SysFont("segoeui", 13, bold=True)
        self.hits = []
        self.order = []
        self.order_val = []
        self.focus = 0
        self.kbd = False
        self.hover = None
        self.drag = None
        self.toast = None
        self.quit_armed = 0.0
        self.last_click = (None, 0.0)
        self.frects = {}
        self.scroll = 0
        self.view_h = 10 ** 6
        self.tab = int(os.environ.get("VIS_TAB", "0"))        # test hook
        self.live = ""
        self.info = ""                 # version / update status, shown in the header of the Ajustes tab
        self.upd_label = ""            # text of the "update to vX" button (empty = no update to offer)
        self.live_h = LIVE_H                           # current height of the live tab's content (the deck reports it)
        self.text_focus = None                         # id of the text field being typed into
        self.reserved = 0                              # height of the preview strip under the tab bar (the control window sets it)
        self.heights = []
        self.scene_view = "gallery"                    # the Cenas tab: gallery (all scenes), picker (a new scene) or editor (one scene)
        self.gal_h = 420                               # height of the gallery content (the control window reports it)
        self.templates = SC.templates()                # the scenes the picker offers (kept, so their live thumbnails stay the same)
        self.preset_templates = SC.preset_templates()  # the second step: a mandala preset
        self._eff_before = 0                           # the Auto / fixed-scene choice to bring back when the editor closes
        self.rebuild_scenes(first=True)
        self.H = max(self.heights)                  # the surface fits the tallest tab (with room for more scenes)
        self.surf = pygame.Surface((self.W, self.H + 800), pygame.SRCALPHA)

    def _compute_heights(self):
        self.heights = []
        for tname, secs in TABS:
            h = self.HEAD
            for _, rows in secs:
                h += 40 + len(rows) * self.ROW + 10 + self.GAP
            if tname == TABS[TAB_LIVE][0]:
                h = self.HEAD + self.live_h + 8
            if tname == TABS[TAB_SCENES][0] and self.scene_view != "editor":
                h = self.HEAD + self.gal_h + 8
            self.heights.append(h + self.FOOT + (112 if tname == TABS[TAB_SET][0] else 0))      # the Ajustes tab has a second row of buttons (updates)

    # ------------------------------------------------------------ scene presets
    def rebuild_scenes(self, first=False):
        TABS[TAB_SCENES] = ("Cenas", scene_rows(self.cfg, self.scene_view))
        self._compute_heights()
        self.need = True
        if not first:
            self.H = max(self.H, max(self.heights))
            if self.surf.get_height() < max(self.heights):
                self.surf = pygame.Surface((self.W, max(self.heights) + 800), pygame.SRCALPHA)

    def store_scene(self):
        scn = self.cfg["scenes"]
        ed = self.cfg["scene_edit"]
        if 0 <= ed < len(scn):
            SC.store_scene(self.cfg, scn[ed])

    def _pal(self):
        return self.cfg["palettes"][self.cfg["pal_edit"]]

    def select_palette(self, i):
        self.cfg["pal_edit"] = max(0, min(i, len(self.cfg["palettes"]) - 1))
        self.cfg["pal_item"] = 0
        load_palette_edit(self.cfg)
        self.rebuild_scenes()

    def _shd(self):
        return self.cfg["shaders"][self.cfg["shd_edit"]]

    def select_shader(self, i):
        self.cfg["shd_edit"] = max(0, min(i, len(self.cfg["shaders"]) - 1))
        self.cfg["shd_item"] = 0
        load_shader_edit(self.cfg)
        self.rebuild_scenes()

    def in_gallery(self):
        return self.tab == TAB_SCENES and self.scene_view != "editor"

    def set_gal_h(self, h):
        """The control window tells how tall the gallery (or the picker) is."""
        h = int(h)
        if h != self.gal_h:
            self.gal_h = h
            self._compute_heights()
            if self.surf.get_height() < max(self.heights):
                self.surf = pygame.Surface((self.W, max(self.heights) + 800), pygame.SRCALPHA)
            self.need = True

    def open_scene(self, i):
        """Open the editor of scene i. The picture shows that scene while it is edited."""
        scn = self.cfg["scenes"]
        if not 0 <= i < len(scn):
            return
        if self.scene_view != "editor":
            self._eff_before = self.cfg["effect"]
        self.cfg["scene_sec"] = 0
        SC.apply_scene(self.cfg, scn[i])
        self.cfg["scene_edit"] = i
        self.cfg["effect"] = i + 1
        self.cfg["scene_now"] = True                        # the editor shows the scene at once, whatever the "Trocar de cena" choice
        self.scene_view = "editor"
        self.scroll = 0
        self.rebuild_scenes()
        self.touch()

    def close_scene(self):
        """Back to the gallery: the Auto / fixed choice from before the editor comes back."""
        self.store_scene()
        self.cfg["scene_now"] = False
        self.cfg["effect"] = self._eff_before if self._eff_before <= len(self.cfg["scenes"]) else 0
        self.scene_view = "gallery"
        self.scroll = 0
        self.rebuild_scenes()
        self.touch()

    def back_to_gallery(self):
        if self.scene_view == "editor":
            self.close_scene()
        else:
            self.scene_view = "gallery"
            self.scroll = 0
            self.rebuild_scenes()
            self.touch()
        return None

    def duplicate_scene(self, i):
        """A copy of scene i, right after it in the gallery."""
        scn = self.cfg["scenes"]
        if not 0 <= i < len(scn):
            return
        if i == self.cfg["scene_edit"]:
            self.store_scene()
        new = copy.deepcopy(scn[i])
        new["scene_name"] = (new["scene_name"] + " (cópia)")[:28]
        scn.insert(i + 1, new)
        eff = self.cfg["effect"]
        if eff > i + 1:
            self.cfg["effect"] = eff + 1
        if self.cfg["scene_edit"] > i:
            self.cfg["scene_edit"] += 1
        self.rebuild_scenes()
        self.touch()
        self.say(f"Cena duplicada: {new['scene_name']}")

    def add_preset(self, i):
        """A new Mandala scene with preset i: it joins the scenes and opens in the editor, on the Visual section."""
        if not 0 <= i < len(self.preset_templates):
            return
        new = copy.deepcopy(self.preset_templates[i])
        self.cfg["scenes"].append(new)
        self._eff_before = self.cfg["effect"]
        self.scene_view = "gallery"
        self.open_scene(len(self.cfg["scenes"]) - 1)
        self.cfg["scene_sec"] = 1
        self.rebuild_scenes()
        self.say(f"Cena criada: {new['scene_name']}")

    def delete_scene(self, i):
        """Remove scene i from the gallery (there is always at least one)."""
        scn = self.cfg["scenes"]
        if len(scn) <= 1 or not 0 <= i < len(scn):
            return False
        name = scn[i]["scene_name"]
        del scn[i]
        eff = self.cfg["effect"]
        self.cfg["effect"] = 0 if eff == i + 1 else (eff - 1 if eff > i + 1 else eff)
        ed = self.cfg["scene_edit"]
        self.cfg["scene_edit"] = max(0, min(ed - 1 if ed > i else ed, len(scn) - 1))
        SC.apply_scene(self.cfg, scn[self.cfg["scene_edit"]])
        self.rebuild_scenes()
        self.touch()
        self.say(f"Cena apagada: {name}")
        return True

    def add_scene(self, t):
        """A new scene from template t of the picker: it joins the scenes and opens in the editor."""
        if not 0 <= t < len(self.templates):
            return
        new = copy.deepcopy(self.templates[t])
        self.cfg["scenes"].append(new)
        self._eff_before = self.cfg["effect"]
        self.scene_view = "gallery"
        self.open_scene(len(self.cfg["scenes"]) - 1)
        self.say(f"Cena criada: {new['scene_name']}")

    def select_scene(self, i):
        scn = self.cfg["scenes"]
        i = max(0, min(i, len(scn) - 1))
        self.cfg["scene_edit"] = i
        SC.apply_scene(self.cfg, scn[i])
        self.rebuild_scenes()

    # ------------------------------------------------------------ state
    def touch(self):
        self.dirty = self.need = True
        self.dirty_t = time.perf_counter()

    def max_scroll(self):
        return max(0, self.heights[self.tab] - self.view_h + self.reserved)

    def content_h(self):
        """Height of the scrolling area: the window minus the tab bar and the preview strip (when the tab has one)."""
        return self.view_h - self.HEAD - self.reserved

    def scroll_to_focus(self):
        if not self.order:
            return
        fr = self.frects.get(self.order[self.focus % len(self.order)])
        if fr is None:
            return
        top = self.HEAD + self.scroll
        if fr.top < top + 8:
            self.scroll = max(0, fr.top - self.HEAD - 8)
        elif fr.bottom > top + self.content_h() - 8:
            self.scroll = min(self.max_scroll(), fr.bottom - self.HEAD - self.content_h() + 8)

    def set_live(self, text):
        """Short live status ("96 FPS · 1280×720 · 80%") shown in the header of the Gráficos tab."""
        if text != self.live:
            self.live = text
            if self.tab == TAB_PERF:
                self.need = True

    def say(self, text):
        self.toast = (text, time.perf_counter() + 2.2)
        self.need = True

    def enabled(self, row):
        fn = row.get("enabled")
        return True if fn is None else bool(fn(self.cfg))

    def find(self, cid):
        for _, secs in TABS:
            for _, rows in secs:
                for r in rows:
                    if r["id"] == cid:
                        return r
        return None

    def set_value(self, cid, value, announce=True):
        if cid == "scene_sec":
            announce = False                                     # changing section says nothing (the toast would cover the tab bar)
        if cid == "preset":
            if value == CUSTOM or not (0 <= value < len(PRESETS)):
                return
            self.cfg.update(PRESETS[value][1])
            self.cfg["preset"] = value
            self.touch()
            if announce:
                self.say(f"Qualidade: {PRESETS[value][0]}")
            return
        if cid == "movement":
            if value == MV_MANUAL or not (0 <= value <= MV_AUTO) or self.cfg["movement"] == value:
                return
            if value < len(MV_PRESETS):
                self.cfg.update(MV_PRESETS[value][1])
            self.cfg["movement"] = value
            self.touch()
            if announce:
                self.say(f"Movimento: {MV_OPTS[value][0]}")
            return
        if cid == "camera":
            if value == CAM_MANUAL or not (0 <= value <= CAM_AUTO) or self.cfg["camera"] == value:
                return
            if value < len(CAM_PRESETS):
                self.cfg.update(CAM_PRESETS[value][1])
            self.cfg["camera"] = value
            self.touch()
            if announce:
                self.say(f"Câmera: {CAM_OPTS[value][0]}")
            return
        if self.cfg.get(cid) == value:
            return
        self.cfg[cid] = value
        if cid == "scene_shader":
            self.store_scene()
            if value >= 1:
                self.select_shader(value - 1)
            self.rebuild_scenes()
        elif cid in ("shd_name", "shd_kind", "shd_p1", "shd_p2", "shd_p3", "shd_auto", "shd_duo"):
            sh = self._shd()
            key = {"shd_name": "name", "shd_kind": "kind", "shd_p1": "p1", "shd_p2": "p2", "shd_p3": "p3", "shd_auto": "auto", "shd_duo": "duo_mode"}[cid]
            sh[key] = str(value)[:28] if cid == "shd_name" else value
            if cid in ("shd_name", "shd_kind", "shd_auto", "shd_duo"):
                self.rebuild_scenes()
        elif cid == "shd_item":
            load_shader_edit(self.cfg)
            self.rebuild_scenes()
        elif cid in ("shd_r", "shd_g", "shd_b"):
            self._shd()["duo_dark" if self.cfg["shd_item"] == 0 else "duo_light"] = [self.cfg["shd_r"], self.cfg["shd_g"], self.cfg["shd_b"]]
            self.rebuild_scenes()
        elif cid == "scene_palette":
            self.store_scene()
            if value >= 1:
                self.select_palette(value - 1)
            self.rebuild_scenes()
        elif cid == "pal_name":
            self._pal()["name"] = str(value)[:28]
            self.rebuild_scenes()
        elif cid == "pal_item":
            load_palette_edit(self.cfg)
            self.rebuild_scenes()
        elif cid in ("pal_r", "pal_g", "pal_b"):
            lst, idx = PAL.item_ref(self._pal(), self.cfg["pal_item"])
            lst[idx] = [self.cfg["pal_r"], self.cfg["pal_g"], self.cfg["pal_b"]]
            self.rebuild_scenes()
        elif cid == "scene_sec":
            self.scroll = 0
            self.rebuild_scenes()
        elif cid == "scene_preset":                                              # a mandala preset: its numbers become the scene's
            SC.apply_preset(self.cfg, int(value))
            self.store_scene()
            self.rebuild_scenes()
        elif cid == "effect" and value >= 1:                                     # selecting a scene: it becomes the one being edited and shown
            self.select_scene(value - 1)
        elif cid in SC.SCENE_KEYS:
            if cid in ("camera", "movement"):
                pass
            self.store_scene()
            if cid in ("scene_name", "scene_genre", "scene_visual") or cid.startswith("m_sym"):
                self.rebuild_scenes()
        elif cid == "scene_sec":
            self.scroll = 0
            self.rebuild_scenes()
        if cid == "cam_fov_min" and value > self.cfg["cam_fov_max"]:
            self.cfg["cam_fov_max"] = value
        if cid == "cam_fov_max" and value < self.cfg["cam_fov_min"]:
            self.cfg["cam_fov_min"] = value
        if cid in CAM_KEYS and self.cfg["camera"] != CAM_AUTO:
            self.cfg["camera"] = match_camera(self.cfg)
            self.store_scene()
        if cid in MV_KEYS and self.cfg["movement"] != MV_AUTO:
            self.cfg["movement"] = match_movement(self.cfg)
            self.store_scene()
        if cid in GFX_KEYS:
            self.cfg["preset"] = match_preset(self.cfg)
        self.touch()
        row = self.find(cid) if announce else None
        if row:
            if row["kind"] == "toggle":
                self.say(f"{NAMES.get(cid, cid)}: {'ligado' if value else 'desligado'}")
            elif row["kind"] == "seg":
                lbl = [l for l, v in row["opts"] if v == value][0]
                self.say(f"{NAMES.get(cid, cid)}: {lbl}" + ("  ·  reinicie para aplicar" if cid == "backend" else ""))

    def adjust(self, cid, d):
        row = self.find(cid)
        if row is None or not self.enabled(row):
            return
        if row["kind"] == "toggle":
            self.set_value(cid, d > 0 if d != 0 else not self.cfg[cid])
        elif row["kind"] == "seg":
            vals = [v for _, v in row["opts"]]
            i = vals.index(self.cfg[cid]) if self.cfg[cid] in vals else 0
            self.set_value(cid, vals[max(0, min(len(vals) - 1, i + d))])
        elif row["kind"] == "slider":
            v = max(row["lo"], min(row["hi"], self.cfg[cid] + d * row["step"]))
            self.set_value(cid, v, announce=False)

    def slider_from_x(self, cid, x):
        row = self.find(cid)
        tl, tw = self.slider_geo
        t = max(0.0, min(1.0, (x - tl) / tw))
        v = row["lo"] + t * (row["hi"] - row["lo"])
        self.set_value(cid, int(round(v / row["step"]) * row["step"]), announce=False)

    def press(self, cid):
        """Activate a button; returns an action string for the caller."""
        now = time.perf_counter()
        if cid.startswith("tab"):
            if int(cid[3:]) == TAB_SCENES and self.tab == TAB_SCENES and self.scene_view != "gallery":
                return self.back_to_gallery()                         # the Cenas tab again: back to the gallery
            self.tab = max(0, min(int(cid[3:]), len(TABS) - 1))
            self.scroll = 0
            self.need = True
            return None
        if cid == "shd_new":
            shs = self.cfg["shaders"]
            new = copy.deepcopy(shs[self.cfg["shd_edit"]])
            new["name"] = (new["name"] + " (cópia)")[:28]
            shs.append(new)
            self.cfg["scene_shader"] = len(shs)
            self.store_scene()
            self.select_shader(len(shs) - 1)
            self.touch()
            self.say("Shader duplicado: mexa à vontade")
            return None
        if cid == "shd_delete":
            shs = self.cfg["shaders"]
            if len(shs) > 1:
                gone = self.cfg["shd_edit"]
                del shs[gone]
                for sc_ in self.cfg["scenes"]:
                    if sc_.get("scene_shader", 0) == gone + 1:
                        sc_["scene_shader"] = 0
                    elif sc_.get("scene_shader", 0) > gone + 1:
                        sc_["scene_shader"] -= 1
                SC.apply_scene(self.cfg, self.cfg["scenes"][self.cfg["scene_edit"]])
                self.select_shader(min(gone, len(shs) - 1))
                self.touch()
                self.say("Shader apagado")
            return None
        if cid == "shd_factory":
            self.cfg["shaders"][:] = SP.factory()
            for sc_ in self.cfg["scenes"]:
                sc_["scene_shader"] = min(sc_.get("scene_shader", 0), len(self.cfg["shaders"]))
            self.select_shader(0)
            self.touch()
            self.say("Shaders de fábrica restaurados")
            return None
        if cid == "pal_new":
            pls = self.cfg["palettes"]
            new = copy.deepcopy(pls[self.cfg["pal_edit"]])
            new["name"] = (new["name"] + " (cópia)")[:28]
            pls.append(new)
            self.cfg["scene_palette"] = len(pls)
            self.store_scene()
            self.select_palette(len(pls) - 1)
            self.touch()
            self.say("Paleta duplicada: mexa à vontade")
            return None
        if cid == "pal_delete":
            pls = self.cfg["palettes"]
            if len(pls) > 1:
                gone = self.cfg["pal_edit"]
                del pls[gone]
                for sc_ in self.cfg["scenes"]:                         # scenes that used it (or a later one) are fixed
                    if sc_.get("scene_palette", 0) == gone + 1:
                        sc_["scene_palette"] = 0
                    elif sc_.get("scene_palette", 0) > gone + 1:
                        sc_["scene_palette"] -= 1
                SC.apply_scene(self.cfg, self.cfg["scenes"][self.cfg["scene_edit"]])
                self.select_palette(min(gone, len(pls) - 1))
                self.touch()
                self.say("Paleta apagada")
            return None
        if cid == "pal_factory":
            self.cfg["palettes"][:] = PAL.factory()
            for sc_ in self.cfg["scenes"]:
                sc_["scene_palette"] = min(sc_.get("scene_palette", 0), len(self.cfg["palettes"]))
            self.select_palette(0)
            self.touch()
            self.say("Paletas de fábrica restauradas")
            return None
        if cid in ("pal_add", "pal_add_bg"):
            pal = self._pal()
            (pal["bgs"] if cid == "pal_add_bg" else pal["colors"]).append([200, 200, 200])
            self.cfg["pal_item"] = len(PAL.items(pal)) - 1 if cid == "pal_add" else len(pal["bgs"]) - 1
            load_palette_edit(self.cfg)
            self.rebuild_scenes()
            self.touch()
            return None
        if cid == "pal_remove":
            pal = self._pal()
            lst, idx = PAL.item_ref(pal, self.cfg["pal_item"])
            if len(lst) > 1:
                del lst[idx]
                self.cfg["pal_item"] = max(0, self.cfg["pal_item"] - 1)
                load_palette_edit(self.cfg)
                self.rebuild_scenes()
                self.touch()
            else:
                self.say("A paleta precisa de pelo menos uma cor e um fundo")
            return None
        if cid == "scene_back":
            self.close_scene()
            return None
        if cid == "scene_new":                                       # duplicate the scene being edited
            scn = self.cfg["scenes"]
            self.store_scene()
            new = copy.deepcopy(scn[self.cfg["scene_edit"]])
            new["scene_name"] = (new["scene_name"] + " (cópia)")[:28]
            scn.append(new)
            self.open_scene(len(scn) - 1)
            self.say("Cena duplicada: mexa à vontade")
            return None
        if cid == "scene_delete":
            scn = self.cfg["scenes"]
            if len(scn) > 1:
                gone = self.cfg["scene_edit"]
                del scn[gone]
                b_ = self._eff_before
                self._eff_before = 0 if b_ == gone + 1 else (b_ - 1 if b_ > gone + 1 else b_)
                self.cfg["scene_edit"] = min(gone, len(scn) - 1)
                SC.apply_scene(self.cfg, scn[self.cfg["scene_edit"]])
                self.close_scene()
                self.say("Cena apagada")
            return None
        if cid == "scene_factory":
            extras = {k: self.cfg[k] for k in SC.CAMERA_KEYS + SC.MOVEMENT_KEYS + SC.SHAPE_KEYS + SC.REACT_KEYS + SC.BG_KEYS}
            self.cfg["scenes"][:] = SC.starter_scenes(extras)
            self.cfg["effect"] = 0
            self.cfg["scene_edit"] = 0
            SC.apply_scene(self.cfg, self.cfg["scenes"][0])
            self.scene_view = "gallery"
            self.rebuild_scenes()
            self.touch()
            self.say("Cenas de fábrica restauradas")
            return None
        if cid == "reset" and self.tab == TAB_SCENES:
            return None
        if cid == "reset":
            keep = {k: self.cfg[k] for k in ("fullscreen",)}
            ids = {r["id"] for _, rows in TABS[self.tab][1] for r in rows}
            base = fresh()
            if "camera" in ids:
                ids |= set(CAM_KEYS)
            if "movement" in ids:
                ids |= set(MV_KEYS)
            if "preset" in ids:
                ids |= set(GFX_KEYS)
            self.cfg.update({k: base[k] for k in ids if k in base})
            self.cfg["preset"] = match_preset(self.cfg)
            self.cfg["camera"] = match_camera(self.cfg) if self.cfg["camera"] != CAM_AUTO else CAM_AUTO
            self.cfg["movement"] = match_movement(self.cfg) if self.cfg["movement"] != MV_AUTO else MV_AUTO
            self.cfg.update(keep)
            self.touch()
            self.say(f"Padrões da aba {TABS[self.tab][0]} restaurados")
            return None
        if cid in ("bench", "update_check", "update_apply"):
            return cid
        if cid == "quit":
            if self.quit_armed > now:
                return "quit"
            self.quit_armed = now + 3.0
            self.need = True
        return None

    # -------------------------------------------------------------- input
    def text_key(self, e):
        """Typing into the text field that has the focus. Returns True when the key was used."""
        if not self.text_focus:
            return False
        cid = self.text_focus
        v = str(self.cfg.get(cid, ""))
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE, pygame.K_TAB):
            self.text_focus = None
        elif e.key == pygame.K_BACKSPACE:
            self.set_value(cid, v[:-1], announce=False)
        elif getattr(e, "unicode", "") and e.unicode.isprintable() and len(v) < 28:
            self.set_value(cid, v + e.unicode, announce=False)
        self.need = True
        return True

    def key(self, k, mod=0):
        self.kbd = True
        self.need = True
        n = len(self.order)
        if n == 0:
            return None
        if k in (pygame.K_DOWN, pygame.K_TAB):
            step = -1 if (k == pygame.K_TAB and mod & pygame.KMOD_SHIFT) else 1
            self.focus = (self.focus + step) % n
        elif k == pygame.K_UP:
            self.focus = (self.focus - 1) % n
        elif k in (pygame.K_LEFT, pygame.K_RIGHT):
            cid = self.order[self.focus].split("#")[0]
            if cid.startswith("tab"):
                self.press(f"tab{max(0, min(len(TABS) - 1, self.tab + (-1 if k == pygame.K_LEFT else 1)))}")
            elif self.find(cid)["kind"] in ("text", "action"):
                pass
            elif self.find(cid)["kind"] == "radio":
                vals = [r["value"] for r in [x for _, rows in TABS[self.tab][1] for x in rows] if r["id"] == cid]
                i = vals.index(self.cfg[cid]) if self.cfg[cid] in vals else 0
                self.set_value(cid, vals[max(0, min(len(vals) - 1, i + (-1 if k == pygame.K_LEFT else 1)))])
            else:
                self.adjust(cid, -1 if k == pygame.K_LEFT else 1)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            fkey = self.order[self.focus]
            cid = fkey.split("#")[0]
            if cid in ("reset", "quit") or cid.startswith("tab"):
                return self.press(cid)
            row = self.find(cid)
            if row["kind"] == "action":
                return self.press(cid) if self.enabled(row) else None
            if row["kind"] == "text":
                self.text_focus = cid
            elif row["kind"] == "radio":
                self.set_value(cid, self.order_val[self.focus % len(self.order)])
            elif row["kind"] == "toggle":
                self.adjust(cid, 0)
            elif row["kind"] == "seg":
                vals = [v for _, v in row["opts"]]
                i = vals.index(self.cfg[cid]) if self.cfg[cid] in vals else 0
                if self.enabled(row):
                    self.set_value(cid, vals[(i + 1) % len(vals)])
        elif k == pygame.K_ESCAPE:
            if self.tab == TAB_SCENES and self.scene_view != "gallery":
                return self.back_to_gallery()
            self.kbd = False
        self.scroll_to_focus()
        return None

    def hit_at(self, pos):
        for rect, cid, kind, arg in reversed(self.hits):
            if rect.collidepoint(pos):
                return rect, cid, kind, arg
        return None

    def mouse(self, ev, ox, oy, scale):
        if ev.type == pygame.MOUSEWHEEL:
            if self.hover and self.find(self.hover) and self.find(self.hover)["kind"] == "slider":
                self.adjust(self.hover, 1 if ev.y > 0 else -1)
            else:
                self.scroll = max(0, min(self.max_scroll(), self.scroll - ev.y * 48))
                self.need = True
            return None
        pos = (ev.pos[0] - ox, ev.pos[1] - oy + self.scroll)
        hit = self.hit_at(pos)
        self.kbd = False
        if ev.type == pygame.MOUSEMOTION:
            hv = hit[1] if hit else None
            if hv != self.hover:
                self.hover = hv
                self.need = True
            if self.drag and ev.buttons[0]:
                self.slider_from_x(self.drag, pos[0])
        elif ev.type == pygame.MOUSEBUTTONUP:
            self.drag = None
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.text_focus and not (hit and hit[1] == self.text_focus):
            self.text_focus = None                                   # a click elsewhere ends the typing
            self.need = True
            return self.mouse(ev, ox, oy, scale)
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and hit:
            rect, cid, kind, arg = hit
            fk = f"{cid}#{arg}" if kind == "radio" else cid
            if fk in self.order:
                self.focus = self.order.index(fk)
            self.need = True
            if kind == "btn":
                return self.press(cid)
            row = self.find(cid)
            if row is None or not self.enabled(row):
                return None
            if kind == "text":
                self.text_focus = cid
            elif kind == "toggle":
                self.adjust(cid, 0)
            elif kind in ("seg", "radio"):
                self.set_value(cid, arg)
            elif kind == "slider":
                now = time.perf_counter()
                if self.last_click[0] == cid and now - self.last_click[1] < 0.4:
                    default = DEFAULTS[cid]
                    self.set_value(cid, default, announce=False)
                    self.say(f"{NAMES.get(cid, cid)} restaurado: {default}{self.find(cid).get('unit', '%')}")
                    self.last_click = (None, 0.0)
                else:
                    self.last_click = (cid, now)
                    self.drag = cid
                    self.slider_from_x(cid, pos[0])
        return None

    # ------------------------------------------------------------- render
    def _txt(self, font, text, pos, color, anchor="l"):
        img = font.render(text, True, color)
        x, y = pos
        if anchor == "r":
            x -= img.get_width()
        elif anchor == "c":
            x -= img.get_width() // 2
        self.surf.blit(img, (x, y))
        return img.get_width()

    def render(self):
        now = time.perf_counter()
        if self.toast and now > self.toast[1]:
            self.toast = None
            self.need = True
        if self.quit_armed and now > self.quit_armed:
            self.quit_armed = 0.0
            self.need = True
        if not self.need:
            return False
        self.need = False
        s, c = self.surf, self.cfg
        s.fill((0, 0, 0, 0))
        self.hits, self.order, self.frects, self.order_val = [], [], {}, []
        W = self.W
        # tab bar
        x = 0
        for i, (name, _) in enumerate(TABS):
            cid = f"tab{i}"
            tw = (W - 6 * (len(TABS) - 1)) // len(TABS)
            r = pygame.Rect(x, 0, tw, 36)
            sel, hov = i == self.tab, self.hover == cid
            ui.rect(s, (*(ACCENT if sel else (SURFACE2 if hov else SURFACE)), 255), r, border_radius=10)
            if not sel:
                ui.rect(s, (*BORDER, 255), r, width=1, border_radius=10)
            self._txt(self.ftab, name, (r.centerx, r.y + 9), ON_ACCENT if sel else TEXT, "c")
            self.hits.append((r, cid, "btn", None))
            self.order.append(cid)
            self.order_val.append(None)
            self.frects[cid] = r
            x += tw + 6
        y = self.HEAD
        for title, rows in TABS[self.tab][1]:
            ch = 40 + len(rows) * self.ROW + 10
            ui.rect(s, (*SURFACE, 255), (0, y, W, ch), border_radius=14)
            ui.rect(s, (*BORDER, 255), (0, y, W, ch), width=1, border_radius=14)
            self._txt(self.f_sb, "  ".join(title), (18, y + 14), ACCENT)
            ry = y + 40
            for row in rows:
                self._row(row, ry)
                ry += self.ROW
            y += ch + self.GAP

        if self.tab == TAB_LIVE:
            y = self.HEAD + self.live_h                 # the live content is drawn here by the control window
        elif self.in_gallery():
            y = self.HEAD + self.gal_h                  # the gallery is drawn here by the control window
        # footer buttons
        fy = y + 4
        armed = self.quit_armed > now
        if self.tab >= 1 and self.tab != TAB_SCENES:
            self._button("reset", pygame.Rect(0, fy, 200, 42), "Restaurar esta aba", False)
        if self.tab == TAB_PERF:
            self._button("bench", pygame.Rect(208, fy, 190, 42), "Medir (10 s)", False)
        if self.tab == TAB_SET:
            self._button("update_check", pygame.Rect(0, fy + 52, 250, 42), "Verificar atualização", False)
            if self.upd_label:
                self._button("update_apply", pygame.Rect(262, fy + 52, 298, 42), self.upd_label, False, True)
        self._button("quit", pygame.Rect(W - 150, fy, 150, 42), "Confirmar?" if armed else "Sair", True, armed)

        sy = fy + (108 if self.tab == TAB_SET else 56)
        if self.tab == TAB_PERF and self.live:
            self._txt(self.f_sb, self.live, (0, sy), OK, "l")
        elif self.tab == TAB_SET and self.info:
            self._txt(self.f_sb, self.info, (0, sy), OK if self.upd_label else DIM, "l")
        else:
            self._txt(self.f_s, "salvo automaticamente", (0, sy + 1), DIM, "l")
        # keyboard focus ring, drawn once the full focus order is known
        if self.kbd and self.order:
            fr = self.frects.get(self.order[self.focus % len(self.order)])
            if fr is not None:
                ui.rect(s, (*ACCENT2, 255), fr.inflate(6, 6), width=2, border_radius=12)
        return True

    def _button(self, cid, rect, label, danger, armed=False):
        self.hits.append((rect, cid, "btn", None))
        self.order.append(cid)
        self.order_val.append(None)
        self.frects[cid] = rect
        hov = self.hover == cid
        col = DANGER if danger else ACCENT2
        fill = col if armed else (SURFACE2 if hov else SURFACE)
        ui.rect(self.surf, (*fill, 255), rect, border_radius=10)
        ui.rect(self.surf, (*col, 255), rect, width=2 if (hov or armed) else 1, border_radius=10)
        tcol = ON_ACCENT if armed else (TEXT if hov else col)
        self._txt(self.fb, label, (rect.centerx, rect.y + 11), tcol, "c")

    def _row(self, row, y):
        s, c = self.surf, self.cfg
        cid, kind = row["id"], row["kind"]
        en = self.enabled(row)
        W = self.W
        fkey = cid if kind != "radio" else f"{cid}#{row['value']}"
        rowr = pygame.Rect(10, y, W - 20, self.ROW - 4)
        if self.hover == cid and en:
            ui.rect(s, (*SURFACE2, 255), rowr, border_radius=10)
        tc, dc = (TEXT, DIM) if en else (dimmed(TEXT, 0.5), dimmed(DIM, 0.55))
        lw = self._txt(self.f, row["label"], (22, y + 7), tc)
        if row.get("chip"):
            cr = pygame.Rect(22 + lw + 10, y + 8, 20, 20)
            ui.rect(s, (*BORDER, 255), cr, width=1, border_radius=5)
            self._txt(self.f_sb, row["chip"], (cr.centerx, cr.y + 2), dc, "c")
        h = row["help"](c) if callable(row["help"]) else row["help"]
        self._txt(self.f_s, h, (22, y + 29), dc)
        cy = y + (self.ROW - 4) // 2
        R = W - 26
        self.frects[fkey] = rowr
        if en:
            self.order.append(fkey)
            self.order_val.append(row.get("value"))

        if kind == "radio":
            sel = c[cid] == row["value"]
            rc = (R - 12, cy)
            ui.circle(s, (*(ACCENT if sel else BORDER), 255), rc, 11, 0 if sel else 2)
            if sel:
                ui.circle(s, (*ON_ACCENT, 255), rc, 4)
            self.hits.append((rowr, cid, "radio", row["value"]))
        elif kind == "toggle":
            on = c[cid]
            pill = pygame.Rect(R - 46, cy - 13, 46, 26)
            col = OK if on else (66, 64, 112)
            ui.rect(s, (*(col if en else dimmed(col)), 255), pill, border_radius=13)
            kx = pill.right - 13 if on else pill.left + 13
            ui.circle(s, (255, 255, 255) if en else dimmed((255, 255, 255)), (kx, pill.centery), 9)
            self._txt(self.f_s, "Ligado" if on else "Desligado", (pill.left - 10, cy - 8), (OK if (on and en) else dc), "r")
            self.hits.append((rowr, cid, "toggle", None))
        elif kind == "seg":
            widths = [max(56, self.f.size(l)[0] + 26) for l, _ in row["opts"]]
            x = R - sum(widths)
            n = len(widths)
            for i, ((lbl, val), w) in enumerate(zip(row["opts"], widths)):
                r = pygame.Rect(x, cy - 17, w, 34)
                sel = c[cid] == val
                hov = self.hover == cid and en
                fill = ACCENT if sel else ((44, 42, 84) if hov else (34, 32, 66))
                if not en:
                    fill = dimmed(fill, 0.6)
                radii = dict(border_top_left_radius=9 if i == 0 else 0, border_bottom_left_radius=9 if i == 0 else 0,
                             border_top_right_radius=9 if i == n - 1 else 0, border_bottom_right_radius=9 if i == n - 1 else 0)
                ui.rect(s, (*fill, 255), r, **radii)
                ui.rect(s, (*BORDER, 255), r, width=1, **radii)
                tcol = ON_ACCENT if sel else (tc if en else dc)
                self._txt(self.fb if sel else self.f, lbl, (r.centerx, r.y + 7), tcol, "c")
                self.hits.append((r, cid, "seg", val))
                x += w
        elif kind == "swatches":
            sw = 28
            n_ = len(row["items"])
            x0 = R - n_ * (sw + 4) + 4
            for i, col in enumerate(row["items"]):
                r_ = pygame.Rect(x0 + i * (sw + 4), cy - sw // 2, sw, sw)
                ui.rect(s, (*col, 255), r_, border_radius=6)
                sel = c[cid] == i
                ui.rect(s, (*(ACCENT if sel else BORDER), 255), r_.inflate(4, 4) if sel else r_, width=2 if sel else 1, border_radius=7)
                self.hits.append((r_, cid, "seg", i))
        elif kind == "action":
            br = pygame.Rect(R - 120, cy - 15, 120, 30)
            hov = self.hover == cid and en
            fill = (44, 42, 82) if hov else (34, 32, 66)
            ui.rect(s, (*(fill if en else dimmed(fill, 0.6)), 255), br, border_radius=9)
            ui.rect(s, (*(ACCENT2 if (hov and en) else BORDER), 255), br, width=1, border_radius=9)
            self._txt(self.fb, row["btn"], (br.centerx, br.y + 6), (ACCENT2 if en else dc), "c")
            self.hits.append((br, cid, "btn", None))
        elif kind == "text":
            fr = pygame.Rect(R - 250, cy - 16, 250, 32)
            foc = self.text_focus == cid
            ui.rect(s, (34, 32, 66, 255), fr, border_radius=8)
            ui.rect(s, (*(ACCENT if foc else BORDER), 255), fr, width=2 if foc else 1, border_radius=8)
            txt = str(c[cid]) + ("|" if foc and int(time.perf_counter() * 2) % 2 == 0 else "")
            self._txt(self.f, txt, (fr.x + 10, fr.y + 5), tc)
            self.hits.append((rowr, cid, "text", None))
        else:
            lo, hi = row["lo"], row["hi"]
            pw = 56
            tr = R - pw - 14
            tl = tr - 170
            self.slider_geo = (tl, 170)
            frac = (c[cid] - lo) / (hi - lo)
            hov = (self.hover == cid or self.drag == cid) and en
            ui.rect(s, (*(dimmed((54, 52, 96), 0.8) if not en else (54, 52, 96)), 255), (tl, cy - 3, 170, 6), border_radius=3)
            dfrac = (DEFAULTS[cid] - lo) / (hi - lo)
            pygame.draw.line(s, (*DIM, 255), (tl + int(170 * dfrac), cy + 7), (tl + int(170 * dfrac), cy + 11))
            ui.rect(s, (*(ACCENT if en else dimmed(ACCENT)), 255), (tl, cy - 3, max(4, int(170 * frac)), 6), border_radius=3)
            kc = (tl + int(170 * frac), cy)
            ui.circle(s, (255, 255, 255) if en else dimmed((255, 255, 255)), kc, 10 if hov else 9)
            ui.circle(s, (*(ACCENT if en else dimmed(ACCENT)), 255), kc, 10 if hov else 9, 2)
            vr = pygame.Rect(R - pw, cy - 14, pw, 28)
            ui.rect(s, (34, 32, 66, 255), vr, border_radius=8)
            self._txt(self.fb, f"{c[cid]}{row.get('unit', '%')}", (vr.centerx, vr.y + 4), tc, "c")
            self.hits.append((pygame.Rect(tl - 12, cy - 20, 170 + 24, 40), cid, "slider", None))
