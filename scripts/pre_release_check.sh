#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if find . -name .env -print -quit | grep -q .; then
  echo "ERROR: no empaquetar ficheros .env"
  exit 1
fi

if find . \( -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.db' -o -name 'users.json' \) -print -quit | grep -q .; then
  echo "ERROR: no empaquetar bases locales ni users.json"
  exit 1
fi

if find . -type d -name __pycache__ -print -quit | grep -q .; then
  echo "ERROR: eliminar __pycache__ antes de la release"
  exit 1
fi

python -m compileall -q backend/app frontend/static
node --check frontend/static/app.js
PYTHONPATH=backend pytest -q tests backend/tests
find . -type d -name __pycache__ -prune -exec rm -rf {} +
find . -name "*.pyc" -delete

echo "Comprobaciones locales básicas superadas."
