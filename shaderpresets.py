"""Shader presets (the Shaders tab). A shader is one of the seven ways the material can be drawn (the kind) plus three numbers that tune it.
The numbers are percentages, 100 meaning how the shader always looked, so a preset with p1 = p2 = p3 = 100 changes nothing.

  kind  1 3D · 2 Neon · 3 Holograma · 4 Raio X · 5 Cromado · 6 Aquarela · 7 Duotom (a two-colour film over the picture)
  p1..p3  what they do depends on the kind, see PARAMS
  auto    the automatic mode may pick this preset (it picks a KIND by the part of the music, then one of that kind's presets)
  duo_mode, duo_dark, duo_light   Duotom only: colours from the palette (0) or two fixed colours (1)

A scene's shader is 0 (automatic) or the 1-based index of a preset in the list.
"""

KIND_NAMES = {1: "3D", 2: "Neon", 3: "Holograma", 4: "Raio X", 5: "Cromado", 6: "Aquarela", 7: "Duotom"}
# label and help of the three numbers for each kind; None = the number does nothing for that kind
PARAMS = {
    1: (("Brilho", "Quanto de luz as faces recebem"), ("Contraste da luz", "Diferença entre o lado claro e o escuro"),
        ("Opacidade das faces", "Abaixo de 100% as camadas de trás aparecem")),
    2: (("Brilho do contorno", "Força do tubo de neon na borda"), ("Espessura do contorno", "Largura do brilho em cada faceta"),
        ("Opacidade das faces", "As faces são vidro escuro: quanto de cor ficam")),
    3: (("Brilho", "Luz geral do holograma"), ("Densidade das linhas", "Linhas finas que cruzam cada faceta"),
        ("Opacidade das faces", "Quanto as camadas se enxergam por dentro")),
    4: (("Brilho do contorno", "Força das bordas e do contorno"), ("Volume", "Quanto o raio X mostra onde as camadas se acumulam"),
        ("Opacidade das faces", "O raio X é quase transparente")),
    5: (("Brilho do reflexo", "Intensidade do estúdio refletido"), ("Tingimento", "Quanto da cor da cena entra no metal"), None),
    6: (("Pigmento", "Quanta tinta o papel guarda"), ("Grão", "Granulado do papel"), ("Opacidade", "Quanto uma camada deixa ver a de baixo")),
    7: (("Contraste", "Separação entre a cor escura e a clara"), None, None),
}
# the kinds, in the order of the shader's own ids: engine style id = kind - 1 (the Duotom is a post effect)
ORDER = (1, 2, 3, 4, 5, 6, 7)


def make(kind, name=None, p1=100, p2=100, p3=100, auto=True):
    return dict(name=name or KIND_NAMES[kind], kind=kind, p1=p1, p2=p2, p3=p3, auto=auto, duo_mode=0, duo_dark=[10, 0, 40], duo_light=[255, 90, 210])


def factory():
    """One preset per kind: the shader as it always was."""
    return [make(k) for k in ORDER]


def valid(p):
    return (isinstance(p, dict) and isinstance(p.get("name"), str) and p.get("kind") in KIND_NAMES
            and all(isinstance(p.get(k), (int, float)) for k in ("p1", "p2", "p3")))


def labels(kind):
    pr = PARAMS.get(kind, PARAMS[1])
    return [x for x in pr]
