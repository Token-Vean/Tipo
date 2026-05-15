# Resuelve el digest de python:3.12-slim con Docker y actualiza .env local.
# Requiere Docker Desktop arrancado.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root
$image = "python:3.12-slim"
Write-Host "Resolviendo digest de $image ..."
$inspect = docker buildx imagetools inspect $image --format '{{json .Manifest.Digest}}'
$digest = ($inspect | ConvertFrom-Json)
if (-not $digest -or -not $digest.StartsWith("sha256:")) { throw "No se pudo resolver el digest de $image" }
$line = "PYTHON_IMAGE=$image@$digest"
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
$content = Get-Content ".env" -Raw
if ($content -match '(?m)^PYTHON_IMAGE=') {
  $content = $content -replace '(?m)^PYTHON_IMAGE=.*$', $line
} else {
  $content += "`n$line`n"
}
Set-Content -Encoding UTF8 ".env" $content
Write-Host "Actualizado .env: $line"
