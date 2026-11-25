"""The layers of a scene: a stack of effects and backgrounds that can be added in any number, like adjustment layers.

A scene keeps `layers`, a list from the bottom to the top. Every layer is a dict with its type `t`, `on`, `op` (opacity %), `bm` (blend mode) and the
parameters of its type; the layers that follow the music also carry the follow set (src, famt, atk, rel, thr, gain, inv, curve).

  effects      fb rastro · ca aberração cromática · edge desfoque nas bordas · fl reflexo de lente · gr grão · tone mapa de tons · part partículas
  backgrounds  grad gradiente (sólido, linear, radial) · lights luzes de fundo

An effect acts on everything below it; a background is laid behind the picture. Scenes saved before the layers existed (fx_*, scene_bg, bg_light ...)
are converted by `migrate`. The editor edits one layer at a time through working keys `lp_<param>` (see `load_lp`)."""
import copy

TYPES = {
    "fb": dict(label="Rastro", tag="RASTRO", group="fx", help="A imagem anterior volta e some devagar"),
    "ca": dict(label="Aberração cromática", tag="ABERRAÇÃO", group="fx", help="Vermelho e azul se separam"),
    "edge": dict(label="Desfoque nas bordas", tag="BORDAS", group="fx", help="Uma lente fora de foco nos cantos"),
    "fl": dict(label="Reflexo de lente", tag="REFLEXO", group="fx", help="Raio e fantasmas nas partes brilhantes"),
    "gr": dict(label="Grão de filme", tag="GRÃO", group="fx", help="Granulado que se mexe"),
    "tone": dict(label="Equilíbrio de luz e cor", tag="TONS", group="fx", help="Como o brilho forte vira cor"),
    "part": dict(label="Partículas", tag="PARTÍCULAS", group="part", help="Milhares de pontos de luz que se movem com a música"),
    "grad": dict(label="Gradiente", tag="GRADIENTE", group="bg", help="Uma cor ou gradiente atrás da imagem"),
    "lights": dict(label="Luzes de fundo", tag="LUZES", group="bg", help="Aurora, feixes, pulsos, estrelas ou faixas"),
}
ORDER = ("grad", "lights", "part", "fb", "edge", "ca", "fl", "gr", "tone")        # the order of the "add" list
BLEND = [("Normal", 0), ("Somar", 1), ("Tela", 2), ("Sobrepor", 3)]
SOURCES = [("Nada", 0), ("Bumbo (kick)", 1), ("Caixa", 2), ("Chimbal", 3), ("Graves", 4), ("Médios", 5), ("Agudos", 6), ("Energia", 7), ("Tensão", 8), ("Drop", 9)]
MAX_FX = 8                          # effect layers drawn as separate passes (the cost is one full-screen pass each)
MAX_BG = 4

SLOTS = (("bg", "Fundo", "Cor ou gradiente atrás de tudo"), ("lights", "Luzes", "Luzes de fundo: aurora, feixes, lasers…"),
         ("form", "Forma principal", "O desenho do meio: mandala, túnel, fractal…"), ("parts", "Partículas e rastro", "Pontos de luz e o rastro da imagem"),
         ("finish", "Acabamento", "Efeitos de lente, cor final e estilo da imagem"), ("over", "Texto e logo", "Um texto ou o seu logo por cima de tudo"))
SLOT_OF = {"grad": "bg", "lights": "lights", "part": "parts", "fb": "parts", "edge": "finish", "ca": "finish", "fl": "finish", "gr": "finish", "tone": "finish"}


def slot_on(sc, slot):
    """Is layer `slot` (see SLOTS) of scene `sc` on? Scenes from before the six layers have them all on except the Sobreposição."""
    return bool(sc.get("ly_" + slot, slot != "over"))


def active_layers(sc):
    """The stack of the scene without the layers of a slot that is turned off (the stored list is never changed: turning a slot on again brings it back)."""
    return [l for l in (sc.get("layers") or []) if slot_on(sc, SLOT_OF.get(l.get("t"), "finish"))]


COMMON = dict(on=True, op=100, bm=0)
FOLLOW = dict(src=0, famt=50, atk=0, rel=25, thr=0, gain=100, inv=False, curve=0)
DEFAULT_COLS = [[10, 0, 40], [235, 8, 56], [0, 79, 236]]
OWN = {
    "fb": dict(amt=60, zoom=0, rot=0, hue=0, blur=0, fbt=0),
    "ca": dict(amt=50, dir=0, start=0, blur=0),
    "edge": dict(amt=50, r=0, shape=0),
    "fl": dict(amt=50, len=100, col=0, n=1, blur=0),
    "gr": dict(amt=50, size=1, where=0, color=0, fps=0, blur=0),
    "tone": dict(mode=1),
    "part": dict(amt=100, count=2, pmode=0, psize=50),
    "grad": dict(amt=100, gtype=1, gcol=0, gdir=0, greact=0, gtrans=2, gevery=1),
    "lights": dict(amt=100, style=1, speed=100, lcol=0),
}
FOLLOWS = ("fb", "ca", "edge", "fl", "gr", "part", "grad", "lights")           # the types that can follow the music (the others have no amount)

# every parameter name with its default, for the working keys of the editor (lp_<name>)
PARAMS = dict(COMMON)
PARAMS.update(FOLLOW)
for _d in OWN.values():
    PARAMS.update(_d)
PARAMS.update(gitem=0, gr_=10, gg_=0, gb_=40)                                  # the colour of a gradient being edited (see load_lp)
LP_DEFAULTS = {"lp_" + k: v for k, v in PARAMS.items()}


def new_layer(t):
    d = dict(t=t, **COMMON)
    d.update(OWN[t])
    if t in FOLLOWS:
        d.update(FOLLOW)
    if t == "grad":
        d["cols"] = copy.deepcopy(DEFAULT_COLS)
    return d


def name_of(layer):
    return TYPES.get(layer.get("t"), {}).get("label", "?")


def detail_of(layer):
    """The short text in the list: what this layer does."""
    t = layer.get("t")
    if t == "grad":
        return ("Sólido", "Linear", "Radial")[int(layer.get("gtype", 1)) % 3]
    if t == "lights":
        return ("", "Aurora", "Feixes", "Pulsos", "Estrelas", "Faixas", "Lasers", "Feixe")[int(layer.get("style", 1)) % 8]
    if t == "part":
        return ("Fluxo", "Explosão", "Órbita")[int(layer.get("pmode", 0)) % 3]
    if t == "tone":
        return ("Padrão", "Fílmico", "Mantém o matiz")[int(layer.get("mode", 1)) % 3]
    if t in OWN and "amt" in OWN[t]:
        s = f"{int(layer.get('amt', 0))}%"
        if int(layer.get("src", 0)) > 0:
            s += " · " + SOURCES[int(layer["src"]) % 10][0].lower()
        return s
    return ""


def counts(layers):
    fx = sum(1 for l in layers if TYPES.get(l.get("t"), {}).get("group") in ("fx",))
    bg = sum(1 for l in layers if TYPES.get(l.get("t"), {}).get("group") == "bg")
    return fx, bg


# ------------------------------------------------------------------ the editor's working keys
def load_lp(cfg):
    """Copy the selected layer into the working keys lp_<param> (what the rows of the editor show)."""
    layers = cfg.get("layers") or []
    sel = max(0, min(int(cfg.get("ly_sel", 0)), max(0, len(layers) - 1)))
    cfg["ly_sel"] = sel
    layer = layers[sel] if layers else None
    for k, v in PARAMS.items():
        cfg["lp_" + k] = (layer.get(k, v) if layer is not None else v)
    cols = (layer or {}).get("cols") or DEFAULT_COLS
    i = max(0, min(len(cols) - 1, int(cfg.get("lp_gitem", 0))))
    cfg["lp_gitem"] = i
    cfg["lp_gr_"], cfg["lp_gg_"], cfg["lp_gb_"] = cols[i]


def write_lp(cfg, key, value):
    """A working key was changed: write it into the selected layer. Returns True when the rows must be rebuilt (the change shows or hides other rows)."""
    layers = cfg.get("layers") or []
    sel = int(cfg.get("ly_sel", 0))
    if not (0 <= sel < len(layers)):
        return False
    layer = layers[sel]
    name = key[3:]
    if name in ("gr_", "gg_", "gb_"):
        cols = layer.setdefault("cols", copy.deepcopy(DEFAULT_COLS))
        cols[max(0, min(len(cols) - 1, int(cfg.get("lp_gitem", 0))))] = [cfg["lp_gr_"], cfg["lp_gg_"], cfg["lp_gb_"]]
        return True
    if name == "gitem":
        load_lp(cfg)
        return True
    layer[name] = value
    return name in ("src", "gtype", "gcol", "style", "on")


# ------------------------------------------------------------------ stack templates
def _t(t, **kw):
    d = new_layer(t)
    d.update(kw)
    return d


TEMPLATES = [
    ("Limpo", "Tira todos os efeitos (os fundos ficam)", lambda: []),
    ("Cinema", "Fílmico, aberração leve, raio azul e grão a 24 por segundo",
     lambda: [_t("tone", mode=1), _t("edge", amt=30, r=30), _t("ca", amt=15), _t("fl", amt=35, len=140), _t("gr", amt=25, size=2, fps=1)]),
    ("VHS", "Cores que escorrem para os lados e grão colorido",
     lambda: [_t("edge", amt=15), _t("ca", amt=55, dir=1), _t("gr", amt=45, color=1, size=2, fps=1)]),
    ("Câmera velha", "Cantos fora de foco, reflexo quente e grão grosso",
     lambda: [_t("tone", mode=1), _t("edge", amt=50, r=25), _t("ca", amt=25), _t("fl", amt=20, col=1), _t("gr", amt=70, size=3, fps=1)]),
    ("Pulsa", "Aberração e reflexo respondem ao bumbo, o desfoque aos graves",
     lambda: [_t("edge", amt=25, src=4, famt=60), _t("ca", amt=40, src=1, famt=80), _t("fl", amt=60, src=1, famt=70)]),
    ("Psicodélico", "Rastro que gira e muda de cor, aberração e partículas",
     lambda: [_t("part", count=2), _t("fb", amt=80, zoom=4, rot=3, hue=5), _t("ca", amt=40)]),
]


def apply_template(layers, i):
    """The layers after template i: the backgrounds stay, the effects are replaced by the template's."""
    keep = [l for l in layers if TYPES.get(l.get("t"), {}).get("group") == "bg"]
    return keep + TEMPLATES[max(0, min(len(TEMPLATES) - 1, i))][2]()


# ------------------------------------------------------------------ scenes of older versions
def migrate(sc):
    """Give a scene saved before the layers existed its `layers`: the effects (fx_*), the gradient background (scene_bg 2..4) and the lights (bg_light) become layers.
    Returns True when the scene was converted."""
    legacy = [k for k in sc if k.startswith("fx_")]
    if isinstance(sc.get("layers"), list):
        for k in legacy:
            sc.pop(k, None)
        return False
    g = sc.get
    L = []

    def follow(prefix, layer):
        for k in FOLLOW:
            v = g(f"fx_{prefix}_{ {'famt': 'amt'}.get(k, k) }", None)
            if v is not None:
                layer[k] = v
        mix = g(f"fx_{prefix}_mix", None)
        if mix is not None:
            layer["op"] = mix
        return layer
    bg = int(g("scene_bg", 0))
    if bg >= 2:
        L.append(_t("grad", gtype={2: 0, 3: 1, 4: 2}[bg], gcol=g("bgc_src", 0), gdir=g("bgc_dir", 0), greact=g("bgc_react", 0), gtrans=g("bgc_trans", 2),
                    gevery=g("bgc_every", 1), cols=copy.deepcopy(g("bgc_cols", DEFAULT_COLS))))
        sc["scene_bg"] = 1                                           # the gradient replaced the palette's background: the base under the layers is black
    if int(g("bg_light", 0)) > 0:
        L.append(_t("lights", style=int(g("bg_light", 1)), amt=g("bg_int", 100), speed=g("bg_speed", 100), lcol=g("bg_col", 0)))
        sc["bg_light"] = 0
    if int(g("fx_part", 0)) > 0:
        L.append(_t("part", count=int(g("fx_part", 0)), pmode=g("fx_pmode", 0), psize=g("fx_psize", 50)))
    if g("fx_fb", 0) > 0:
        L.append(follow("fb", _t("fb", amt=g("fx_fb", 0), zoom=g("fx_fbzoom", 0), rot=g("fx_fbrot", 0), hue=g("fx_fbhue", 0), blur=g("fx_fb_blur", 0))))
    if g("fx_edge", 0) > 0:
        L.append(follow("edge", _t("edge", amt=g("fx_edge", 0), r=g("fx_edge_r", 0), shape=g("fx_edge_shape", 0))))
    if g("fx_ca", 0) > 0:
        L.append(follow("ca", _t("ca", amt=g("fx_ca", 0), dir=g("fx_ca_dir", 0), start=g("fx_ca_start", 0), blur=g("fx_ca_blur", 0))))
    if g("fx_flare", 0) > 0:
        L.append(follow("fl", _t("fl", amt=g("fx_flare", 0), len=g("fx_fl_len", 100), col=g("fx_fl_col", 0), n=g("fx_fl_n", 1), blur=g("fx_fl_blur", 0))))
    if g("fx_grain", 0) > 0:
        L.append(follow("gr", _t("gr", amt=g("fx_grain", 0), size=g("fx_gr_size", 1), where=g("fx_gr_where", 0), color=g("fx_gr_color", 0), fps=g("fx_gr_fps", 0),
                                 blur=g("fx_gr_blur", 0))))
    if int(g("fx_tone", 0)) > 0:
        L.append(_t("tone", mode=int(g("fx_tone", 0))))
    for k in legacy:
        sc.pop(k, None)
    sc["layers"] = L
    return True


# ------------------------------------------------------------------ the rows of the editor
def list_items(cfg, slot=None):
    """The rows of the list of layers (top first), the "add" menu and the stack templates. With `slot` (see SLOTS) only the layers of that one, and only its kinds to add."""
    layers = cfg.get("layers") or []
    n = len(layers)
    keep = lambda i: slot is None or SLOT_OF.get(layers[i].get("t")) == slot
    items = [dict(id=f"ly_row{i}", kind="layer", idx=i, label="", help="") for i in range(n - 1, -1, -1) if keep(i)]
    fx, bg = counts(layers)
    kinds = [t for t in ORDER if slot is None or SLOT_OF.get(t) == slot]
    if not items:
        items.append(dict(id="ly_empty", kind="note", label="Nada aqui ainda", help="Adicione abaixo", idx=-1))
    items.append(dict(id="ly_add", kind="dd", label="Adicionar", placeholder="Escolha o tipo…", opts=[(TYPES[t]["label"], t) for t in kinds],
                      help=f"{fx} de {MAX_FX} efeitos  ·  {bg} de {MAX_BG} fundos"))
    if slot is not None:
        return items
    items.append(dict(id="ly_tpl", kind="dd", label="Começar de um modelo", placeholder="Aplicar um modelo…", opts=[(t[0], i) for i, t in enumerate(TEMPLATES)],
                      help="Troca os efeitos desta cena por um conjunto pronto"))
    return items


def first_of(cfg, slot):
    """The index of the top layer of `slot` in the stack, or -1."""
    layers = cfg.get("layers") or []
    return next((i for i in range(len(layers) - 1, -1, -1) if SLOT_OF.get(layers[i].get("t")) == slot), -1)


def detail_cards(cfg):
    """The parameters of the layer selected, and what it follows in the music."""
    layers = cfg.get("layers") or []
    n = len(layers)
    if not n:
        return []
    sel = max(0, min(int(cfg.get("ly_sel", 0)), n - 1))
    layer = layers[sel]
    t = layer.get("t")
    info = TYPES.get(t, TYPES["fb"])
    on = lambda c: bool(c["lp_on"])
    head = [dict(id="lp_on", kind="toggle", label="Ligada", help="Desligada, a camada fica na lista mas não age")]
    if info["group"] in ("fx", "bg") and t != "tone":
        head.append(dict(id="lp_bm", kind="dd", label="Mistura", opts=BLEND,
                         help=lambda c: ["Substitui o que está abaixo", "Soma luz ao que está abaixo", "Clareia sem estourar", "Mistura mantendo luzes e sombras"][c["lp_bm"] % 4], enabled=on))
        head.append(dict(id="lp_op", kind="slider", label="Opacidade", lo=0, hi=100, step=5, unit="%", help="Quanto desta camada entra na imagem", enabled=on))
    extra = grad_rows(cfg, on) if t == "grad" else []
    cards = [(info["label"].upper(), head + type_rows(t, on) + extra)]
    if t in FOLLOWS:
        cards.append(("SEGUIR A MÚSICA", follow_rows(cfg, on)))
    return cards


def rows(cfg):
    """The base of the background, the list and the detail together (what the Camadas section was before the editor had its own list)."""
    base = ("FUNDO BASE", [dict(id="scene_bg", kind="seg", label="Fundo base", opts=[("Paleta", 0), ("Preto", 1)],
                                help=lambda c: ["O fundo da paleta da cena, sob as camadas", "Preto, sob as camadas"][c["scene_bg"] % 2])])
    return [base, ("CAMADAS  ·  A DE CIMA POR ÚLTIMO", list_items(cfg))] + detail_cards(cfg)


def type_rows(t, on):
    def S(i, lab, lo, hi, step, help, unit="%"):
        return dict(id=f"lp_{i}", kind="slider", label=lab, lo=lo, hi=hi, step=step, unit=unit, help=help, enabled=on)

    def G(i, lab, opts, help):
        return dict(id=f"lp_{i}", kind="seg", label=lab, opts=opts, help=help, enabled=on)
    if t == "fb":
        return [S("amt", "Rastro", 0, 95, 5, "A imagem anterior volta e some devagar"), S("zoom", "Zoom", -10, 10, 1, "Positivo se afasta do centro, negativo afunda", ""),
                S("rot", "Giro", -10, 10, 1, "O rastro gira a cada quadro", ""), S("hue", "Cor", -20, 20, 1, "O matiz muda enquanto o rastro some", ""),
                S("blur", "Desfoque do efeito", 0, 100, 5, "O rastro se espalha enquanto some"),
                G("fbt", "Onde", [("Imagem toda", 0), ("Só partículas", 1)], "Só partículas: a forma fica nítida e só os pontos de luz deixam rastro")]
    if t == "ca":
        return [S("amt", "Intensidade", 0, 100, 5, "Vermelho e azul se separam"),
                G("dir", "Direção", [("Radial", 0), ("Horizontal", 1), ("Vertical", 2)], "Do centro para as bordas, para os lados (VHS) ou para cima e baixo"),
                S("start", "Começa em", 0, 80, 5, "Distância do centro onde o efeito começa"), S("blur", "Desfoque do efeito", 0, 100, 5, "Suaviza as franjas")]
    if t == "edge":
        return [S("amt", "Intensidade", 0, 100, 5, "Como uma lente fora de foco nos cantos"), S("r", "Centro nítido", 0, 80, 5, "Tamanho da região que fica em foco"),
                G("shape", "Formato", [("Redondo", 0), ("Hexagonal", 1), ("Faixa", 2)], "Foco circular, em hexágono ou uma faixa horizontal (tilt-shift)")]
    if t == "fl":
        return [S("amt", "Intensidade", 0, 100, 5, "Raio horizontal e fantasmas nas partes brilhantes"), S("len", "Comprimento do raio", 20, 200, 10, "Quão longe o raio se estende"),
                G("col", "Cor", [("Azul", 0), ("Quente", 1), ("Branco", 2)], "Anamórfico azul, âmbar ou neutro"),
                G("n", "Fantasmas", [("1", 1), ("2", 2), ("3", 3), ("4", 4)], "Reflexos do outro lado da imagem"), S("blur", "Desfoque do efeito", 0, 100, 5, "Difunde o raio e os fantasmas")]
    if t == "gr":
        return [S("amt", "Intensidade", 0, 100, 5, "Granulado que se mexe"),
                G("size", "Tamanho", [("Fino", 1), ("Médio", 2), ("Grosso", 3), ("Muito grosso", 4)], "Tamanho de cada grão em pixels"),
                G("where", "Onde pesa", [("Tudo", 0), ("Sombras", 1), ("Realces", 2)], "Em que parte do brilho o grão aparece mais"),
                G("color", "Cor", [("Cinza", 0), ("Colorido", 1)], "Colorido separa em vermelho, verde e azul"),
                G("fps", "Ritmo", [("A cada quadro", 0), ("24 por segundo", 1)], "24 dá o jeito de filme"), S("blur", "Desfoque do efeito", 0, 100, 5, "Grão macio")]
    if t == "tone":
        return [G("mode", "Mapa de tons", [("Padrão", 0), ("Fílmico", 1), ("Mantém o matiz", 2)], "Padrão: brilho suave  ·  Fílmico: contraste de cinema  ·  Mantém o matiz: cores sem desbotar")]
    if t == "part":
        return [S("amt", "Brilho", 0, 100, 5, "Quanta luz cada ponto emite"),
                G("count", "Quantas partículas", [("16 mil", 1), ("65 mil", 2), ("262 mil", 3)], "Mais partículas deixam mais bonito e mais pesado"),
                G("pmode", "Movimento", [("Fluxo", 0), ("Explosão", 1), ("Órbita", 2)], "Nuvem que vem para você, jorro a cada batida ou anel que gira"),
                S("psize", "Tamanho", 10, 100, 5, "Tamanho de cada ponto")]
    if t == "grad":
        return [S("amt", "Intensidade", 0, 100, 5, "Quão forte o fundo brilha"), G("gtype", "Tipo", [("Sólido", 0), ("Linear", 1), ("Radial", 2)], "Uma cor, gradiente em linha ou do centro para fora"),
                G("gcol", "Cores", [("Da paleta", 0), ("Fixas", 1)], "Os fundos da paleta, ou três cores que você escolhe"),
                dict(id="lp_gdir", kind="seg", label="Direção", opts=[("Vertical", 0), ("Horizontal", 1), ("Diagonal", 2), ("Girando", 3)], help="Para onde o gradiente corre",
                     enabled=lambda c: bool(c["lp_on"]) and c["lp_gtype"] == 1)]
    if t == "lights":
        return [S("amt", "Intensidade", 10, 300, 10, "Com as cores da paleta da cena"),
                dict(id="lp_style", kind="seg", label="Estilo", opts=[("Aurora", 1), ("Feixes", 2), ("Pulsos", 3), ("Estrelas", 4), ("Faixas", 5), ("Lasers", 6), ("Feixe", 7)],
                     help=lambda c: ["", "Ondas de luz", "Raios que giram", "Anéis no ritmo", "Pontos que cintilam", "Listras que sobem", "Leques de laser que abrem com os graves", "Um feixe de laser com um ponto quente no meio"][c["lp_style"] % 8], enabled=on),
                G("lcol", "Cor", [("Paleta", 0), ("Branco", 1), ("Vermelho", 2), ("Azul", 3)], "A paleta da cena, ou uma cor só"), S("speed", "Velocidade", 20, 300, 10, "Quão rápido as luzes se movem")]
    return []


def grad_rows(cfg, on):
    """The extra rows of a gradient: its colours, the pulse and the way the colours change."""
    layers = cfg.get("layers") or []
    sel = int(cfg.get("ly_sel", 0))
    out = []
    if not (0 <= sel < len(layers)):
        return out
    L = layers[sel]
    if int(L.get("gcol", 0)) == 1:
        out.append(dict(id="lp_gitem", kind="swatches", label="Cor", help="A, B e C: do começo ao fim do gradiente", items=[list(c) for c in L.get("cols", DEFAULT_COLS)]))
        for key, lab in (("gr_", "Vermelho"), ("gg_", "Verde"), ("gb_", "Azul")):
            out.append(dict(id=f"lp_{key}", kind="slider", label=lab, lo=0, hi=255, step=5, unit="", help="Da cor selecionada", enabled=on))
    out.append(dict(id="lp_greact", kind="slider", label="Pulsa com a batida", lo=0, hi=100, step=5, unit="%", help="O fundo clareia a cada batida", enabled=on))
    out.append(dict(id="lp_gtrans", kind="seg", label="Transição", opts=[("Seco", 0), ("Rápida", 1), ("Suave", 2), ("Lenta", 3), ("No tempo", 4)],
                    help=lambda c: ["De uma vez", "Em 0,25 s", "Em 0,8 s", "Em 1,8 s", "Dura duas batidas"][c["lp_gtrans"] % 5], enabled=on))
    out.append(dict(id="lp_gevery", kind="seg", label="Troca de cores", opts=[("Nunca", 0), ("Na frase", 1), ("Compasso", 2), ("4 compassos", 3), ("Pela música", 4)],
                    help=lambda c: ["O fundo fica como está", "A cada frase", "A cada compasso", "A cada 4 compassos", "Nos drops, quebras e mudanças de parte"][c["lp_gevery"] % 5], enabled=on))
    return out


def follow_rows(cfg, on):
    src = int(cfg.get("lp_src", 0))
    rows_ = [dict(id="lp_src", kind="dd", label="Segue", opts=SOURCES, help="Graves, médios, agudos…", enabled=on)]
    if src > 0:
        rows_ += [
            dict(id="lp_famt", kind="slider", label="Quanto segue", lo=0, hi=100, step=5, unit="%",
                 help=lambda c: "Fica no valor fixo" if c["lp_famt"] == 0 else ("Só aparece com o som" if c["lp_famt"] >= 95 else f"{c['lp_famt']}% vem da música"), enabled=on),
            dict(id="lp_atk", kind="slider", label="Ataque", lo=0, hi=100, step=5, unit="%", help="0 sobe na hora  ·  mais alto: sobe devagar", enabled=on),
            dict(id="lp_rel", kind="slider", label="Soltura", lo=0, hi=100, step=5, unit="%", help="0 corta seco  ·  mais alto: volta devagar, como uma cauda", enabled=on),
            dict(id="lp_gain", kind="slider", label="Sensibilidade", lo=25, hi=300, step=25, unit="%", help="Amplifica o sinal  ·  100% é o natural", enabled=on),
            dict(id="lp_thr", kind="slider", label="Limiar", lo=0, hi=90, step=5, unit="%", help="Ignora o que fica abaixo deste nível", enabled=on),
            dict(id="lp_curve", kind="seg", label="Curva", opts=[("Linear", 0), ("Só picos", 1), ("Sensível", 2)],
                 help=lambda c: ["Proporcional ao sinal", "Só os picos fortes aparecem", "Reage até ao som baixo"][c["lp_curve"] % 3], enabled=on),
            dict(id="lp_inv", kind="toggle", label="Inverter", help="Forte no silêncio, some com o som", enabled=on),
        ]
    return rows_


def has_bg(sc):
    """True when the scene has a background layer on (a gradient or lights): a scene with nothing drawn is not black then."""
    return any(l.get("t") in ("grad", "lights") and l.get("on", True) for l in (sc.get("layers") or []))


def lights_style(sc):
    """The style (1..5) of the first lights layer on, or 0."""
    for l in sc.get("layers") or []:
        if l.get("t") == "lights" and l.get("on", True):
            return int(l.get("style", 1))
    return 0
