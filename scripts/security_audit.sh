#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p security-reports

python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
python -m pip install pytest ruff pip-audit cyclonedx-bom

PYTHONPATH="$ROOT/backend" pytest -q tests backend/tests
ruff check backend/app tests
pip-audit -r backend/requirements.txt -f json -o security-reports/pip-audit.json
cyclonedx-py requirements -i backend/requirements.txt -o security-reports/sbom-python.cdx.json

if command -v docker >/dev/null 2>&1; then
  docker build -t tipo-app:audit ./backend
  if command -v trivy >/dev/null 2>&1; then
    trivy image --format json --output security-reports/trivy-image.json tipo-app:audit || true
    trivy image --format cyclonedx --output security-reports/sbom-image.cdx.json tipo-app:audit || true
    trivy image --format spdx-json --output security-reports/sbom-image.spdx.json tipo-app:audit || true
  else
    echo "Trivy no está instalado; omitiendo escaneo Trivy."
  fi
  if command -v grype >/dev/null 2>&1; then
    grype tipo-app:audit -o json > security-reports/grype-image.json || true
  else
    echo "Grype no está instalado; omitiendo escaneo Grype."
  fi
else
  echo "Docker no está disponible; omitiendo escaneo de imagen."
fi

echo "Informes generados en security-reports/."
