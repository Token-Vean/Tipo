# =============================================================================
# Tipo - creación de paquete ZIP de release para Windows
# -----------------------------------------------------------------------------
# Ejecutar desde la raíz del repositorio:
#   powershell -ExecutionPolicy Bypass -File scripts\crear_release_windows.ps1 -Version 0.2.0-beta.7
#
# Resultado:
#   dist\Tipo-<version>-windows.zip
#   dist\Tipo-<version>-windows.zip.sha256.txt
#
# Estructura generada para usuario final:
#   Instalar Tipo.bat       <- único archivo visible que debe ejecutar el usuario
#   _tipo\                 <- payload técnico; el lanzador lo marca como oculto
#
# Seguridad (lista de permitidos, no de excluidos):
#   El payload se genera con `git archive` a partir del commit indicado
#   (HEAD por defecto). Solo entra lo que está versionado en Git. Ficheros
#   ignorados o sin rastrear del árbol de trabajo (.env.local, documentos de
#   prueba en ejemplos/, pruebas/, documentos_prueba/, data/batches/,
#   secrets/, credentials/, exports/...) NO pueden colarse en el ZIP.
#
#   Si hay cambios sin confirmar en ficheros versionados, el script se detiene,
#   para que la release coincida exactamente con un commit identificable.
#   Usa -PermitirArbolSucio solo para pruebas locales.
#
#   Para dejar fuera del paquete ficheros versionados que no deben distribuirse
#   (p. ej. .github/, scripts de mantenimiento), márcalos con `export-ignore`
#   en .gitattributes.
# =============================================================================

param(
    [string]$Version = "0.2.0-beta.7",
    [string]$Ref = "HEAD",
    [switch]$PermitirArbolSucio
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Dist = Join-Path $Root "dist"
$PackageName = "Tipo-$Version-windows"
$PackageDir = Join-Path $Dist $PackageName
$PayloadZip = Join-Path $Dist "$PackageName-payload.tmp.zip"
$ZipPath = Join-Path $Dist "$PackageName.zip"
$ShaPath = Join-Path $Dist "$PackageName.zip.sha256.txt"

# Función simple (sin bloque param) a propósito: así los argumentos que
# empiezan por guion (--porcelain, -o...) llegan intactos a git vía $args
# en lugar de interpretarse como parámetros de PowerShell.
function Invoke-Git {
    $salida = & git -C $Root @args
    if ($LASTEXITCODE -ne 0) {
        throw "git $($args -join ' ') falló (código $LASTEXITCODE)."
    }
    return $salida
}

Write-Host "Comprobando repositorio Git..."
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "No se encuentra git en el PATH. Es necesario para generar la release."
}
Invoke-Git rev-parse --is-inside-work-tree | Out-Null
$Commit = (Invoke-Git rev-parse --verify "$Ref^{commit}") | Select-Object -First 1

# Cambios sin confirmar en ficheros versionados (los no rastreados no importan:
# git archive no los incluye).
$Pendientes = Invoke-Git status --porcelain --untracked-files=no
if ($Pendientes -and -not $PermitirArbolSucio) {
    Write-Host "Cambios sin confirmar en ficheros versionados:" -ForegroundColor Yellow
    $Pendientes | ForEach-Object { Write-Host "  $_" }
    throw "Confirma (commit) o descarta los cambios antes de crear la release, o usa -PermitirArbolSucio para pruebas."
}
if ($Pendientes -and $PermitirArbolSucio) {
    Write-Host "AVISO: hay cambios sin confirmar; NO se incluyen en el paquete (se empaqueta $Commit)." -ForegroundColor Yellow
}

Write-Host "Preparando directorio de distribución..."
if (Test-Path $PackageDir) { Remove-Item $PackageDir -Recurse -Force }
if (Test-Path $PayloadZip) { Remove-Item $PayloadZip -Force }
if (-not (Test-Path $Dist)) { New-Item -ItemType Directory -Path $Dist | Out-Null }
New-Item -ItemType Directory -Path $PackageDir -Force | Out-Null

Write-Host "Exportando payload versionado ($Commit) a _tipo con git archive..."
Invoke-Git archive --format=zip --prefix=_tipo/ -o $PayloadZip $Commit | Out-Null
try {
    Expand-Archive -Path $PayloadZip -DestinationPath $PackageDir -Force
} finally {
    if (Test-Path $PayloadZip) { Remove-Item $PayloadZip -Force }
}

Write-Host "Creando lanzador único..."
@'
@echo off
setlocal
cd /d "%~dp0"
if exist "_tipo" attrib +h "_tipo" >nul 2>&1
if not exist "_tipo\tools\windows\Tipo-Control.bat" (
  echo No se encuentra el paquete interno de Tipo.
  echo Vuelve a descomprimir el ZIP completo y ejecuta de nuevo este archivo.
  pause
  exit /b 1
)
call "_tipo\tools\windows\Tipo-Control.bat"
'@ | Set-Content -Encoding ASCII (Join-Path $PackageDir "Instalar Tipo.bat")

Write-Host "Comprobando que no se ha empaquetado .env ni artefactos sensibles..."
# Segunda barrera: aunque git archive solo exporta lo versionado, si algo
# sensible llegó a commitearse por error, la release se aborta aquí.
$Forbidden = Get-ChildItem -Path $PackageDir -Force -Recurse -File | Where-Object {
    ($_.Name -like ".env*" -and $_.Name -ne ".env.example") -or
    $_.Name -match '\.(pem|key|crt|pfx|p12|sqlite|sqlite3|db|log|bak|tmp|gguf)$' -or
    $_.Name -eq "users.json" -or
    $_.FullName -match '[\\/](secrets|credentials|pruebas|documentos_prueba|test_documents|uploads_local|exports|salidas|data)[\\/]'
}
$EjemplosNoMd = Get-ChildItem -Path (Join-Path $PackageDir "_tipo\ejemplos") -Force -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -ne ".md" }
$Forbidden = @($Forbidden) + @($EjemplosNoMd) | Where-Object { $_ }
if ($Forbidden) {
    $Forbidden | ForEach-Object { Write-Host "ERROR: fichero prohibido en paquete: $($_.FullName)" -ForegroundColor Red }
    throw "El paquete contiene ficheros prohibidos. Abortando."
}

Write-Host "Comprobando ficheros mínimos..."
$Required = @(
    "Instalar Tipo.bat",
    "_tipo\docker-compose.yml",
    "_tipo\instalar.bat",
    "_tipo\detener.bat",
    "_tipo\desinstalar.bat",
    "_tipo\.env.example",
    "_tipo\backend\Dockerfile",
    "_tipo\backend\requirements.txt",
    "_tipo\frontend\static\index.html",
    "_tipo\tools\windows\Tipo-Control.bat",
    "_tipo\tools\windows\Tipo-Control.ps1",
    "_tipo\Tipo.ico"
)
foreach ($item in $Required) {
    if (-not (Test-Path (Join-Path $PackageDir $item))) {
        throw "Falta fichero obligatorio en release: $item (¿está versionado en Git?)"
    }
}

Write-Host "Creando ZIP..."
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal

$hash = Get-FileHash -Algorithm SHA256 $ZipPath
"$($hash.Hash)  $PackageName.zip" | Set-Content -Encoding ASCII $ShaPath

Write-Host "Release creada: $ZipPath"
Write-Host "Commit empaquetado: $Commit"
Write-Host "SHA256: $($hash.Hash)"
