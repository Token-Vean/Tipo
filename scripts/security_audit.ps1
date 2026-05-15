# Tipo - auditoría local de seguridad y SBOM
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root
New-Item -ItemType Directory -Force -Path "security-reports" | Out-Null

python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
python -m pip install pytest ruff pip-audit cyclonedx-bom
$env:PYTHONPATH = Join-Path $Root "backend"
pytest -q tests backend\tests
ruff check backend\app tests
pip-audit -r backend\requirements.txt -f json -o security-reports\pip-audit.json
cyclonedx-py requirements -i backend\requirements.txt -o security-reports\sbom-python.cdx.json

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
  docker build -t tipo-app:audit .\backend
  $trivy = Get-Command trivy -ErrorAction SilentlyContinue
  if ($trivy) {
    trivy image --format json --output security-reports\trivy-image.json tipo-app:audit
    trivy image --format cyclonedx --output security-reports\sbom-image.cdx.json tipo-app:audit
    trivy image --format spdx-json --output security-reports\sbom-image.spdx.json tipo-app:audit
  } else {
    Write-Warning "Trivy no está instalado; omitiendo escaneo Trivy."
  }
  $grype = Get-Command grype -ErrorAction SilentlyContinue
  if ($grype) {
    grype tipo-app:audit -o json | Out-File -Encoding utf8 security-reports\grype-image.json
  } else {
    Write-Warning "Grype no está instalado; omitiendo escaneo Grype."
  }
} else {
  Write-Warning "Docker no está disponible; omitiendo escaneo de imagen."
}

Write-Host "Informes generados en security-reports/."
