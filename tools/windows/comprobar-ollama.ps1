# =============================================================================
# Tipo — comprobación de la versión del Ollama del equipo (Windows)
# -----------------------------------------------------------------------------
# Lo usa instalar.bat cuando hay un Ollama respondiendo en 127.0.0.1:11434.
# Tipo reutiliza ese Ollama y sus modelos solo si es de una versión segura:
# todas las anteriores a 0.35.0 están afectadas por CVE-2026-103663 (path
# traversal en /api/pull). Si es antiguo o no informa de su versión, se pide
# actualizarlo: no se cambia a Ollama en Docker, porque el Ollama antiguo
# seguiría funcionando y vulnerable en el equipo.
#
# Salida: 0 = versión válida; 1 = antigua o ilegible (con mensaje).
# La versión mínima debe coincidir con VERSION_MINIMA_OLLAMA de
# backend/app/llm.py (tests/test_revision_2026_11_unidad.py lo comprueba).
# =============================================================================
$ErrorActionPreference = "Stop"
$VersionMinima = [version]'0.35.0'

$version = $null
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/version' -UseBasicParsing -TimeoutSec 3
    $texto = ($r.Content | ConvertFrom-Json).version
    if ($texto -match '^\s*v?(\d+)\.(\d+)\.(\d+)') {
        $version = [version]("{0}.{1}.{2}" -f $Matches[1], $Matches[2], $Matches[3])
    }
} catch {}

if ($null -eq $version) {
    Write-Host "   ERROR: no se ha podido leer la version del Ollama de este equipo."
    Write-Host "          Tipo necesita Ollama $VersionMinima o posterior."
    Write-Host "          Comprueba la version con:  ollama --version"
    Write-Host "          y, si es anterior, actualizalo desde https://ollama.com/download"
    Write-Host "          Despues reinicia Ollama y vuelve a ejecutar este instalador."
    exit 1
}
if ($version -lt $VersionMinima) {
    Write-Host "   ERROR: el Ollama de este equipo es la version $version, afectada por un"
    Write-Host "          aviso de seguridad (CVE-2026-103663). Tipo necesita Ollama"
    Write-Host "          $VersionMinima o posterior."
    Write-Host "          Actualizalo desde https://ollama.com/download (tus modelos se"
    Write-Host "          conservan), reinicialo y vuelve a ejecutar este instalador."
    exit 1
}
Write-Host "   OK - Ollama del equipo: version $version"
exit 0
