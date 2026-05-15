@echo off
REM =============================================================================
REM Tipo - instalador/iniciador para Windows
REM -----------------------------------------------------------------------------
REM Pensado para usuarios no expertos: comprueba requisitos, detecta Ollama,
REM prepara configuracion, fija automaticamente la imagen Python por digest,
REM construye imagen, repara permisos, inicia Tipo y abre el navegador.
REM =============================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM Usar IPv4 explícito evita fallos en Windows cuando localhost resuelve a ::1.
set "TIPO_LOCAL_HOST=127.0.0.1"

echo.
echo Tipo 0.2.0-beta.7 - instalacion local
echo ----------------------------------------
echo.

REM -----------------------------------------------------------------------------
REM 1. Docker
REM -----------------------------------------------------------------------------
echo [1/10] Comprobando Docker...

set "DOCKER=docker"
where docker >nul 2>&1
if errorlevel 1 (
    if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" (
        set "DOCKER=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
    ) else if exist "%ProgramFiles(x86)%\Docker\Docker\resources\bin\docker.exe" (
        set "DOCKER=%ProgramFiles(x86)%\Docker\Docker\resources\bin\docker.exe"
    ) else (
        echo.
        echo    ERROR: Docker Desktop no esta instalado o Windows no puede localizarlo.
        echo.
        echo    Tipo necesita Docker Desktop para funcionar.
        echo    Instala Docker Desktop, abrelo una vez y vuelve a ejecutar este archivo:
        echo      https://www.docker.com/products/docker-desktop/
        echo.
        pause
        exit /b 1
    )
)

"!DOCKER!" --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo    ERROR: Docker se ha localizado, pero no responde correctamente.
    echo    Cierra esta ventana, abre Docker Desktop y vuelve a ejecutar el instalador.
    echo.
    pause
    exit /b 1
)

"!DOCKER!" info >nul 2>&1
if errorlevel 1 (
    echo.
    echo    ERROR: Docker esta instalado, pero no esta arrancado.
    echo    Abre Docker Desktop, espera a que termine de iniciarse y vuelve a ejecutar este instalador.
    echo.
    pause
    exit /b 1
)

echo    OK - Docker instalado y arrancado

REM -----------------------------------------------------------------------------
REM 2. Docker Compose
REM -----------------------------------------------------------------------------
echo.
echo [2/10] Comprobando Docker Compose...

"!DOCKER!" compose version >nul 2>&1
if errorlevel 1 (
    echo.
    echo    ERROR: Docker Compose no esta disponible.
    echo    Actualiza Docker Desktop y vuelve a intentarlo.
    echo.
    pause
    exit /b 1
)

echo    OK - Docker Compose disponible

REM -----------------------------------------------------------------------------
REM 3. Deteccion de Ollama
REM -----------------------------------------------------------------------------
echo.
echo [3/10] Detectando Ollama...

set PERFIL=bundled
set APP_SERVICE=app

set "OLLAMA_EXE="
where ollama >nul 2>&1
if not errorlevel 1 set "OLLAMA_EXE=ollama"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    set PERFIL=external
    set APP_SERVICE=app-external
    echo    OK - Ollama instalado y arrancado ^(127.0.0.1:11434^).
    echo        Tipo usara tu instalacion local de Ollama.
) else if defined OLLAMA_EXE (
    echo    AVISO - Ollama parece instalado, pero no esta arrancado en 127.0.0.1:11434.
    echo            Tipo continuara usando Ollama dentro de Docker.
    echo            No tienes que hacer nada para completar la instalacion.
) else (
    echo    AVISO - No se ha detectado Ollama instalado/arrancado en el equipo.
    echo            Tipo continuara usando Ollama dentro de Docker.
    echo            No tienes que instalar Ollama manualmente para usar esta release.
)

REM -----------------------------------------------------------------------------
REM 4. Puerto configurado
REM -----------------------------------------------------------------------------
echo.
echo [4/10] Comprobando puerto de la aplicacion...

set PUERTO=8082
if exist .env (
    for /f "tokens=2 delims==" %%a in ('findstr /b "PUERTO=" .env 2^>nul') do set PUERTO=%%a
)

netstat -an | findstr ":!PUERTO! " | findstr "LISTENING" >nul
if errorlevel 1 (
    echo    OK - Puerto !PUERTO! disponible
) else (
    "!DOCKER!" ps --filter "name=tipo-app" --format "{{.Names}}" | findstr "tipo-app" >nul
    if not errorlevel 1 (
        echo    OK - Puerto !PUERTO! ocupado por Tipo ^(se reiniciara^).
    ) else (
        echo    AVISO - El puerto !PUERTO! esta en uso por otra aplicacion.
        echo            Tipo intentara arrancar igualmente. Si falla, revisa el panel de soporte.
    )
)

REM -----------------------------------------------------------------------------
REM 5. Configuracion (.env)
REM -----------------------------------------------------------------------------
echo.
echo [5/10] Preparando configuracion local...

if exist .env (
    echo    OK - Fichero .env ya existe
) else (
    if exist .env.example (
        copy .env.example .env >nul
        echo    OK - Fichero .env creado a partir de .env.example
    ) else (
        echo    ERROR: No se encuentra .env.example.
        pause
        exit /b 1
    )
)

findstr /b "PERFIL=" .env >nul 2>&1
if not errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content .env) -replace '^PERFIL=.*', 'PERFIL=!PERFIL!' | Set-Content .env"
) else (
    echo.>> .env
    echo # Perfil detectado automaticamente>> .env
    echo PERFIL=!PERFIL!>> .env
)

findstr /b /c:"MODELO_BASE=gemma3:4b" .env >nul 2>&1
if not errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content .env) -replace '^MODELO_BASE=gemma3:4b$', 'MODELO_BASE=gemma4:e4b' | Set-Content .env"
) else (
    findstr /b "MODELO_BASE=" .env >nul 2>&1
    if errorlevel 1 echo MODELO_BASE=gemma4:e4b>> .env
)
findstr /b /c:"MODELO_NOMBRE=tipo" .env >nul 2>&1
if not errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content .env) -replace '^MODELO_NOMBRE=tipo$', 'MODELO_NOMBRE=gemma4:e4b' | Set-Content .env"
) else (
    findstr /b "MODELO_NOMBRE=" .env >nul 2>&1
    if errorlevel 1 echo MODELO_NOMBRE=gemma4:e4b>> .env
)

findstr /b "TIPO_CREAR_MODELO_DERIVADO=" .env >nul 2>&1
if errorlevel 1 echo TIPO_CREAR_MODELO_DERIVADO=false>> .env

echo    OK - Perfil activo: !PERFIL!

REM -----------------------------------------------------------------------------
REM 6. Fijar imagen Python por digest de forma automatica
REM -----------------------------------------------------------------------------
echo.
echo [6/10] Fijando imagen base Python por digest...

echo        Descargando/metadatando python:3.12-slim. Puede tardar la primera vez.
"!DOCKER!" pull python:3.12-slim >nul 2>python-image.log
if errorlevel 1 (
    echo    AVISO - No se pudo resolver ahora el digest de python:3.12-slim.
    echo            Se usara la referencia ya configurada en .env.
    type python-image.log
) else (
    set "PYTHON_IMAGE_DIGEST="
    for /f "delims=" %%i in ('"!DOCKER!" image inspect python:3.12-slim --format "{{index .RepoDigests 0}}" 2^>nul') do set "PYTHON_IMAGE_DIGEST=%%i"
    if defined PYTHON_IMAGE_DIGEST (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$path='.env'; $value='PYTHON_IMAGE=!PYTHON_IMAGE_DIGEST!'; $lines=@(); if(Test-Path $path){$lines=Get-Content $path}; if($lines -match '^PYTHON_IMAGE='){ $lines = $lines -replace '^PYTHON_IMAGE=.*', $value } else { $lines += $value }; Set-Content -Encoding ASCII $path $lines"
        echo    OK - Imagen Python fijada: !PYTHON_IMAGE_DIGEST!
    ) else (
        echo    AVISO - Docker no devolvio RepoDigest. Se usara python:3.12-slim.
    )
)
del python-image.log >nul 2>&1

REM -----------------------------------------------------------------------------
REM 7. Construccion de imagen
REM -----------------------------------------------------------------------------
echo.
echo [7/10] Preparando imagen de Tipo...
echo        Este paso puede tardar la primera vez.

set COMPOSE_PROFILES=!PERFIL!

"!DOCKER!" compose build !APP_SERVICE! >nul 2>build.log
if errorlevel 1 (
    echo.
    echo    ERROR: Fallo al construir la imagen. Detalles:
    type build.log
    pause
    exit /b 1
)
del build.log >nul 2>&1
echo    OK - Imagen preparada

REM -----------------------------------------------------------------------------
REM 8. Reparacion preventiva de permisos del volumen local
REM -----------------------------------------------------------------------------
echo.
echo [8/10] Verificando permisos del almacen local de usuarios...

echo    Deteniendo posibles contenedores previos de Tipo...
"!DOCKER!" compose down --remove-orphans >nul 2>&1
"!DOCKER!" rm -f tipo-app tipo-ollama >nul 2>&1

"!DOCKER!" compose --profile tools run --rm fix-permissions >permisos.log 2>&1
if errorlevel 1 (
    echo.
    echo    ERROR: No se pudieron preparar los permisos del almacen local.
    echo.
    echo    Detalles tecnicos para soporte:
    type permisos.log
    echo.
    echo    Tipo no continuara porque podria no permitir crear el usuario inicial.
    echo    Abre Docker Desktop, comprueba que esta arrancado y vuelve a ejecutar este instalador.
    echo    Si el problema continua, usa la opcion Reparar permisos desde el panel.
    pause
    exit /b 1
) else (
    echo    OK - Almacen local preparado
)
del permisos.log >nul 2>&1

REM -----------------------------------------------------------------------------
REM 9. Arranque
REM -----------------------------------------------------------------------------
echo.
echo [9/10] Arrancando Tipo...

"!DOCKER!" compose down >nul 2>&1

"!DOCKER!" compose up -d
if errorlevel 1 (
    echo.
    echo    ERROR: No se pudieron arrancar los servicios.
    echo.
    echo    Causas habituales:
    echo      - Puerto !PUERTO! en uso por otra aplicacion.
    echo      - Docker Desktop sin recursos suficientes.
    echo      - Falta de espacio en disco.
    echo.
    pause
    exit /b 1
)

echo    OK - Servicios arrancados

REM -----------------------------------------------------------------------------
REM 10. Esperar API y abrir navegador
REM -----------------------------------------------------------------------------
echo.
echo [10/10] Esperando a que Tipo este listo...

set MAX_INTENTOS=60
set INTENTO=0

:wait_loop
set /a INTENTO+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://!TIPO_LOCAL_HOST!:!PUERTO!/api/estado' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto wait_ok

"!DOCKER!" ps --filter "name=tipo-app" --filter "status=exited" --format "{{.Names}}" | findstr "tipo-app" >nul 2>&1
if not errorlevel 1 goto app_exited

set /a RESTO=!INTENTO! %% 5
if !RESTO! EQU 0 echo    Esperando respuesta local... intento !INTENTO!/!MAX_INTENTOS!
if !INTENTO! GEQ !MAX_INTENTOS! goto wait_timeout
timeout /t 1 /nobreak >nul
goto wait_loop

:wait_ok
echo    OK - Tipo responde correctamente
goto abrir_navegador

:app_exited
echo.
echo    ERROR: Tipo se ha detenido durante el arranque.
echo.
echo    Ultimos mensajes del contenedor:
"!DOCKER!" logs --tail 120 tipo-app
echo.
echo    Sugerencia: revisa los mensajes anteriores. Si aparece un error de permisos,
echo    ejecuta de nuevo este instalador o usa Reparar permisos desde el panel.
pause
exit /b 1

:wait_timeout
echo.
echo    AVISO - Tipo no ha respondido en el tiempo esperado.
echo.
echo    Estado del contenedor:
"!DOCKER!" ps -a --filter "name=tipo-app" --format "table {{.Names}}	{{.Status}}	{{.Ports}}"
echo.
echo    Ultimos mensajes del contenedor:
"!DOCKER!" logs --tail 120 tipo-app
echo.
echo    Se abrira el navegador igualmente por si el arranque termina unos segundos despues.

:abrir_navegador
echo.
echo ----------------------------------------
echo Instalacion completada.
echo.
echo URL: http://!TIPO_LOCAL_HOST!:!PUERTO!
echo Perfil: !PERFIL!
echo.
echo En el primer arranque, Tipo pedira crear un usuario administrador local.
echo Recuerda la contrasena: no se sube a ningun servicio externo.
echo.

start "" "http://!TIPO_LOCAL_HOST!:!PUERTO!"

echo Puedes dejar esta ventana abierta mientras trabajas con Tipo.
echo Si apagas Tipo desde la interfaz web, podras cerrar esta ventana o usar el panel.
echo.
pause
