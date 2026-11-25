#!/usr/bin/env bash
# Fija en docker-compose.yml el digest de una versión concreta de la imagen
# oficial ollama/ollama (perfil "bundled"). Uso de mantenimiento antes de una
# release; requiere Docker con buildx y conexión a Docker Hub.
#
#   scripts/actualizar_ollama.sh 0.40.17
#
# Comprueba además que la imagen descargada informa de esa misma versión.
# Rechaza las versiones anteriores a 0.35.0: path traversal en /api/pull
# (CVE-2026-103663, intervalo ampliado por CERT Polska el 17-11-2026).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

version="${1:-}"
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Uso: $0 <versión>   (p. ej. 0.40.17)" >&2
  exit 2
fi
IFS=. read -r mayor menor _parche <<<"$version"
if [[ "$mayor" == "0" && "$menor" -lt 35 ]]; then
  echo "Ollama $version está afectado por CVE-2026-103663 (todas las versiones anteriores a 0.35.0)." >&2
  exit 2
fi

imagen="ollama/ollama:$version"
echo "Resolviendo digest de $imagen ..."
digest="$(docker buildx imagetools inspect "$imagen" --format '{{json .Manifest.Digest}}' | tr -d '"')"
if [[ ! "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "No se pudo resolver el digest de $imagen" >&2
  exit 1
fi

echo "Comprobando la versión que informa la imagen ..."
informada="$(docker run --rm "ollama/ollama@$digest" --version 2>&1 || true)"
if ! grep -q "$version" <<<"$informada"; then
  echo "La imagen no informa de la versión $version:" >&2
  echo "$informada" >&2
  exit 1
fi

sed -i.bak -E "s#^(    image: )ollama/ollama[:@][^[:space:]]+#\1ollama/ollama:$version@$digest#" docker-compose.yml
rm -f docker-compose.yml.bak
if ! grep -q "ollama/ollama:$version@$digest" docker-compose.yml; then
  echo "No se encontró la línea image: ollama/ollama… en docker-compose.yml" >&2
  exit 1
fi
echo "docker-compose.yml actualizado: ollama/ollama@$digest ($version)"
echo "Recuerde anotar la versión en CHANGELOG.md."
