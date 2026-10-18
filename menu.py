"""Settings panel (mouse + keyboard) and persistent settings.

Design: six tabs (Cenas, Câmera, Movimento, Imagem, Gráficos, Ajustes), grouped in cards. Every option has a label, a one-line explanation and a
clearly stateful control: toggle, segmented choice or slider. Disabled controls say why. Keyboard focus is
always visible. Changes apply instantly and show a short confirmation.
"""
import json
import os
import time

import pygame

APPDIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AudioOrganism")
PATH = os.path.join(APPDIR, "settings.json")

DEFAULTS = {"vsync": False, "fps_cap": 0, "fullscreen": False, "strobe": 2, "bursts": True, "bloom": 60, "react": 100,
            "effect": 0, "backend": 0, "style": 8, "style_v": 6, "camera": 0, "cam_orbit": 0, "cam_roll": 0, "cam_shake": 0, "cam_punch": 0, "cam_funnel": 2,
            "cam_fov_min": 90, "cam_fov_max": 90, "cam_fov_var": 0, "cam_sync": 0,
            "mv_speed": 1, "mv_rot": 2, "mv_dir": 0, "mv_pulse": 0, "mv_one": False, "mv_cuts": 1, "mv_inertia": 1, "movement": 0,
            # what the automatic modes may control (aba Auto)
            "auto_cam_orbit": True, "auto_cam_roll": True, "auto_cam_shake": True, "auto_cam_punch": True, "auto_cam_funnel": True,
            "auto_cam_fov": True, "auto_cam_sync": True, "auto_mv_speed": True, "auto_mv_rot": True, "auto_mv_pulse": True, "auto_mv_cuts": True,
            "auto_mv_inertia": True, "auto_scene": True, "auto_style": True, "auto_cuts": True, "auto_vars": True,
            # graphics (see PRESETS): render scale %, ray steps, ray-traced shadow / reflection / occlusion quality, lighting mode,
            # bloom levels, edge AA, panel density %, dynamic resolution and its FPS target
            "preset": 1, "res": 80, "steps": 60, "shadows": 1, "reflect": 1, "ao": 1, "rt": 0, "bloomq": 2, "aa_mode": 1, "detail": 75,
            "dynres": True, "fps_target": 60, "mblur": 90, "mblur_fps": 24, "auto_update": True,
            # more performance options: sharpening, bloom resolution, ray distance, render rate, lowest dynamic scale, panel refresh, GPU choice
            "sharp": 0, "bloomres": 0, "dist": 1, "rrate": 0, "dynmin": 40, "panel_hz": 20, "gpu": 0}

# graphics presets; any manual change of one of these options switches the preset to "Personalizado"
GFX_KEYS = ("res", "steps", "shadows", "reflect", "ao", "bloomq", "aa_mode", "detail", "rt", "mblur", "mblur_fps", "sharp", "bloomres", "dist")
PRESETS = [
    ("Baixo",  dict(res=60,  steps=48,  shadows=0, reflect=0, ao=0, bloomq=1, aa_mode=0, detail=55,  rt=0, mblur=0, mblur_fps=24, sharp=1, bloomres=1, dist=0)),
    ("Médio",  dict(res=80,  steps=60,  shadows=1, reflect=1, ao=1, bloomq=2, aa_mode=1, detail=75,  rt=0, mblur=90, mblur_fps=24, sharp=0, bloomres=0, dist=1)),
    ("Alto",   dict(res=100, steps=72,  shadows=2, reflect=2, ao=2, bloomq=3, aa_mode=3, detail=100, rt=1, mblur=180, mblur_fps=24, sharp=0, bloomres=0, dist=1)),
    ("Ultra",  dict(res=100, steps=110, shadows=3, reflect=3, ao=3, bloomq=4, aa_mode=4, detail=100, rt=1, mblur=270, mblur_fps=24, sharp=0, bloomres=0, dist=2)),
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
    return dict(DEFAULTS)


def load_cfg():
    cfg = fresh()
    data_style_v = 6
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        data_style_v = data.get("style_v", 1) if isinstance(data.get("style_v", 1), int) else 1
        for k, v in data.items():
            if k in cfg and type(v) is type(cfg[k]):
                cfg[k] = v
        if "aa_mode" not in data and "aa" in data:                 # older settings: the on/off edge switch
            cfg["aa_mode"] = 1 if data["aa"] else 0
    except Exception:
        pass
    if cfg["effect"] > 6:
        cfg["effect"] = 0
    if data_style_v < 6:                 # the style list changed: back to "scene default"
        cfg["style"] = 8
    cfg["style_v"] = 6
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


FPS_OPTS = [("Livre", 0), ("60", 60), ("120", 120), ("144", 144), ("240", 240)]
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
        dict(id="fps_cap", kind="seg", label="Limite de FPS", opts=FPS_OPTS,
             help=lambda c: "Desativado enquanto o VSync está ligado" if c["vsync"] else "Máximo de quadros por segundo",
             enabled=lambda c: not c["vsync"]),
    ]),
    ("DESEMPENHO", [
        dict(id="res", kind="slider", label="Escala de resolução", lo=25, hi=200, step=5, unit="%",
             help=lambda c: "Acima de 100%: supersampling, bem mais pesado" if c["res"] > 100 else "Menor = muito mais FPS, imagem mais suave  ·  duplo clique restaura"),
        dict(id="dynres", kind="toggle", label="Resolução dinâmica",
             help="Baixa a resolução sozinha quando o FPS cai do alvo"),
        dict(id="fps_target", kind="seg", label="FPS alvo", opts=TARGET_OPTS,
             help=lambda c: "A resolução dinâmica tenta manter este FPS" if c["dynres"] else "Ligue a resolução dinâmica para usar",
             enabled=lambda c: c["dynres"]),
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
        dict(id="rt", kind="seg", label="Modo de iluminação", opts=LIGHT_OPTS,
             help=lambda c: "Reflexo de ambiente e brilho, sem raios: muito mais leve" if not c["rt"] else "Raios de verdade: sombras e reflexos entre painéis"),
        dict(id="shadows", kind="seg", label="Sombras", opts=QUAL4_OPTS,
             help=lambda c: "Raio de sombra entre painéis" if c["rt"] else "Só no modo Ray tracing",
             enabled=lambda c: c["rt"] == 1),
        dict(id="reflect", kind="seg", label="Reflexos", opts=QUAL4_OPTS,
             help=lambda c: "Painéis refletem as cores dos vizinhos" if c["rt"] else "Só no modo Ray tracing",
             enabled=lambda c: c["rt"] == 1),
        dict(id="ao", kind="seg", label="Oclusão ambiente", opts=QUAL4_OPTS,
             help=lambda c: "Escurece os cantos onde painéis se encontram" if c["rt"] else "Só no modo Ray tracing",
             enabled=lambda c: c["rt"] == 1),
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
             help=lambda c: ["Sem suavização, o mais leve", "Cobertura nas bordas: boa e barata",
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
             help="Completo pisca rápido: cuidado com a luz"),
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
        dict(id="panel_hz", kind="seg", label="Atualização do painel", opts=[("10", 10), ("20", 20), ("30", 30), ("60", 60)],
             help="FPS do painel: menor poupa CPU"),
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


AUTO = [
    ("CÂMERA AUTO", [
        dict(id="auto_cam_orbit", kind="toggle", label="Órbita",
             help="Desmarcado: vale o seu controle na aba Câmera"),
        dict(id="auto_cam_roll", kind="toggle", label="Giro",
             help="Desmarcado: vale o seu controle na aba Câmera"),
        dict(id="auto_cam_shake", kind="toggle", label="Tremor no kick",
             help="Desmarcado: vale o seu controle na aba Câmera"),
        dict(id="auto_cam_punch", kind="toggle", label="Soco no kick",
             help="Desmarcado: vale o seu controle na aba Câmera"),
        dict(id="auto_cam_funnel", kind="toggle", label="Funil",
             help="Desmarcado: vale o seu controle na aba Câmera"),
        dict(id="auto_cam_fov", kind="toggle", label="Lente (FOV)",
             help="Mínimo, máximo e variação do ângulo"),
        dict(id="auto_cam_sync", kind="toggle", label="Sincronia com o ritmo",
             help="Compasso ou frase"),
    ]),
    ("MOVIMENTO AUTO", [
        dict(id="auto_mv_speed", kind="toggle", label="Velocidade geral",
             help="Desmarcado: vale o seu controle na aba Movimento"),
        dict(id="auto_mv_rot", kind="toggle", label="Rotação e direção",
             help="Desmarcado: vale o seu controle na aba Movimento"),
        dict(id="auto_mv_pulse", kind="toggle", label="Pulso no kick",
             help="Inclui pulsar só na batida 1"),
        dict(id="auto_mv_cuts", kind="toggle", label="Frequência dos cortes",
             help="Desmarcado: vale o seu controle na aba Movimento"),
        dict(id="auto_mv_inertia", kind="toggle", label="Inércia",
             help="Desmarcado: vale o seu controle na aba Movimento"),
    ]),
    ("TROCAS AUTO", [
        dict(id="auto_scene", kind="toggle", label="Cena",
             help="Ligado: o Automático troca a cena pelo gênero e pelas partes"),
        dict(id="auto_style", kind="toggle", label="Estilo",
             help="Ligado: o estilo Automático muda pelas partes"),
        dict(id="auto_cuts", kind="toggle", label="Cortes de cor e universo",
             help="Na batida e na virada de frase"),
        dict(id="auto_vars", kind="toggle", label="Trocas de cor por elemento",
             help="O sequenciador 4/4 das camadas"),
    ]),
]
MV_OPTS = [(n, i) for i, (n, _) in enumerate(MV_PRESETS)] + [("Auto", MV_AUTO), ("Manual", MV_MANUAL)]
MOVEMENT = [
    ("PREDEFINIÇÃO", [
        dict(id="movement", kind="seg", label="Modo", opts=MV_OPTS,
             help=lambda c: "Muda pela música (veja a aba Auto)" if c["movement"] == MV_AUTO else ("Ajustado por você" if c["movement"] == MV_MANUAL else "Preenche os controles")),
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
        dict(id="mv_cuts", kind="seg", label="Frequência dos cortes", opts=[("Raros", 0), ("Normais", 1), ("Frequentes", 2)],
             help="Trocas de cor e universo na batida", enabled=lambda c: _mv_on("cuts")(c)),
    ]),
]
_ROWS = {r["id"]: r for _, rs in GRAPHICS + SETTINGS for r in rs if r["kind"] != "radio"}


def _card(title, *ids):
    return (title, [_ROWS[i] for i in ids])


# five tabs, one purpose each: what is drawn / how the camera moves / how the picture looks / how heavy it is / the program itself
TABS = [
    ("Cenas", SCENES + STYLES),
    ("Câmera", CAMERA),
    ("Movimento", MOVEMENT),
    ("Auto", AUTO),
    ("Imagem", [_card("BRILHO", "bloomq", "bloom", "bloomres"), _card("MOTION BLUR", "mblur", "mblur_fps"), _card("SUAVIZAÇÃO", "aa_mode", "sharp")]),
    ("Gráficos", [_card("PREDEFINIÇÃO", "preset"), _card("RESOLUÇÃO E FPS", "res", "dynres", "fps_target", "dynmin", "rrate"),
                    _card("RAIOS E CAMADAS", "detail", "steps", "dist"),
                    _card("ILUMINAÇÃO", "rt", "shadows", "reflect", "ao")]),
    ("Ajustes", [_card("TELA", "fullscreen", "vsync", "fps_cap"), _card("MÚSICA E LUZ", "strobe", "bursts", "react"),
                 _card("SISTEMA", "backend", "gpu", "panel_hz", "auto_update")]),
]
TAB_PERF = [n for n, _ in TABS].index("Gráficos")
TAB_SET = [n for n, _ in TABS].index("Ajustes")
NAMES = {"fullscreen": "Tela cheia", "vsync": "VSync", "fps_cap": "Limite de FPS", "strobe": "Flashes",
         "bursts": "Rajadas", "bloom": "Intensidade do brilho", "react": "Reatividade", "effect": "Cena", "res": "Resolução",
         "backend": "Backend", "preset": "Qualidade", "steps": "Passos do raio", "shadows": "Sombras", "reflect": "Reflexos",
         "ao": "Oclusão", "bloomq": "Brilho", "aa_mode": "Suavização", "sharp": "Nitidez", "bloomres": "Resolução do brilho", "dist": "Distância", "rrate": "Taxa de renderização", "dynmin": "Escala mínima", "gpu": "Placa de vídeo", "panel_hz": "Painel", "detail": "Densidade", "rt": "Iluminação",
         "style": "Estilo", "camera": "Câmera", "cam_orbit": "Órbita", "cam_roll": "Giro", "cam_shake": "Tremor", "cam_punch": "Soco", "cam_funnel": "Funil", "cam_fov_min": "FOV mínimo", "cam_fov_max": "FOV máximo", "cam_fov_var": "Variação do FOV", "cam_sync": "Sincronia", "auto_cam_orbit": "Auto: órbita", "auto_cam_roll": "Auto: giro", "auto_cam_shake": "Auto: tremor", "auto_cam_punch": "Auto: soco", "auto_cam_funnel": "Auto: funil", "auto_cam_fov": "Auto: FOV", "auto_cam_sync": "Auto: sincronia", "auto_mv_speed": "Auto: velocidade", "auto_mv_rot": "Auto: rotação", "auto_mv_pulse": "Auto: pulso", "auto_mv_cuts": "Auto: cortes", "auto_mv_inertia": "Auto: inércia", "auto_scene": "Auto: cena", "auto_style": "Auto: estilo", "auto_cuts": "Auto: cortes de cor", "auto_vars": "Auto: cor por elemento",  "movement": "Movimento", "mv_speed": "Velocidade", "mv_inertia": "Inércia", "mv_rot": "Rotação", "mv_dir": "Direção", "mv_pulse": "Pulso", "mv_one": "Pulso só na batida 1", "mv_cuts": "Cortes", "mblur": "Obturador", "auto_update": "Verificação de atualização", "mblur_fps": "Quadros de referência", "dynres": "Resolução dinâmica", "fps_target": "FPS alvo"}


class Menu:
    W = 560
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
        self.heights = []
        for tname, secs in TABS:
            h = self.HEAD
            for _, rows in secs:
                h += 40 + len(rows) * self.ROW + 10 + self.GAP
            self.heights.append(h + self.FOOT + (112 if tname == TABS[TAB_SET][0] else 0))      # the Ajustes tab has a second row of buttons (updates)
        self.H = max(self.heights)                  # the surface fits the tallest tab
        self.surf = pygame.Surface((self.W, self.H), pygame.SRCALPHA)

    # ------------------------------------------------------------ state
    def touch(self):
        self.dirty = self.need = True
        self.dirty_t = time.perf_counter()

    def max_scroll(self):
        return max(0, self.heights[self.tab] - self.view_h)

    def scroll_to_focus(self):
        if not self.order:
            return
        fr = self.frects.get(self.order[self.focus % len(self.order)])
        if fr is None:
            return
        if fr.top < self.scroll + 8:
            self.scroll = max(0, fr.top - 8)
        elif fr.bottom > self.scroll + self.view_h - 8:
            self.scroll = min(self.max_scroll(), fr.bottom - self.view_h + 8)

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
        if cid == "cam_fov_min" and value > self.cfg["cam_fov_max"]:
            self.cfg["cam_fov_max"] = value
        if cid == "cam_fov_max" and value < self.cfg["cam_fov_min"]:
            self.cfg["cam_fov_min"] = value
        if cid in CAM_KEYS and self.cfg["camera"] != CAM_AUTO:
            self.cfg["camera"] = match_camera(self.cfg)
        if cid in MV_KEYS and self.cfg["movement"] != MV_AUTO:
            self.cfg["movement"] = match_movement(self.cfg)
        if cid in GFX_KEYS:
            self.cfg["preset"] = match_preset(self.cfg)
        self.touch()
        if announce:
            row = self.find(cid)
            if row["kind"] == "toggle":
                self.say(f"{NAMES[cid]}: {'ligado' if value else 'desligado'}")
            elif row["kind"] == "seg":
                lbl = [l for l, v in row["opts"] if v == value][0]
                self.say(f"{NAMES[cid]}: {lbl}" + ("  ·  reinicie para aplicar" if cid == "backend" else ""))

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
            self.tab = int(cid[3:])
            self.scroll = 0
            self.need = True
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
            if row["kind"] == "radio":
                self.set_value(cid, self.order_val[self.focus % len(self.order)])
            elif row["kind"] == "toggle":
                self.adjust(cid, 0)
            elif row["kind"] == "seg":
                vals = [v for _, v in row["opts"]]
                i = vals.index(self.cfg[cid]) if self.cfg[cid] in vals else 0
                if self.enabled(row):
                    self.set_value(cid, vals[(i + 1) % len(vals)])
        elif k == pygame.K_ESCAPE:
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
            if kind == "toggle":
                self.adjust(cid, 0)
            elif kind in ("seg", "radio"):
                self.set_value(cid, arg)
            elif kind == "slider":
                now = time.perf_counter()
                if self.last_click[0] == cid and now - self.last_click[1] < 0.4:
                    default = DEFAULTS[cid]
                    self.set_value(cid, default, announce=False)
                    self.say(f"{NAMES[cid]} restaurado: {default}{self.find(cid).get('unit', '%')}")
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
            pygame.draw.rect(s, (*(ACCENT if sel else (SURFACE2 if hov else SURFACE)), 255), r, border_radius=10)
            if not sel:
                pygame.draw.rect(s, (*BORDER, 255), r, width=1, border_radius=10)
            self._txt(self.ftab, name, (r.centerx, r.y + 9), ON_ACCENT if sel else TEXT, "c")
            self.hits.append((r, cid, "btn", None))
            self.order.append(cid)
            self.order_val.append(None)
            self.frects[cid] = r
            x += tw + 6
        y = self.HEAD
        for title, rows in TABS[self.tab][1]:
            ch = 40 + len(rows) * self.ROW + 10
            pygame.draw.rect(s, (*SURFACE, 255), (0, y, W, ch), border_radius=14)
            pygame.draw.rect(s, (*BORDER, 255), (0, y, W, ch), width=1, border_radius=14)
            self._txt(self.f_sb, "  ".join(title), (18, y + 14), ACCENT)
            ry = y + 40
            for row in rows:
                self._row(row, ry)
                ry += self.ROW
            y += ch + self.GAP

        # footer buttons
        fy = y + 4
        armed = self.quit_armed > now
        if self.tab >= 1:
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
                pygame.draw.rect(s, (*ACCENT2, 255), fr.inflate(6, 6), width=2, border_radius=12)
        return True

    def _button(self, cid, rect, label, danger, armed=False):
        self.hits.append((rect, cid, "btn", None))
        self.order.append(cid)
        self.order_val.append(None)
        self.frects[cid] = rect
        hov = self.hover == cid
        col = DANGER if danger else ACCENT2
        fill = col if armed else (SURFACE2 if hov else SURFACE)
        pygame.draw.rect(self.surf, (*fill, 255), rect, border_radius=10)
        pygame.draw.rect(self.surf, (*col, 255), rect, width=2 if (hov or armed) else 1, border_radius=10)
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
            pygame.draw.rect(s, (*SURFACE2, 255), rowr, border_radius=10)
        tc, dc = (TEXT, DIM) if en else (dimmed(TEXT, 0.5), dimmed(DIM, 0.55))
        lw = self._txt(self.f, row["label"], (22, y + 7), tc)
        if row.get("chip"):
            cr = pygame.Rect(22 + lw + 10, y + 8, 20, 20)
            pygame.draw.rect(s, (*BORDER, 255), cr, width=1, border_radius=5)
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
            pygame.draw.circle(s, (*(ACCENT if sel else BORDER), 255), rc, 11, 0 if sel else 2)
            if sel:
                pygame.draw.circle(s, (*ON_ACCENT, 255), rc, 4)
            self.hits.append((rowr, cid, "radio", row["value"]))
        elif kind == "toggle":
            on = c[cid]
            pill = pygame.Rect(R - 46, cy - 13, 46, 26)
            col = OK if on else (66, 64, 112)
            pygame.draw.rect(s, (*(col if en else dimmed(col)), 255), pill, border_radius=13)
            kx = pill.right - 13 if on else pill.left + 13
            pygame.draw.circle(s, (255, 255, 255) if en else dimmed((255, 255, 255)), (kx, pill.centery), 9)
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
                pygame.draw.rect(s, (*fill, 255), r, **radii)
                pygame.draw.rect(s, (*BORDER, 255), r, width=1, **radii)
                tcol = ON_ACCENT if sel else (tc if en else dc)
                self._txt(self.fb if sel else self.f, lbl, (r.centerx, r.y + 7), tcol, "c")
                self.hits.append((r, cid, "seg", val))
                x += w
        else:
            lo, hi = row["lo"], row["hi"]
            pw = 56
            tr = R - pw - 14
            tl = tr - 170
            self.slider_geo = (tl, 170)
            frac = (c[cid] - lo) / (hi - lo)
            hov = (self.hover == cid or self.drag == cid) and en
            pygame.draw.rect(s, (*(dimmed((54, 52, 96), 0.8) if not en else (54, 52, 96)), 255), (tl, cy - 3, 170, 6), border_radius=3)
            dfrac = (DEFAULTS[cid] - lo) / (hi - lo)
            pygame.draw.line(s, (*DIM, 255), (tl + int(170 * dfrac), cy + 7), (tl + int(170 * dfrac), cy + 11))
            pygame.draw.rect(s, (*(ACCENT if en else dimmed(ACCENT)), 255), (tl, cy - 3, max(4, int(170 * frac)), 6), border_radius=3)
            kc = (tl + int(170 * frac), cy)
            pygame.draw.circle(s, (255, 255, 255) if en else dimmed((255, 255, 255)), kc, 10 if hov else 9)
            pygame.draw.circle(s, (*(ACCENT if en else dimmed(ACCENT)), 255), kc, 10 if hov else 9, 2)
            vr = pygame.Rect(R - pw, cy - 14, pw, 28)
            pygame.draw.rect(s, (34, 32, 66, 255), vr, border_radius=8)
            self._txt(self.fb, f"{c[cid]}{row.get('unit', '%')}", (vr.centerx, vr.y + 4), tc, "c")
            self.hits.append((pygame.Rect(tl - 12, cy - 20, 170 + 24, 40), cid, "slider", None))
