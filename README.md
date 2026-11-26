# Audio Organism

Visualizador 3D que reage à música que toca no computador, feito em wgpu (Vulkan / Direct3D 12) com shaders em WGSL.
Captura o áudio do sistema (WASAPI loopback), detecta BPM, build-ups e drops e transforma isso em imagem em tempo real.

## Baixar e usar (Windows 10/11)

1. Abra a página de [Releases](../../releases/latest) e baixe `MusicVisualizer.exe`.
2. Dê duplo clique. Toque uma música no computador.
3. O Windows pode avisar "o Windows protegeu o computador" (o programa não é assinado): clique em **Mais informações** e depois em **Executar assim mesmo**.

Precisa de uma placa de vídeo com Vulkan ou Direct3D 12 e driver atualizado. Em placas mais fracas, use a predefinição **Baixo** ou **Médio** em *Sistema > Imagem*.

Duas janelas abrem: a de imagem (só o efeito) e a de controles (monitor da música e ajustes).
Na janela de imagem: `F` tela cheia (ou duplo clique), `Esc` sai dela, `V` VSync, `S` strobe, `D` drop de teste, `1` a `9` tocam a cena, `A` liga ou desliga a troca automática, `T` bate o ritmo (tap tempo, veja abaixo).

### Se a abertura travar

Se o motor de vídeo (Vulkan ou Direct3D 12) travar ou falhar enquanto o programa carrega, ele troca de motor sozinho: depois de 2 minutos na janela de carregamento (ou na hora, se houver erro) o programa reabre com o outro motor e guarda o que deu certo em `%APPDATA%\AudioOrganism\boot.json`. Se os dois falharem, abre no automático com a qualidade **Baixo**. O veredito é esquecido a cada versão nova. Sua escolha em Sistema > Motor de vídeo não é apagada. Em notebooks com placa dedicada, a dedicada passa a ser preferida à integrada.

## Como usar

O painel tem **três abas**: **Palco** (tocar), **Estúdio** (criar) e **Sistema** (configurar o programa). A janela já abre larga o bastante para ver a imagem e as cenas sem rolar (todas, numa tela Full HD; a primeira fileira, num notebook de 1366×768) e pode ser redimensionada e maximizada: o painel se reorganiza.

**Primeiro minuto**: o cartão "Comece por aqui" tem três passos que se marcam sozinhos (som detectado, cena escolhida, tela cheia) e some quando os três estão feitos (ou em **Pular**). Um clique numa cena **entra na hora** (e desliga a troca automática, dizendo isso); esperar o compasso ou a frase é uma opção do modo Avançado (Sistema > Automático > "Ao clicar numa cena"). Em tela cheia a imagem mostra, por alguns segundos, `Esc sai · 1–9 trocam a cena · A liga a troca automática` e o nome da cena que você trouxe para a tela com um clique ou uma tecla (nunca por controle externo nem no modo palco; dá para desligar em Sistema > Tela e áudio > "Dicas na tela cheia"). As miniaturas do Palco mostram o número 1–9 de cada cena. Os avisos do Palco trazem o botão que resolve: **Sem som** leva a Sistema > Tela e áudio (a saída de som vem primeiro), **Travando** baixa a qualidade um nível (**Melhorar sozinho**); os dois só aparecem depois de alguns segundos de problema. Sem som, a imagem segue o silêncio: não há demonstração nem música de teste.

- **Palco**: a imagem ao vivo (**Editar esta cena** abre a cena que está no ar no Estúdio), **Tela cheia** e **Troca automática** em botões grandes (ao lado da troca, **Opções** abre a página Automático), e três controles que valem para todas as cenas: **Intensidade** (quanto reage ao som), **Velocidade** e **Cores** (uma paleta para todas, ou "Da cena"); embaixo as cenas (um clique toca; o último bloco, **+ Nova cena**, cria uma cena em 3 passos: **o que ver** com miniaturas ao vivo, **cores** e **nome**, sempre com a imagem da cena que você está montando; ao criar, ela já entra no ar). No modo Avançado o primeiro passo tem também **Em branco**, que abre o editor de camadas vazio. Em janela larga (a partir de ~1400 px) no modo Avançado, o Palco vira **duas colunas**: à esquerda o que você toca, à direita os **Detalhes** sempre abertos. Em **Detalhes** (fechado até você abrir, nas janelas estreitas ou no modo Simples): BPM, tom, energia, a linha do tempo da música com a previsão da próxima frase, a faixa inteira, o status, os atalhos da imagem e o card **O que estou ouvindo** (ritmo, espectro, acorde, volume, estéreo, seções).
- **Live** (Estúdio, ao lado de Salvar): ligado, o que você muda na cena aparece na tela grande na hora e "Descartar" vira "Voltar ao que era"; desligado (padrão, e sempre ao abrir o programa), você edita um rascunho e vê só a prévia pequena até salvar. Atalho: `L`.
- **Estúdio**: onde as cenas são feitas. Numa janela larga (a partir de ~900 px) ele tem **duas colunas**: à esquerda a lista de **cenas** (miniatura ao vivo; um clique edita e o menu ••• toca, duplica e apaga, com confirmação; *Nova cena*), a biblioteca (exportar, importar, cenas de fábrica); à direita, a parte da cena escolhida nas **abas** (o Modelo da mandala e as Cores se escolhem por miniaturas ao vivo) (Aparência, Cores, Câmera, Movimento, Música, Camadas no Avançado, Cena). O cabeçalho mostra só o nome da cena e **NO AR** quando é ela. A cena aberta é sempre a que você está editando; para trocar de cena com mudanças não salvas, o primeiro clique só avisa. Numa janela estreita o Estúdio vira a galeria de cartões (um clique edita; o menu ••• toca, duplica e apaga) e o editor, com as mesmas abas. Tocar uma cena é coisa do Palco; quais cenas o automático pode trazer e quando ele troca ficam em **Sistema > Automático**.
  Cada cena guarda tudo: **Mandala** (Nenhum ou Mandala, com presets, geometria, cores, shader, simetrias e formas) · **Câmera** · **Movimento** · **Música** (reação ao som por faixa, piscadas e brilho) · **Camadas** · **Propriedades** (nome, chance no sorteio, gênero).
- **Piscadas**: strobe do build-up, flash do drop, rajadas de 1/4 de tempo, duração e efeito (inverter a imagem ou clarão).
- **Transições**: forma, cor, camadas e troca de cena, cada uma de corte seco a suave.
- **Sistema**: um campo de **busca** no topo (`Ctrl+F`; digite o nome de qualquer configuração), categorias à esquerda e a página à direita (numa janela estreita, uma fileira de categorias): **Imagem** (a qualidade em quatro predefinições; em **Personalizado** aparecem a resolução, o brilho, a suavização e o resto; medir o desempenho; com a imagem no ar ao lado), **Tela e áudio**, **Automático** (troca automática, quando troca sozinha, uma pílula por cena e o que a música decide), **Perfis e controle** e **Aplicativo** (motor de vídeo, atualização, sair).
- **Cenas prontas e Nova cena**: os seis presets de mandala (Facetas, Estrela, Túnel, Catedral, Impacto, Palco) já vêm como cenas da galeria, cada um com as suas camadas, e a Nova cena abre direto no editor de camadas.
- **Editor de cena**: uma pilha única (Mandala, Câmera, Movimento, Música, as camadas e as propriedades); clicar em um item mostra os controles dele (ao lado, ou numa página própria em janela estreita). O que você mexe fica num **rascunho**: a imagem no ar só muda quando você clica em **Salvar** (ou volta com **Descartar**). O preview do editor mostra o rascunho e, em Mandala > Simetrias, marca o **setor real** e os **espelhos** da simetria que você tocou.
- **Visuais**: cada cena tem um visual, escolhido em *Visual da cena*: **Mandala**, **Túnel**, **Espectro** (barras sobre piso espelhado), **Fractal**, **Grade neon** (synthwave), **Fluido**, **Galáxia**, **Osciloscópio** e **Logo / texto** (seu texto ou uma imagem no meio, pulsando com a música; também vale um `logo.png` em `Documentos\AudioOrganism`). Cada um tem três ajustes próprios e usa a paleta, as camadas, o Automático e todas as opções de qualidade. Já vêm prontas as cenas Vórtice, Espectro, Fractal, Synthwave, Fluido, Galáxia, Laser e Logo.
- **Camadas** (seção do editor de cena): uma pilha de camadas, quantas quiser (até 8 efeitos e 4 fundos), como camadas de ajuste. Tipos: gradiente, luzes de fundo, partículas, rastro, aberração cromática, desfoque nas bordas, reflexo de lente, grão de filme e mapa de tons. Cada camada tem modo de mistura (normal, somar, tela, sobrepor), opacidade, ordem, parâmetros próprios e **segue a música** (fonte, quanto, ataque, soltura, sensibilidade, limiar, curva, inverter). Há modelos de pilha (Cinema, VHS, Câmera velha, Pulsa, Psicodélico). As cenas antigas são convertidas sozinhas. Em Gráficos > Suavização há o modo **TAA**.
- **Busca** (o campo no topo do Sistema) e **Perfis**: três perfis (salvam e carregam tudo), `Ctrl+Z` desfaz mudanças nas cenas/shaders/paletas, editor do que o modo Automático faz em cada parte da música, e controle externo.
- **Controle externo** (desligado por padrão, liga em Sistema > Perfis e controle): OSC na porta UDP 9000 (`/scene 1..9`, `/auto`, `/strobe`, `/drop`, `/fullscreen`, `/stage`, `/vsync`, `/tap`) e notas MIDI (60–68 = cenas 1–9; 69 Auto, 70 drop, 71 strobe, 72 tela cheia, 73 palco, 74 VSync, 75 tap tempo).
- **Atalhos**: `1` a `9` tocam a cena, `A` liga ou desliga a troca automática, `F` tela cheia, `S` strobe, `D` drop de teste, `T` tap tempo, `P` modo palco (tela cheia e painel minimizado; `P` ou `Esc` volta).
- **Tap tempo (BPM na mão)**: quando o BPM que o programa ouve está errado (ou pela metade, ou em dobro), bata o ritmo: em **Detalhes**, clique em **TAP** (ou no próprio número do BPM) no tempo da música, ou aperte `T` (nas duas janelas, ou uma nota MIDI / `/tap`). O primeiro toque só começa a série; do segundo em diante o BPM é a mediana dos últimos 8 intervalos (um toque atrasado não estraga), entre 40 e 240, e cada toque põe a grade da batida no toque. Uma pausa de mais de 2 s começa outra série. O BPM batido fica até você clicar em **AUTO** (o botão no lugar do TAP) ou até a próxima música (depois de um silêncio).
- **Compartilhar**: *Exportar* e *Importar* na biblioteca do Estúdio gravam e leem `Documentos\AudioOrganism\cenas.json` (com as paletas e shaders das cenas).

## Atualizações

Em **Sistema > Aplicativo**, o botão **Verificar atualização** consulta esta página de Releases. Se houver uma versão nova, aparece
**Atualizar para x.y.z**: o programa baixa o novo `.exe`, confere o arquivo, troca e reabre sozinho. Nada é baixado sem você clicar.
Dá para desligar a verificação automática ao abrir na mesma página.

## Rodar pelo código

```
pip install -r requirements.txt
python app.py            # ou: iniciar.bat
python app.py --backend vulkan     # ou d3d12
```

Os shaders ficam em `shaders/` e são recarregados enquanto o programa roda: edite um `.wgsl` e salve.
Uma pasta `shaders` ao lado do `.exe` tem prioridade sobre a que vem dentro dele.

Testes:

```
python tests/run.py [--exe dist\MusicVisualizer.exe]    # tudo: menus, cenas, diretor, renderização, telas (com --exe, também o programa de verdade)
python tests/lay.py [dist\MusicVisualizer.exe]          # 5 tarefas de quem nunca viu o programa, com cliques e teclas de verdade
```

Para ver o programa como numa primeira vez (cenas de fábrica e o cartão "Comece por aqui"), sem mexer nas suas configurações, dê dois cliques em `testar_primeira_vez.bat`: ele abre o `dist\MusicVisualizer.exe` com uma pasta de configurações nova, apagada a cada abertura.

O `tests/lay.py` abre o programa pela primeira vez (pasta de configurações nova) e faz: tela cheia e voltar, trocar o visual, mexer em intensidade, velocidade e cores, criar uma cena (visual, cores e nome) e ligar a troca automática tirando uma cena dela. Só clica no que está na tela naquele instante (nunca rola antes), conta as ações de cada tarefa e confere que ela aconteceu. Roda na janela de abertura de uma tela Full HD e nas de telas 1366×768 e 1280×720 (`--size=LARGURAxALTURA` roda só uma). É um roteiro: prova que cada tarefa tem caminho, à vista e curto, mas não diz se uma pessoa reconhece os nomes dos botões; para isso é preciso alguém de verdade fazendo as cinco tarefas sem ajuda.

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

**Sistema > Imagem (modo Personalizado)** ganhou três cartões: **Tela** (formato 16:9, 21:9, 4:3, 1:1 ou 9:16 com barras pretas, aproximar, espelhar, cantos escuros), **Conforto** (limitar flashes e movimento da câmera, para plateias e pessoas sensíveis). Vale para todas as cenas e fica de fora do "Restaurar a imagem" e dos perfis. A **Cor final** (brilho, contraste, cores vivas, tons médios, temperatura, anti-faixas) fica em cada cena, em Estúdio > Acabamento.

O cartão **Efeitos pesados** (também em Sistema > Imagem) liga e desliga vidro das faces, brilho, rastro, partículas e borrão de movimento, um a um ou todos pelo botão "Desligar todos".

O cartão **Estilo da imagem** troca o visual de todas as cenas: Normal, Chapado (poucas cores lisas), Linhas (só contornos) ou Pixelado (blocos de cor, tamanho ajustável).

**Revisão do Estúdio e do Sistema:** no modo simples, Câmera e Movimento viram uma aba só (Movimento), com uma frase para cada escolha. A lista de cenas tem filtro (Todas, Mandalas, Outras) e a biblioteca virou um menu. As cores da paleta só abrem para edição em "Editar cores". A barra do editor diz "Tudo salvo", "Só na prévia" ou "Mudando ao vivo", e o cabeçalho resume tipo, cores, câmera e ritmo. Duplicar e Apagar ficam só no ••• da cena. Sistema separou Áudio e Tela, e Sair fica sempre embaixo das páginas. Os cartões Estilo, Tela, Cor final e Conforto aparecem sem precisar de Personalizado.
