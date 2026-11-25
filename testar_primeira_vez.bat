@echo off
rem Abre o programa (dist\MusicVisualizer.exe) como se fosse a primeira vez: pasta de configuracoes nova, cenas de fabrica e o cartao "Comece por aqui".
rem As suas configuracoes de verdade nao sao tocadas: esta copia usa %TEMP%\ao_primeira_vez, que e apagada a cada abertura.
rem O --multi deixa abrir mesmo com o seu programa normal aberto.
set "VIS_APPDIR=%TEMP%\ao_primeira_vez"
if exist "%VIS_APPDIR%" rmdir /s /q "%VIS_APPDIR%"
start "" "%~dp0dist\MusicVisualizer.exe" --multi
