#!/usr/bin/env bash
# =============================================================================
# Comprobación pre-subida a GitHub
# -----------------------------------------------------------------------------
# Ejecutar ANTES de hacer git push, para verificar que no se cuela nada
# de las pruebas locales (ficheros .env, documentos personales, caches,
# logs con datos sensibles).
#
# Seguridad: los nombres de fichero se tratan siempre como datos. Se leen
# separados por NUL (git -z / xargs -0 / read -d '') y nunca se interpolan
# dentro de una cadena que ejecute un shell (sh -c, eval). Un fichero
# llamado, por ejemplo, 'x$(comando).txt' no ejecuta nada.
# =============================================================================
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

ROJO='\033[0;31m'
VERDE='\033[0;32m'
AMARILLO='\033[1;33m'
SIN='\033[0m'

problemas=0

echo "═══════════════════════════════════════════════════════════════════════════"
echo "  Comprobación pre-subida a GitHub"
echo "═══════════════════════════════════════════════════════════════════════════"
echo ""

# 1. Comprobar si estamos en un repo git
if [ ! -d ".git" ]; then
    echo -e "${ROJO}ERROR${SIN}: no estás en la raíz de un repositorio git."
    exit 1
fi

# 2. Mostrar ficheros que git va a subir (nuevos o modificados)
echo "── Ficheros que git ve como cambios pendientes ──────────────────"
git status --short
echo ""

# 3. Comprobar que no hay ficheros .env (ni variantes) rastreados
#    Se aceptan solo las plantillas .env.example.
echo "── Comprobación de secretos ─────────────────────────────────────"
envs_rastreados=$(git ls-files | grep -E '(^|/)\.env(\.[^/]+)?$' | grep -vE '(^|/)\.env\.example$' || true)
if [ -n "$envs_rastreados" ]; then
    echo -e "${ROJO}PELIGRO${SIN}: hay ficheros .env rastreados por git:"
    printf '%s\n' "$envs_rastreados"
    echo "  Ejecuta: git rm --cached <fichero>"
    problemas=$((problemas+1))
else
    echo -e "${VERDE}OK${SIN}: ningún .env rastreado"
fi

# 4. Comprobar claves o certificados
claves=$(git ls-files | grep -iE '\.(key|pem|p12|pfx)$' || true)
if [ -n "$claves" ]; then
    echo -e "${ROJO}PELIGRO${SIN}: hay claves o certificados rastreados:"
    printf '%s\n' "$claves"
    problemas=$((problemas+1))
else
    echo -e "${VERDE}OK${SIN}: sin claves ni certificados rastreados"
fi

# 5. Comprobar __pycache__
caches=$(git ls-files | grep -E '__pycache__|\.pyc$' || true)
if [ -n "$caches" ]; then
    echo -e "${AMARILLO}AVISO${SIN}: hay __pycache__ o .pyc rastreados:"
    printf '%s\n' "$caches" | head -5
    echo "  Ejecuta: git rm --cached -r --ignore-unmatch '*__pycache__*' '*.pyc'"
    problemas=$((problemas+1))
else
    echo -e "${VERDE}OK${SIN}: sin caché Python rastreada"
fi

# 6. Documentos de prueba en /ejemplos
echo ""
echo "── Comprobación de documentos de prueba ─────────────────────────"
ejemplos_extra=$(git ls-files -- ejemplos/ 2>/dev/null | grep -vE '\.md$' || true)
if [ -n "$ejemplos_extra" ]; then
    echo -e "${AMARILLO}AVISO${SIN}: hay ficheros en ejemplos/ que NO son .md:"
    printf '%s\n' "$ejemplos_extra"
    echo ""
    echo "  Si son documentos de DOMINIO PÚBLICO que quieres incluir como"
    echo "  ejemplos, perfecto. Si son documentos reales de pruebas, MUY"
    echo "  IMPORTANTE: quítalos antes de subir:"
    echo "    git rm --cached ejemplos/<fichero>"
    problemas=$((problemas+1))
else
    echo -e "${VERDE}OK${SIN}: ejemplos/ contiene solo documentación"
fi

# 7. Buscar palabras clave sospechosas en ficheros nuevos/modificados
#    --diff-filter=d excluye los borrados (no existen en disco).
#    -z / -0 / -- : los nombres nunca se interpretan como opciones ni se trocean.
echo ""
echo "── Comprobación de contenido (cabezadas de secretos) ────────────"
patrones_secretos="password|secret|api_key|apikey|token|auth_key"
sospechosos=$(git diff --cached --name-only -z --diff-filter=d 2>/dev/null \
    | xargs -0 -r grep -liE -e "$patrones_secretos" -- 2>/dev/null \
    | grep -vE '\.(md|example|gitignore)$|test_security|csrf\.py|llm\.py' || true)
if [ -n "$sospechosos" ]; then
    echo -e "${AMARILLO}REVISAR${SIN}: ficheros que mencionan secretos:"
    printf '%s\n' "$sospechosos"
    echo "  Inspecciona manualmente si contienen valores reales o solo nombres de variables."
else
    echo -e "${VERDE}OK${SIN}: sin patrones obvios de secretos en ficheros con cambios"
fi

# 8. Tamaño de los ficheros que se van a subir
echo ""
echo "── Tamaño total del commit pendiente ────────────────────────────"
tam_total=$(git diff --cached --numstat 2>/dev/null | awk '{sum+=$1+$2} END {print sum+0}')
echo "  Líneas añadidas + eliminadas en staging: ${tam_total:-0}"

# Sin 'sh -c': el nombre llega a "$f" como dato y solo se usa entre comillas.
limite_bytes=$((1024 * 1024))
ficheros_grandes=""
while IFS= read -r -d '' f; do
    if [ -f "$f" ]; then
        tam=$(wc -c < "$f" | tr -d '[:space:]')
        if [ "${tam:-0}" -gt "$limite_bytes" ]; then
            ficheros_grandes+="${f}"$'\n'
        fi
    fi
done < <(git diff --cached --name-only -z --diff-filter=d 2>/dev/null || true)

if [ -n "$ficheros_grandes" ]; then
    echo -e "${AMARILLO}AVISO${SIN}: ficheros grandes (>1 MB):"
    printf '%s' "$ficheros_grandes" | head -5
fi

# 9. Resumen
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
if [ "$problemas" -eq 0 ]; then
    echo -e "${VERDE}Listo para subir.${SIN} No se han detectado problemas evidentes."
    echo ""
    echo "Recordatorio: este script no garantiza que no se cuele algo. Revisa"
    echo "siempre 'git status' y 'git diff --cached' antes de hacer push."
else
    echo -e "${ROJO}Se han detectado ${problemas} problema(s).${SIN}"
    echo "Resuélvelos antes de hacer git push."
fi
echo "═══════════════════════════════════════════════════════════════════════════"

exit "$problemas"
