@echo off
REM =============================================================================
REM Tipo - abre el panel si VBScript esta desactivado en el equipo.
REM Puede verse un instante una ventana negra; es normal.
REM =============================================================================
if not exist "%~dp0..\programa\tools\windows\Tipo-Control.ps1" (
    echo No se encuentra el panel de Tipo. Descomprime el ZIP completo.
    pause
    exit /b 1
)
start "" "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0..\programa\tools\windows\Tipo-Control.ps1"
exit /b 0
