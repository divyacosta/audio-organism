# Sistema de design — Audio Organism

Fonte única: `widgets.py`. Tudo que o painel desenha (`menu.py`, `control.py`, `deck.py`) usa estes tokens e estes componentes. Nenhuma tela escolhe cor ou tamanho por conta própria.

Base: o sistema do **ScreenMaster** (`App.xaml`), com os mesmos neutros, a mesma cor de tema e os mesmos estilos de botão, adaptados a desenho direto em `pygame`.

## Cores

Neutros frios e escuros, uma só cor de tema (lima), vermelho só para erro. Regra: uma cor, um significado.

| Token | Valor | Papel |
|---|---|---|
| `BG` | `#161617` | fundo da tela (atrás dos painéis) |
| `SURFACE` | `#1C1C1F` | painéis e cartões (Panel) |
| `SURFACE2` | `#232326` | controles em repouso, linhas (Raised) |
| `HOVER_FILL` | `#26262A` | sob o ponteiro (Hover) |
| `BORDER` | `#2A2A2D` | filetes entre coisas (Line) |
| `LINE_STRONG` | `#3A3A3F` | divisória mais forte |
| `CTRL` | `#7E7E84` | borda de controle, ≥ 3:1 sobre `SURFACE` e `SURFACE2` |
| `TEXT` | `#E6E6E8` | texto principal |
| `DIM` | `#9A9AA0` | texto secundário, ≥ 4,5:1 sobre `SURFACE` |
| `FAINT` | `#5A5A60` | desligado ou não se aplica |
| `SEL` / `ACCENT` | `#C6F24E` | o que está escolhido, ligado, selecionado, focado e "agora" (NO AR) |
| `ACCENT_DIM` | `#2E3324` | fundo da linha selecionada (lima a ~12%) |
| `DANGER` | `#F06A62` | erro real e o que apaga |
| `PRIMARY_FILL` | `#2E2E33` | botão principal (neutro) |
| `ON_SEL` | `#161617` | texto sobre a lima |

Tipo de cor, sem exceção: texto em cor do tema sobre fundo escuro só quando é ele o destaque; o texto normal é `TEXT` ou `DIM`.

## Tipografia

Segoe UI Variable (reserva: Segoe UI). Tamanhos em `SIZES`:
`cap 12 · small 13 · label 14 · body 15 · lead 18 · head 20 · title 22 · h1 26 · h2 34 · display 60`.
Títulos de cartão: `TITLE` (= `DIM`), em frase normal (como as legendas do ScreenMaster), tamanho `cap`.

## Espaço e forma

- Raio: 6 px em botões, linhas, cartões e miniaturas (como o ScreenMaster). Pílulas e interruptores são redondos.
- Altura mínima de qualquer coisa que se clica: `MIN_H` = 24 px.
- Hairline de 1 px (`BORDER`) para separar painéis; nunca linhas grossas.

## Componentes (`widgets.py`)

| Componente | Função | Visual |
|---|---|---|
| `button(kind="primary")` | ação principal | fundo neutro `PRIMARY_FILL`, rótulo claro |
| `button(kind="select")` | escolhido | lima com texto escuro |
| `button(kind="plain")` | ação comum | fundo `SURFACE2`, borda `CTRL` |
| `button(kind="quiet")` | ícone ou texto puro | sem fundo nem borda em repouso |
| `button(kind="tone")` | ação com cor, pede confirmação | cor do tema na borda; dois toques |
| `button(kind="danger")` | apagar, sair | vermelho `DANGER` |
| `pill` | selo (NO AR, RASCUNHO) | cápsula cheia |
| `chip` | etiqueta pequena | texto com fundo `SURFACE2` |

## Regras

1. Lima (`SEL`) é sempre "escolhido ou ligado"; nunca decoração.
2. Vermelho (`DANGER`) é só erro ou ação destrutiva.
3. O botão principal de uma tela é `primary`, e só um por vista.
4. Texto secundário é `DIM`, nunca cinza de cor própria.
5. Contraste: texto ≥ 4,5:1, bordas de controle ≥ 3:1. Os testes conferem.

## Verificação

`tests/run.py` confere os contrastes dos tokens sobre `BG`, `SURFACE` e `SURFACE2`.
