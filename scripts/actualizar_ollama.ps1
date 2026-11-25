# Fija en docker-compose.yml el digest de una versión concreta de la imagen
# oficial ollama/ollama (perfil "bundled"). Uso de mantenimiento antes de una
# release; requiere Docker Desktop arrancado y conexión a Docker Hub.
#
#   powershell -ExecutionPolicy Bypass -File scripts\actualizar_ollama.ps1 0.40.17
#
# Comprueba además que la imagen descargada informa de esa misma versión.
# Rechaza las versiones anteriores a 0.35.0: path traversal en /api/pull
# (CVE-2026-103663, intervalo ampliado por CERT Polska el 17-11-2026).
param([Parameter(Mandatory = $true)][string]$Version)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if ($Version -notmatch '^(\d+)\.(\d+)\.(\d+)$') { throw "Versión no válida: $Version (p. ej. 0.40.17)" }
$mayor = [int]$Matches[1]; $menor = [int]$Matches[2]; $parche = [int]$Matches[3]
if ($mayor -eq 0 -and $menor -lt 35) {
    throw "Ollama $Version está afectado por CVE-2026-103663 (todas las versiones anteriores a 0.35.0)."
}

$imagen = "ollama/ollama:$Version"
Write-Host "Resolviendo digest de $imagen ..."
$digest = (docker buildx imagetools inspect $imagen --format '{{json .Manifest.Digest}}' | ConvertFrom-Json)
if (-not $digest -or $digest -notmatch '^sha256:[0-9a-f]{64}$') { throw "No se pudo resolver el digest de $imagen" }

Write-Host "Comprobando la versión que informa la imagen ..."
$informada = (docker run --rm "ollama/ollama@$digest" --version 2>&1 | Out-String)
if ($informada -notmatch [regex]::Escape($Version)) { throw "La imagen no informa de la versión ${Version}: $informada" }

$compose = Get-Content "docker-compose.yml" -Raw
$nuevo = [regex]::Replace($compose, '(?m)^(    image: )ollama/ollama[:@]\S+', "`${1}ollama/ollama:$Version@$digest")
if ($nuevo -notmatch [regex]::Escape("ollama/ollama:$Version@$digest")) {
    throw "No se encontró la línea image: ollama/ollama… en docker-compose.yml"
}
[System.IO.File]::WriteAllText((Join-Path $Root "docker-compose.yml"), $nuevo, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "docker-compose.yml actualizado: ollama/ollama@$digest ($Version)"
Write-Host "Recuerde anotar la versión en CHANGELOG.md."
