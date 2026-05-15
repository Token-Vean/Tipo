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
# =============================================================================

param(
    [string]$Version = "0.2.0-beta.7"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Dist = Join-Path $Root "dist"
$PackageName = "Tipo-$Version-windows"
$PackageDir = Join-Path $Dist $PackageName
$PayloadDir = Join-Path $PackageDir "_tipo"
$ZipPath = Join-Path $Dist "$PackageName.zip"
$ShaPath = Join-Path $Dist "$PackageName.zip.sha256.txt"

$ExcludeDirs = @(".git", ".venv", "venv", "env", "dist", "build", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "node_modules")
$ExcludeFiles = @(".env", "*.pyc", "*.pyo", "*.log", "build.log", ".DS_Store", "Thumbs.db", "*.sqlite", "*.sqlite3", "*.db", "*.pem", "*.key", "*.crt", "*.pfx", "*.p12", "users.json")

function Should-ExcludeFile([System.IO.FileInfo]$File) {
    foreach ($pattern in $ExcludeFiles) {
        if ($File.Name -like $pattern) { return $true }
    }
    return $false
}

Write-Host "Preparando directorio de distribución..."
if (Test-Path $PackageDir) { Remove-Item $PackageDir -Recurse -Force }
if (-not (Test-Path $Dist)) { New-Item -ItemType Directory -Path $Dist | Out-Null }
New-Item -ItemType Directory -Path $PayloadDir -Force | Out-Null

Write-Host "Copiando payload técnico limpio a _tipo..."
Get-ChildItem -Path $Root -Force | Where-Object { $_.Name -notin @("dist", ".git", ".venv", "venv", "build") } | ForEach-Object {
    if ($_.PSIsContainer) {
        robocopy $_.FullName (Join-Path $PayloadDir $_.Name) /E /XD .git .venv venv env dist build __pycache__ .pytest_cache .ruff_cache .mypy_cache node_modules /XF .env *.pyc *.pyo *.log build.log .DS_Store Thumbs.db *.sqlite *.sqlite3 *.db *.pem *.key *.crt *.pfx *.p12 users.json | Out-Null
        if ($LASTEXITCODE -gt 7) { throw "Robocopy falló copiando $($_.FullName)" }
    } else {
        if (-not (Should-ExcludeFile $_)) {
            Copy-Item $_.FullName -Destination $PayloadDir -Force
        }
    }
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
$Forbidden = Get-ChildItem -Path $PackageDir -Force -Recurse -File | Where-Object {
    $_.Name -eq ".env" -or $_.Name -match '\.(pem|key|pfx|p12|sqlite|sqlite3|db|log)$' -or $_.Name -eq "users.json"
}
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
        throw "Falta fichero obligatorio en release: $item"
    }
}

Write-Host "Creando ZIP..."
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal

$hash = Get-FileHash -Algorithm SHA256 $ZipPath
"$($hash.Hash)  $PackageName.zip" | Set-Content -Encoding ASCII $ShaPath

Write-Host "Release creada: $ZipPath"
Write-Host "SHA256: $($hash.Hash)"
