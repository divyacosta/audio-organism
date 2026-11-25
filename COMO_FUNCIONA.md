# Audio Organism: como funciona

## O que é
O Audio Organism é um visualizador de música para Windows. Ele escuta o som do computador e desenha imagens 3D que reagem à música: batida, graves, médios, agudos e a energia de cada trecho. Funciona com duas janelas:

- **Tela grande**: a imagem em si, feita para projetor, TV ou segundo monitor.
- **Painel de controle**: onde tudo é escolhido e ajustado.

A ideia central: abrir e já ter uma imagem bonita sem mexer em nada. Quem quiser ir além encontra todos os ajustes no painel, e o modo Avançado mostra ainda mais.

## Como a imagem nasce
1. **Escuta**: o som entra pelo dispositivo escolhido em Sistema > Áudio. O analisador separa as faixas de frequência, detecta batidas e o tempo da música, e classifica cada trecho como Calmo, Normal ou Intenso. Build-ups e drops ficam no Intenso.
2. **Direção**: a partir disso, o programa decide a câmera, o giro, os pulsos, os flashes e quando trocar de forma ou de cena.
3. **Desenho**: a placa de vídeo desenha a cena (pelo wgpu, em Vulkan ou D3D12). Os efeitos entram por cima: vidro, brilho das luzes, rastro, partículas e borrão de movimento.
4. **Passe final**: por último entram a cor final (brilho, contraste, saturação, gama, temperatura, vinheta), o estilo da imagem (normal, chapado, linhas ou pixels), o espelho, o zoom e as barras de formato. Quando tudo está no neutro, essa etapa é pulada e não custa nada.

## O painel: três abas

### Palco
É a tela do dia a dia. Mostra o que está no ar e o motivo da escolha, e tem os atalhos principais: tela cheia, Automático e flashes. Dá para trocar de cena com um clique.

### Estúdio
Aqui ficam as **cenas**. Uma cena é um "look" completo: forma, cores, câmera, ritmo e reação à música.

- **Galeria**: a lista de cenas com miniatura. Com mais de 8 cenas aparece um filtro (Todas, Mandalas, Outras). O menu ••• de cada cena tem Duplicar e Apagar. A **Biblioteca** é um único menu com exportar, importar e voltar às cenas de fábrica.
- **Editor**: abre ao clicar numa cena. No topo há um resumo em três linhas: o tipo, as cores, e câmera com ritmo. As abas são:
  - **Aparência**: o tipo de imagem e as formas. Nas mandalas há modelos prontos, como Facetas, com vidro, simetrias e camadas.
  - **Cores**: a paleta da cena. O editor de paletas só abre pelo botão "Editar cores".
  - **Câmera** e **Movimento**: no modo simples viram uma aba só, "Movimento", com uma frase explicando cada escolha. No Avançado ficam separadas.
  - **Música**: quanto a imagem reage, a qual faixa de som, e o gênero preferido (o Automático prefere esta cena quando reconhece esse estilo).
  - **Camadas**: aparece só no Avançado.
  - **Cena**: nome e situação. Uma linha informa se a cena entra no Automático; para mudar, vá em Sistema > Automático.
- **Salvar e prévia**: toda edição é um rascunho, e a barra mostra um de três estados:
  - **Tudo salvo**.
  - **Só na prévia**: você vê na prévia pequena, e a tela grande só muda ao salvar.
  - **Mudando ao vivo**: com "Mostrar na tela grande enquanto edita" ligado, cada mudança vai ao ar na hora.

  Salvar guarda a edição; Voltar desfaz.

### Sistema
Ajustes globais, que valem para todas as cenas. As páginas aparecem nesta ordem:

1. **Imagem**: perfis de qualidade e os cartões de imagem.
   - **Estilo da imagem**: normal, chapado, linhas ou pixels, com o tamanho do pixel.
   - **Tela**: formato com barras, espelho e zoom.
   - **Cor final**: brilho, contraste, saturação, gama, temperatura, vinheta e dither.
   - **Conforto**: reduz flashes e movimentos fortes, em níveis.
   - **Efeitos pesados**: liga e desliga vidro, brilho das luzes, rastro, partículas e borrão. O botão "Nenhum" desliga os cinco de uma vez, para PCs mais fracos.
   - **Personalizado**: no perfil Personalizado aparecem também resolução, nitidez, detalhes, serrilhado e fluidez (FPS).
2. **Áudio**: de onde vem o som e o atraso do áudio (menor acompanha mais junto; maior evita falhas).
3. **Tela**: tela cheia, qual monitor e as dicas na tela.
4. **Automático**: quais cenas entram, de quanto em quanto tempo trocam e como a música decide a troca, por frase, drop e energia.
5. **Perfis e controle**: perfis salvos e controle externo por OSC ou MIDI. Dá para controlar pela rede, até pelo celular, na porta 9000.
6. **Aplicativo**: motor de vídeo e atualizações.

O botão Sair fica embaixo da lista de páginas. Cada página tem um "Restaurar" que volta só aquela página ao padrão.

## Modo simples e Avançado
- **Simples** (padrão): menos abas, textos curtos e escolhas prontas.
- **Avançado**: separa Câmera e Movimento, mostra Camadas e os controles finos.

O painel se adapta à largura da janela:

- **Larga**: os cartões ficam em duas colunas.
- **Estreita**: uma coluna. Quando as opções de uma linha não cabem ao lado do nome, descem para a linha de baixo, então nenhum texto fica cortado.

## O Automático
Com o Automático ligado, o programa troca de cena sozinho, seguindo a música:

- Muda de cena nas frases e nos drops.
- Prefere as cenas cujo gênero combina com a música que está tocando.
- Usa só as cenas marcadas em Sistema > Automático.

Desligado, a cena só muda quando você escolhe.

## Onde ficam as coisas
- **Configurações e cenas**: são salvas automaticamente na pasta do programa. As cenas podem ser exportadas para um `cenas.json` e compartilhadas.
- **Tudo de Sistema** é global. As cenas guardam só o próprio visual.
- **O executável**: `dist\MusicVisualizer.exe`.

## Como cada versão é conferida
- **Testes automáticos** (`tests/run.py`): cobrem o menu, as cenas, o passe final, os estilos, o conforto, os efeitos pesados e a ordem das páginas.
- **Teste de layout** (`tests/lay.py`) e **tour pelo exe**: abrem o programa de verdade e percorrem as telas. Durante esse teste, o programa ignora o mouse e o teclado reais para não atrapalhar o resultado.
- **Varredura de textos**: renderiza todas as páginas nos dois modos e nas duas larguras para garantir que nada fique cortado.
