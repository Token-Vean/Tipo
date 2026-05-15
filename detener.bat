@echo off
REM =============================================================================
REM Tipo - detener servicios
REM =============================================================================

setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "DOCKER=docker"
where docker >nul 2>&1
if errorlevel 1 (
    if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" (
        set "DOCKER=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
    ) else if exist "%ProgramFiles(x86)%\Docker\Docker\resources\bin\docker.exe" (
        set "DOCKER=%ProgramFiles(x86)%\Docker\Docker\resources\bin\docker.exe"
    )
)

REM Recuperar perfil del .env
set PERFIL=bundled,external
if exist .env (
    for /f "tokens=2 delims==" %%a in ('findstr /b "PERFIL=" .env 2^>nul') do set PERFIL=%%a
)

set COMPOSE_PROFILES=!PERFIL!

echo Deteniendo servicios...
"!DOCKER!" compose down

echo.
echo Servicios detenidos.
echo.
echo Los datos y el modelo se conservan. Para volver a arrancar, ejecuta:
echo   instalar.bat
echo.
echo Para eliminar TODO (contenedores, modelo descargado, configuracion):
echo   desinstalar.bat
echo.
pause
