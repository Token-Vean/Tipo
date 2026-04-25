@echo off
REM Limpieza local previa a commit/release en Windows.
cd /d "%~dp0\.."
powershell -ExecutionPolicy Bypass -File scripts\limpiar_release_windows.ps1
pause
