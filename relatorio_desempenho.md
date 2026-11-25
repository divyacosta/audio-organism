# Relatório de desempenho — qualidade Ultra

Gerado em 2026-11-25 07:41:51  ·  20.0 s medidos depois do aquecimento  ·  2776 quadros  ·  **sem limite de FPS**, para mostrar do que o programa é capaz

## O que roda

- **Placa de vídeo:** NVIDIA GeForce RTX 5060 Ti (D3D12)
- **Imagem:** 1280×720 (resolução interna 100.0%, 110 passos por raio)
- **Sistema:** Windows-11-10.0.26200-SP0  ·  Python 3.14.7

## Quanto custa cada parte de um quadro, e cada subparte

Um quadro leva em média **7.21 ms** (138.7 fps). Cada subparte é um cronômetro dentro do programa; a soma delas fecha o quadro.

| Parte / subparte | ms por quadro | % do quadro | % da parte |
|---|---:|---:|---:|
| **Desenho da imagem** | **4.36** | **60%** | |
| &nbsp;&nbsp;&nbsp;obter a imagem da janela (aqui o programa espera a placa liberar o quadro) | 2.75 | 38.2% | 63% |
| &nbsp;&nbsp;&nbsp;fechar e enviar os comandos (submit) | 0.53 | 7.3% | 12% |
| &nbsp;&nbsp;&nbsp;entregar o quadro (swap e espera pela placa) | 0.22 | 3.0% | 5% |
| &nbsp;&nbsp;&nbsp;brilho (bloom) | 0.20 | 2.8% | 5% |
| &nbsp;&nbsp;&nbsp;composição, efeitos de tela, FXAA e cópia da prévia | 0.19 | 2.6% | 4% |
| &nbsp;&nbsp;&nbsp;enviar parâmetros (buffers) | 0.19 | 2.6% | 4% |
| &nbsp;&nbsp;&nbsp;passe da cena (raymarching ou gerador) | 0.07 | 0.9% | 2% |
| &nbsp;&nbsp;&nbsp;rastro (feedback) | 0.06 | 0.8% | 1% |
| &nbsp;&nbsp;&nbsp;leitura da prévia (volta da placa) | 0.05 | 0.7% | 1% |
| &nbsp;&nbsp;&nbsp;borrão de movimento (acúmulo) | 0.05 | 0.7% | 1% |
| &nbsp;&nbsp;&nbsp;pilha de efeitos (plano do quadro) | 0.03 | 0.4% | 1% |
| &nbsp;&nbsp;&nbsp;suavização temporal (TAA) | 0.02 | 0.3% | 0% |
| &nbsp;&nbsp;&nbsp;partículas | 0.00 | 0.0% | 0% |
| &nbsp;&nbsp;&nbsp;texto na tela (OSD) | 0.00 | 0.0% | 0% |
| **Painel de controles e miniaturas** | **1.50** | **21%** | |
| &nbsp;&nbsp;&nbsp;enviar a imagem do painel à janela (textura) | 0.48 | 6.7% | 32% |
| &nbsp;&nbsp;&nbsp;Palco, galeria, rolagem e avisos (resto do desenho) | 0.24 | 3.4% | 16% |
| &nbsp;&nbsp;&nbsp;apresentar a janela do painel | 0.24 | 3.3% | 16% |
| &nbsp;&nbsp;&nbsp;painel: desenhar linhas e cartões (menu.render) | 0.21 | 2.9% | 14% |
| &nbsp;&nbsp;&nbsp;conteúdo e rolagem (cópia para a janela) | 0.19 | 2.6% | 13% |
| &nbsp;&nbsp;&nbsp;faixa de cima (prévia e botões) | 0.14 | 1.9% | 9% |
| &nbsp;&nbsp;&nbsp;miniaturas das cenas (thumbs.feed) | 0.00 | 0.0% | 0% |
| **Análise do som** | **0.88** | **12%** | |
| &nbsp;&nbsp;&nbsp;análise (FFT, bandas, batida, estados da música) | 0.52 | 7.3% | 60% |
| &nbsp;&nbsp;&nbsp;entrada (captura ou sinal de teste) e troca de dispositivo | 0.35 | 4.9% | 40% |
| **Diretor e parâmetros** | **0.13** | **2%** | |
| &nbsp;&nbsp;&nbsp;diretor (escolha de cena, câmera, movimento, parâmetros) | 0.12 | 1.7% | 93% |
| &nbsp;&nbsp;&nbsp;look: tipo de shader, cores e sala | 0.01 | 0.1% | 4% |
| &nbsp;&nbsp;&nbsp;ligar o som aos parâmetros e ao flash | 0.00 | 0.1% | 3% |
| **Resto do laço** | **0.11** | **2%** | |
| &nbsp;&nbsp;&nbsp;prévia, estado e salvar configurações | 0.06 | 0.9% | 57% |
| &nbsp;&nbsp;&nbsp;eventos, atalhos, comandos remotos e painel web | 0.02 | 0.3% | 21% |
| &nbsp;&nbsp;&nbsp;fim do quadro | 0.02 | 0.3% | 18% |
| &nbsp;&nbsp;&nbsp;gestos de drop e checagens | 0.00 | 0.0% | 2% |
| &nbsp;&nbsp;&nbsp;limitador de FPS (espera para chegar à meta) | 0.00 | 0.0% | 1% |
| &nbsp;&nbsp;&nbsp;preparar o quadro | 0.00 | 0.0% | 1% |
| *Não coberto por nenhum cronômetro* | 0.23 | 3.3% | |

Com o limite de 60 fps do programa ligado: **51.9 fps** em média, 1% mais lento 33.0 fps, e 39.2% de um núcleo (o limitador dorme entre os quadros).

## Como os quadros saem

- **Média:** 138.7 fps
- **1% mais lento:** 35.8 fps (quadro de 27.96 ms)
- **Pior quadro:** 32.7 ms

## O que o programa consome

- **Processador:** 63.2% de um núcleo (soma de todas as threads do programa; 100% = um núcleo inteiro)
- **Memória:** 414 MB em uso, pico de 418 MB

## Por módulo e por função (com profiler)

Medição com o `cProfile` ligado: os tempos saem inflados (o profiler também custa), então use as proporções, não os valores. Média de 73.6 fps nesta execução.

### Tempo próprio por módulo

| Módulo | ms por quadro |
|---|---:|
| wgpu | 5.86 |
| Python (embutido) | 2.74 |
| control.py | 1.40 |
| menu.py | 0.86 |
| numpy | 0.79 |
| analysis.py | 0.41 |
| neon_director.py | 0.28 |
| renderer.py | 0.26 |
| widgets.py | 0.23 |
| Python (biblioteca padrão) | 0.23 |
| cffi | 0.11 |
| ear.py | 0.10 |
| ui.py | 0.08 |
| i18n.py | 0.04 |
| fxstack.py | 0.04 |
| glfw | 0.03 |
| rendercanvas | 0.03 |
| prof.py | 0.03 |
| app.py | 0.01 |
| look.py | 0.01 |

### As 25 funções mais caras (tempo próprio)

| Função | Onde | Módulo | Chamadas por quadro | ms por quadro |
|---|---|---|---:|---:|
| `proxy_func` | _helpers.py:352 | wgpu | 150.9 | 4.843 |
| `update` | control.py:1259 | control.py | 1.0 | 1.326 |
| `<function TFont.size at 0x000001EF32B20EB0>` |  | Python (embutido) | 446.53 | 0.485 |
| `<method 'blit' of 'pygame.surface.Surface' objects>` |  | Python (embutido) | 41.97 | 0.339 |
| `_rows_h` | menu.py:227 | menu.py | 120.47 | 0.280 |
| `<method 'get' of 'dict' objects>` |  | Python (embutido) | 1840.83 | 0.232 |
| `size` | widgets.py:89 | widgets.py | 446.53 | 0.221 |
| `<built-in method time.sleep>` |  | Python (embutido) | 0.13 | 0.217 |
| `<genexpr>` | menu.py:2334 | menu.py | 543.83 | 0.202 |
| `_new_struct_p` | _api.py:121 | wgpu | 75.33 | 0.197 |
| `chunk` | analysis.py:844 | analysis.py | 1.0 | 0.183 |
| `_stacked` | menu.py:255 | menu.py | 318.03 | 0.116 |
| `_var` | _methods.py:148 | numpy | 15.46 | 0.112 |
| `<built-in method builtins.sum>` |  | Python (embutido) | 108.43 | 0.111 |
| `_draw` | renderer.py:522 | renderer.py | 1.0 | 0.109 |
| `capture` | _helpers.py:270 | wgpu | 150.9 | 0.109 |
| `_mean` | _methods.py:115 | numpy | 44.06 | 0.106 |
| `_hop` | analysis.py:342 | analysis.py | 1.27 | 0.097 |
| `<built-in method builtins.isinstance>` |  | Python (embutido) | 799.12 | 0.094 |
| `<built-in method pygame.transform.smoothscale>` |  | Python (embutido) | 0.61 | 0.085 |
| `<built-in method builtins.max>` |  | Python (embutido) | 813.63 | 0.083 |
| `select` | selectors.py:310 | Python (biblioteca padrão) | 0.03 | 0.080 |
| `lstsq` | _linalg.py:2417 | numpy | 3.73 | 0.076 |
| `<method 'reduce' of 'numpy.ufunc' objects>` |  | Python (embutido) | 85.91 | 0.075 |
| `_ctl_left` | menu.py:2331 | menu.py | 104.19 | 0.074 |

## Como ler

- **Desenho da imagem:** os cronômetros dentro dele medem o processador montando e enviando os comandos. O tempo que o programa passa **esperando a placa de vídeo** aparece em *obter a imagem da janela* e em *entregar o quadro*: se essas duas dominam, a placa é o limite.
- Na visão por função, `proxy_func` do `wgpu` mostra o custo de chamar a API da placa a partir do Python (dezenas de chamadas por quadro).
- Se **Painel de controles** ou **Diretor** dominam, o limite é o Python e dá para otimizar sem trocar de motor.
- O tempo de cada passe dentro da placa (cena, bloom, TAA...) não é medido aqui; seria preciso consultar cronômetros da própria placa.
- A memória da placa de vídeo também não é medida.
