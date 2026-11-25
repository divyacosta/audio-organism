# Relatório de desempenho — qualidade Ultra

Gerado em 2026-11-25 07:08:59  ·  20.01 s medidos depois do aquecimento  ·  1699 quadros  ·  **sem limite de FPS**, para mostrar do que o programa é capaz

## O que roda

- **Placa de vídeo:** NVIDIA GeForce RTX 5060 Ti (D3D12)
- **Imagem:** 1280×720 (resolução interna 100.0%, 110 passos por raio)
- **Sistema:** Windows-11-10.0.26200-SP0  ·  Python 3.14.7

## Quanto custa cada parte de um quadro

Um quadro leva em média **11.78 ms** (84.9 fps).

| Parte | ms por quadro | % do quadro |
|---|---:|---:|
| Desenho da imagem (chamada ao renderizador, inclui a espera pela placa) | 7.75 | 66% |
| Painel de controles (pygame) e prévias | 2.64 | 22% |
| Análise do som (FFT, batida) | 1.11 | 9% |
| Diretor (cena, câmera, parâmetros) | 0.12 | 1% |
| Resto (eventos, espera, limitador, cópia da prévia) | 0.16 | 1% |

Com o limite de 60 fps do programa ligado: **55.6 fps** em média, 1% mais lento 39.4 fps, e 40.5% de um núcleo (o limitador dorme entre os quadros).

## Como os quadros saem

- **Média:** 84.9 fps (meta do programa: 1000 fps)
- **1% mais lento:** 40.9 fps (quadro de 24.44 ms)
- **Pior quadro:** 26.6 ms

## O que o programa consome

- **Processador:** 48.3% de um núcleo (soma de todas as threads do programa; 100% = um núcleo inteiro)
- **Memória:** 413 MB em uso, pico de 417 MB

## Como ler

- A parte **Desenho da imagem** mede a chamada ao renderizador no processador; com o VSync desligado ela inclui esperar a placa terminar. Se ela domina, o limite é a placa de vídeo.
- Se **Painel de controles** ou **Diretor** dominam, o limite é o Python e dá para otimizar sem trocar de motor.
- A memória da placa de vídeo não é medida aqui.
