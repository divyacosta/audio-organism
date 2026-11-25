# Plano: monitor por camada

Pendência da verificação de paridade com o ScreenMaster (item 23: "Monitor por camada", AUSENTE).
Este documento é só o plano. Nenhuma linha de código foi escrita para isto.

## O que o ScreenMaster faz

- Cada camada tem uma lista de monitores (`Layer.Monitors`) e aplica-se a eles (`AppliesTo(device)`).
- Camadas únicas por tipo (`LayerDefs.Unique` e `PerMonitor`) pegam só os monitores livres (`FreeMonitors`).
- Algumas camadas são de um monitor só (`SingleMonitor`), como o ajuste de Monitor: ele lê os valores atuais do monitor por DDC/CI
  (`LoadMonitorValues`) e só então passa a valer.
- O limite de FPS do grão (`MaxFps`) usa o monitor mais rápido entre os que a camada atende.
- Fonte: `ScreenMaster/UI/LayerSetup.cs:14-39` e `Core/LayerDefs`.

## Como o painel está hoje

- Uma janela de imagem (`renderer.py`), que pode ser movida para um monitor (`move_to_monitor`, `monitor_pick` em Ajustes).
- Todas as camadas desenham na mesma janela, em um monitor.
- Não há campo de monitor em `layers.py`. A única escolha de monitor é a global, em Ajustes ("Monitor da imagem").

## Decisões que faltam

1. **Modelo.** Opção A: uma janela de saída por monitor, cada uma desenha só as camadas que a atendem. Opção B: uma janela
   grande que cobre todos os monitores, com uma faixa de camadas por monitor. A opção A se parece mais com o ScreenMaster,
   mas custa uma passagem de render por monitor. A opção B é mais simples, mas o brilho e a sincronia entre monitores ficam piores.
2. **Brilho por DDC/CI.** O ajuste de Monitor depende de DDC/CI. Não há isso no pygame nem no wgpu. Precisa de uma biblioteca
   de DDC/CI para Windows e de uma decisão sobre o que acontece quando o monitor não responde.
3. **Quem renderiza o quê.** Cada janela de saída precisa do mesmo áudio e da mesma análise, mas com as próprias camadas e o próprio
   efeito de tela. Isso pede separar o passe de cena (compartilhado) do passe por monitor.

## Passos sugeridos

1. Modelo de dados: `layers.py` ganha `monitors` (lista de nomes de dispositivo, vazia = todos). Migração do `settings.json`
   sem perder nada (vazio = o comportamento de hoje).
2. Painel: na camada, uma linha "Monitores" com os monitores detectados (`glfw.get_monitors()`), como o `LayerSetup.Prepare`.
3. Renderer: uma janela de saída por monitor escolhido. Cada uma desenha as camadas que a atendem. Teste de quadros com um
   monitor e com dois (simulados).
4. Desempenho: medir o custo de duas janelas com `relatorio_desempenho.py`. Meta: não cair abaixo do limite de 60 fps em Alto.
5. Brilho por DDC/CI: fora do primeiro corte. Entra depois, se o usuário quiser.

## Critérios de pronto

- Uma camada com monitor escolhido aparece só nele; uma camada sem monitor aparece em todos.
- Migração do `settings.json` antigo sem alterar o resultado visual.
- `tests/run.py` cobre a escolha, o filtro por monitor e a migração.
- Relatório de desempenho com dois monitores, sem regressão grande em relação ao atual.
- Verificação visual em máquina real com dois monitores (não é possível só com render headless).

## Riscos

- Duas janelas de saída podem derrubar o desempenho ou o modo de tela cheia.
- Sem máquina de teste com dois monitores, a verificação fica incompleta.
- DDC/CI depende do monitor e do cabo; nem todo monitor responde.
