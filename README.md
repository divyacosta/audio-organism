# Audio Organism

Visualizador 3D que reage à música que toca no computador, feito em wgpu (Vulkan / Direct3D 12) com shaders em WGSL.
Captura o áudio do sistema (WASAPI loopback), detecta BPM, build-ups e drops e transforma isso em imagem em tempo real.

## Baixar e usar (Windows 10/11)

1. Abra a página de [Releases](../../releases/latest) e baixe `MusicVisualizer.exe`.
2. Dê duplo clique. Toque uma música no computador.
3. O Windows pode avisar "o Windows protegeu o computador" (o programa não é assinado): clique em **Mais informações** e depois em **Executar assim mesmo**.

Precisa de uma placa de vídeo com Vulkan ou Direct3D 12 e driver atualizado. Em placas mais fracas, use a predefinição **Baixo** ou **Médio** na aba Gráficos.

Duas janelas abrem: a de imagem (só o efeito) e a de controles (monitor da música e ajustes).
Na janela de imagem: `F` tela cheia, `D` drop de teste, `M` marcar um momento.

## Como usar

- **Ao vivo**: BPM, tom, energia e a linha do tempo da música, com as seções (calmo, groove, energia alta, breakdown, drop, silêncio, build-up) e a previsão da próxima frase.
- **Cenas**: a galeria do que o visualizador pode mostrar, com miniaturas ao vivo. Um clique toca a cena (na próxima frase, no compasso ou na hora, como você escolher em *Trocar de cena*), duplo clique abre o editor.
  Cada cena guarda tudo: **visual** (nenhum ou mandala, com presets Facetas, Estrela, Túnel, Catedral, Impacto e Palco), **fundo e luzes** (aurora, feixes, pulsos), **cores** (paletas), **shader** (3D, Neon, Holograma, Raio X, Cromado, Aquarela, Duotom), **câmera**, **movimento**, **formas**, reatividade, flashes e brilho.
  O interruptor de cada cartão define se a cena entra na **troca automática**.
- **Gráficos** e **Ajustes**: desempenho, qualidade e sistema, que valem para o programa todo.

## Atualizações

Na aba **Ajustes**, o botão **Verificar atualização** consulta esta página de Releases. Se houver uma versão nova, aparece
**Atualizar para x.y.z**: o programa baixa o novo `.exe`, confere o arquivo, troca e reabre sozinho. Nada é baixado sem você clicar.
Dá para desligar a verificação automática ao abrir em Ajustes.

## Rodar pelo código

```
pip install -r requirements.txt
python app.py            # ou: iniciar.bat
python app.py --backend vulkan     # ou d3d12
```

Os shaders ficam em `shaders/` e são recarregados enquanto o programa roda: edite um `.wgsl` e salve.
Uma pasta `shaders` ao lado do `.exe` tem prioridade sobre a que vem dentro dele.

## Gerar o executável e publicar uma versão

```
python -m PyInstaller --noconfirm --onefile --windowed --name MusicVisualizer ^
  --collect-all wgpu --collect-all rendercanvas --collect-all glfw --add-data "shaders;shaders" app.py
```

1. Aumente `VERSION` em `version.py`.
2. Crie um Release com a tag `v<VERSION>` e anexe `dist/MusicVisualizer.exe`.
   Opcional: anexe também `MusicVisualizer.exe.sha256` (hash SHA-256 do exe), que o atualizador confere.

## Privacidade

O programa grava, no seu computador, os últimos minutos de áudio da sessão em `%APPDATA%\AudioOrganism\gravacoes`
e eventos de detecção em `%APPDATA%\AudioOrganism\eventos.log`. Nada é enviado para fora. A única conexão de rede é a
consulta de versão ao GitHub.
