#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
image="python:3.12-slim"
echo "Resolviendo digest de $image ..."
digest="$(docker buildx imagetools inspect "$image" --format '{{json .Manifest.Digest}}' | tr -d '"')"
if [[ ! "$digest" =~ ^sha256: ]]; then
  echo "No se pudo resolver el digest de $image" >&2
  exit 1
fi
line="PYTHON_IMAGE=$image@$digest"
[[ -f .env ]] || cp .env.example .env
if grep -q '^PYTHON_IMAGE=' .env; then
  sed -i.bak "s#^PYTHON_IMAGE=.*#$line#" .env && rm -f .env.bak
else
  printf '\n%s\n' "$line" >> .env
fi
echo "Actualizado .env: $line"
