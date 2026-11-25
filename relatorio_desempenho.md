# Relatório de desempenho — qualidade Ultra

Gerado em 2026-11-25 07:22:56  ·  20.01 s medidos depois do aquecimento  ·  2263 quadros  ·  **sem limite de FPS**, para mostrar do que o programa é capaz

## O que roda

- **Placa de vídeo:** NVIDIA GeForce RTX 5060 Ti (D3D12)
- **Imagem:** 1280×720 (resolução interna 100.0%, 110 passos por raio)
- **Sistema:** Windows-11-10.0.26200-SP0  ·  Python 3.14.7

## Quanto custa cada parte de um quadro, e cada subparte

Um quadro leva em média **8.85 ms** (113.1 fps). Cada subparte é um cronômetro dentro do programa; a soma delas fecha o quadro.

| Parte / subparte | ms por quadro | % do quadro | % da parte |
|---|---:|---:|---:|
| **Desenho da imagem** | **5.56** | **63%** | |
| &nbsp;&nbsp;&nbsp;obter a imagem da janela (aqui o programa espera a placa liberar o quadro) | 3.91 | 44.2% | 70% |
| &nbsp;&nbsp;&nbsp;fechar e enviar os comandos (submit) | 0.55 | 6.3% | 10% |
| &nbsp;&nbsp;&nbsp;entregar o quadro (swap e espera pela placa) | 0.23 | 2.6% | 4% |
| &nbsp;&nbsp;&nbsp;enviar parâmetros (buffers) | 0.20 | 2.2% | 4% |
| &nbsp;&nbsp;&nbsp;brilho (bloom) | 0.20 | 2.2% | 4% |
| &nbsp;&nbsp;&nbsp;composição, efeitos de tela, FXAA e cópia da prévia | 0.19 | 2.1% | 3% |
| &nbsp;&nbsp;&nbsp;passe da cena (raymarching ou gerador) | 0.07 | 0.8% | 1% |
| &nbsp;&nbsp;&nbsp;rastro (feedback) | 0.06 | 0.6% | 1% |
| &nbsp;&nbsp;&nbsp;leitura da prévia (volta da placa) | 0.05 | 0.6% | 1% |
| &nbsp;&nbsp;&nbsp;borrão de movimento (acúmulo) | 0.05 | 0.6% | 1% |
| &nbsp;&nbsp;&nbsp;pilha de efeitos (plano do quadro) | 0.03 | 0.3% | 1% |
| &nbsp;&nbsp;&nbsp;suavização temporal (TAA) | 0.02 | 0.2% | 0% |
| &nbsp;&nbsp;&nbsp;partículas | 0.00 | 0.0% | 0% |
| &nbsp;&nbsp;&nbsp;texto na tela (OSD) | 0.00 | 0.0% | 0% |
| **Painel de controles e miniaturas** | **1.77** | **20%** | |
| &nbsp;&nbsp;&nbsp;enviar a imagem do painel à janela (textura) | 0.59 | 6.7% | 34% |
| &nbsp;&nbsp;&nbsp;apresentar a janela do painel | 0.29 | 3.3% | 17% |
| &nbsp;&nbsp;&nbsp;Palco, galeria, rolagem e avisos (resto do desenho) | 0.29 | 3.3% | 16% |
| &nbsp;&nbsp;&nbsp;conteúdo e rolagem (cópia para a janela) | 0.23 | 2.6% | 13% |
| &nbsp;&nbsp;&nbsp;painel: desenhar linhas e cartões (menu.render) | 0.20 | 2.3% | 11% |
| &nbsp;&nbsp;&nbsp;faixa de cima (prévia e botões) | 0.16 | 1.8% | 9% |
| &nbsp;&nbsp;&nbsp;miniaturas das cenas (thumbs.feed) | 0.00 | 0.0% | 0% |
| **Análise do som** | **1.00** | **11%** | |
| &nbsp;&nbsp;&nbsp;análise (FFT, bandas, batida, estados da música) | 0.58 | 6.6% | 58% |
| &nbsp;&nbsp;&nbsp;entrada (captura ou sinal de teste) e troca de dispositivo | 0.42 | 4.7% | 42% |
| **Diretor e parâmetros** | **0.13** | **1%** | |
| &nbsp;&nbsp;&nbsp;diretor (escolha de cena, câmera, movimento, parâmetros) | 0.12 | 1.4% | 93% |
| &nbsp;&nbsp;&nbsp;look: tipo de shader, cores e sala | 0.01 | 0.1% | 4% |
| &nbsp;&nbsp;&nbsp;ligar o som aos parâmetros e ao flash | 0.00 | 0.0% | 3% |
| **Resto do laço** | **0.12** | **1%** | |
| &nbsp;&nbsp;&nbsp;prévia, estado e salvar configurações | 0.07 | 0.7% | 56% |
| &nbsp;&nbsp;&nbsp;eventos, atalhos, comandos remotos e painel web | 0.03 | 0.3% | 22% |
| &nbsp;&nbsp;&nbsp;fim do quadro | 0.02 | 0.2% | 17% |
| &nbsp;&nbsp;&nbsp;gestos de drop e checagens | 0.00 | 0.0% | 2% |
| &nbsp;&nbsp;&nbsp;preparar o quadro | 0.00 | 0.0% | 2% |
| &nbsp;&nbsp;&nbsp;limitador de FPS (espera para chegar à meta) | 0.00 | 0.0% | 1% |
| *Não coberto por nenhum cronômetro* | 0.28 | 3.1% | |

Com o limite de 60 fps do programa ligado: **55.1 fps** em média, 1% mais lento 36.9 fps, e 41.6% de um núcleo (o limitador dorme entre os quadros).

## Como os quadros saem

- **Média:** 113.1 fps
- **1% mais lento:** 49.4 fps (quadro de 20.25 ms)
- **Pior quadro:** 36.5 ms

## O que o programa consome

- **Processador:** 57.9% de um núcleo (soma de todas as threads do programa; 100% = um núcleo inteiro)
- **Memória:** 413 MB em uso, pico de 417 MB

## Por módulo e por função (com profiler)

Medição com o `cProfile` ligado: os tempos saem inflados (o profiler também custa), então use as proporções, não os valores. Média de 72.7 fps nesta execução.

### Tempo próprio por módulo

| Módulo | ms por quadro |
|---|---:|
| wgpu | 6.31 |
| Python (embutido) | 2.55 |
| control.py | 1.48 |
| menu.py | 0.83 |
| numpy | 0.74 |
| analysis.py | 0.41 |
| neon_director.py | 0.27 |
| renderer.py | 0.25 |
| widgets.py | 0.22 |
| Python (biblioteca padrão) | 0.22 |
| cffi | 0.11 |
| ear.py | 0.10 |
| ui.py | 0.08 |
| fxstack.py | 0.04 |
| i18n.py | 0.03 |
| glfw | 0.03 |
| rendercanvas | 0.03 |
| prof.py | 0.02 |
| app.py | 0.01 |
| look.py | 0.01 |

### As 25 funções mais caras (tempo próprio)

| Função | Onde | Módulo | Chamadas por quadro | ms por quadro |
|---|---|---|---:|---:|
| `proxy_func` | _helpers.py:352 | wgpu | 150.9 | 5.334 |
| `update` | control.py:1259 | control.py | 1.0 | 1.407 |
| `<function TFont.size at 0x000001BFBDDC0EB0>` |  | Python (embutido) | 446.33 | 0.471 |
| `<method 'blit' of 'pygame.surface.Surface' objects>` |  | Python (embutido) | 43.35 | 0.339 |
| `_rows_h` | menu.py:227 | menu.py | 120.23 | 0.268 |
| `<method 'get' of 'dict' objects>` |  | Python (embutido) | 1838.68 | 0.218 |
| `size` | widgets.py:89 | widgets.py | 446.33 | 0.211 |
| `<genexpr>` | menu.py:2334 | menu.py | 543.13 | 0.193 |
| `_new_struct_p` | _api.py:121 | wgpu | 75.32 | 0.188 |
| `chunk` | analysis.py:844 | analysis.py | 1.0 | 0.181 |
| `<built-in method time.sleep>` |  | Python (embutido) | 0.14 | 0.153 |
| `_stacked` | menu.py:255 | menu.py | 317.57 | 0.111 |
| `_var` | _methods.py:148 | numpy | 15.48 | 0.107 |
| `capture` | _helpers.py:270 | wgpu | 150.9 | 0.104 |
| `<built-in method builtins.sum>` |  | Python (embutido) | 108.69 | 0.104 |
| `_draw` | renderer.py:522 | renderer.py | 1.0 | 0.103 |
| `_mean` | _methods.py:115 | numpy | 43.88 | 0.102 |
| `_hop` | analysis.py:342 | analysis.py | 1.29 | 0.095 |
| `<built-in method builtins.isinstance>` |  | Python (embutido) | 798.03 | 0.090 |
| `<built-in method pygame.transform.smoothscale>` |  | Python (embutido) | 0.61 | 0.085 |
| `<built-in method builtins.max>` |  | Python (embutido) | 815.67 | 0.081 |
| `base` | neon_director.py:216 | neon_director.py | 157.95 | 0.072 |
| `<built-in method pygame.draw.rect>` |  | Python (embutido) | 33.82 | 0.072 |
| `<method 'reduce' of 'numpy.ufunc' objects>` |  | Python (embutido) | 85.54 | 0.071 |
| `_ctl_left` | menu.py:2331 | menu.py | 104.13 | 0.070 |

## Como ler

- **Desenho da imagem:** os cronômetros dentro dele medem o processador montando e enviando os comandos. O tempo que o programa passa **esperando a placa de vídeo** aparece em *obter a imagem da janela* e em *entregar o quadro*: se essas duas dominam, a placa é o limite.
- Na visão por função, `proxy_func` do `wgpu` mostra o custo de chamar a API da placa a partir do Python (dezenas de chamadas por quadro).
- Se **Painel de controles** ou **Diretor** dominam, o limite é o Python e dá para otimizar sem trocar de motor.
- O tempo de cada passe dentro da placa (cena, bloom, TAA...) não é medido aqui; seria preciso consultar cronômetros da própria placa.
- A memória da placa de vídeo também não é medida.
