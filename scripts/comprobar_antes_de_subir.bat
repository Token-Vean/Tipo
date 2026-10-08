@echo off
REM ============================================================================
REM Comprobacion pre-subida a GitHub (Windows)
REM ============================================================================
REM Ejecutar ANTES de hacer git push, para verificar que no se cuela nada
REM de las pruebas locales (.env, documentos personales, caches, etc).
REM
REM Seguridad: los nombres de fichero nunca pasan por una tuberia ("|") dentro
REM de un bucle FOR. En una tuberia, cmd.exe vuelve a interpretar el texto ya
REM expandido en un proceso hijo, de modo que un nombre como "a&calc.md"
REM ejecutaria "calc". Aqui la extension se comprueba con operaciones de cadena.
REM ============================================================================
setlocal enabledelayedexpansion

cd /d "%~dp0\.."

set PROBLEMAS=0

echo ===========================================================================
echo   Comprobacion pre-subida a GitHub
echo ===========================================================================
echo.

if not exist ".git" (
    echo ERROR: no estas en la raiz de un repositorio git.
    exit /b 1
)

echo -- Ficheros que git ve como cambios pendientes --
git status --short
echo.

echo -- Comprobacion de .env --
REM Detecta .env y variantes (.env.local, .env.prod...) salvo .env.example.
REM La salida de git va directa a findstr: no hay variables FOR en la tuberia.
git ls-files 2>nul | findstr /R /C:"^\.env" /C:"/\.env" | findstr /V /R /C:"\.env\.example$" >nul 2>&1
if !errorlevel! equ 0 (
    echo PELIGRO: hay ficheros .env rastreados por git:
    git ls-files | findstr /R /C:"^\.env" /C:"/\.env" | findstr /V /R /C:"\.env\.example$"
    echo   Ejecuta: git rm --cached ^<fichero^>
    set /a PROBLEMAS+=1
) else (
    echo OK: ningun .env rastreado
)

echo.
echo -- Comprobacion de claves y certificados --
git ls-files 2>nul | findstr /R /I /C:"\.key$" /C:"\.pem$" /C:"\.p12$" /C:"\.pfx$" >nul 2>&1
if !errorlevel! equ 0 (
    echo PELIGRO: hay claves o certificados rastreados:
    git ls-files | findstr /R /I /C:"\.key$" /C:"\.pem$" /C:"\.p12$" /C:"\.pfx$"
    set /a PROBLEMAS+=1
) else (
    echo OK: sin claves ni certificados rastreados
)

echo.
echo -- Comprobacion de cache Python --
git ls-files 2>nul | findstr /R "__pycache__ \.pyc$" >nul 2>&1
if !errorlevel! equ 0 (
    echo AVISO: hay __pycache__ o .pyc rastreados:
    git ls-files | findstr /R "__pycache__ \.pyc$"
    set /a PROBLEMAS+=1
) else (
    echo OK: sin cache Python rastreada
)

echo.
echo -- Comprobacion de documentos de prueba --
set EJEMPLOS_EXTRA=0
for /f "delims=" %%f in ('git -c core.quotePath^=false ls-files -- ejemplos/ 2^>nul') do (
    set "NOMBRE=%%f"
    if /i not "!NOMBRE:~-3!"==".md" (
        echo AVISO: !NOMBRE! no es .md
        set /a PROBLEMAS+=1
        set EJEMPLOS_EXTRA=1
    )
)
if !EJEMPLOS_EXTRA! equ 0 (
    echo OK: ejemplos/ contiene solo documentacion
) else (
    echo   Si son documentos reales de pruebas, quitalos antes de subir:
    echo     git rm --cached ejemplos/^<fichero^>
)

echo.
echo ===========================================================================
if !PROBLEMAS! equ 0 (
    echo Listo para subir. No se han detectado problemas evidentes.
    echo.
    echo Recordatorio: revisa 'git status' y 'git diff --cached' antes de push.
) else (
    echo Se han detectado !PROBLEMAS! problema^(s^). Resuelvelos antes del push.
)
echo ===========================================================================
echo.
pause
exit /b !PROBLEMAS!
