@echo off
rem Inicia o Audio Organism (wgpu: Vulkan ou Direct3D 12). Na primeira vez instala as bibliotecas que faltarem.
rem Opcoes:  iniciar.bat --backend vulkan   ou   iniciar.bat --backend d3d12
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=C:\Python314\python.exe"
if not exist "%PY%" set "PY=py -3"

%PY% -c "import numpy, pygame, pyaudiowpatch, wgpu, rendercanvas, glfw" 2>nul
if errorlevel 1 (
  echo Instalando as bibliotecas necessarias - so na primeira vez, precisa de internet...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Nao foi possivel instalar as bibliotecas. Veja a mensagem acima.
    pause
    exit /b 1
  )
)

%PY% app.py %*
if errorlevel 1 (
  echo.
  echo O programa fechou com erro. Veja a mensagem acima.
  pause
)
