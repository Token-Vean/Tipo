# =============================================================================
# Tipo - comprobacion del Ollama del equipo (Windows)
# -----------------------------------------------------------------------------
# Lo usa instalar.bat. Tipo reutiliza el Ollama del equipo y sus modelos solo
# si es de una version segura: todas las anteriores a 0.35.0 estan afectadas
# por CVE-2026-103663 (path traversal en /api/pull). Si es antiguo o no
# informa de su version, se pide actualizarlo: no se cambia a Ollama en
# Docker, porque el Ollama antiguo seguiria funcionando y vulnerable.
#
# Codigos de salida:
#   0  arrancado, version valida: Tipo usa el Ollama del equipo
#   1  arrancado, pero antiguo o sin version: hay que actualizarlo (mensaje)
#   2  no instalado o no arrancado: Tipo usa Ollama en Docker
#   3  el programa de Ollama dice que esta arrancado, pero no responde en
#      127.0.0.1:11434 (mensaje): se detiene para no descargar el modelo otra
#      vez en Docker sin que el usuario lo sepa
# La version minima debe coincidir con VERSION_MINIMA_OLLAMA de
# backend/app/llm.py (tests/test_revision_2026_11_unidad.py lo comprueba).
# =============================================================================
$ErrorActionPreference = "Stop"
$VersionMinima = [version]'0.35.0'

. (Join-Path $PSScriptRoot "ollama-equipo.ps1")
$o = Get-OllamaEquipo

if ($o.Estado -eq "no_instalado" -or $o.Estado -eq "no_arrancado") {
    exit 2
}
if ($o.Estado -eq "no_responde") {
    Write-Host "   ERROR: Ollama $($o.Version) esta arrancado, pero no responde en 127.0.0.1:11434."
    Write-Host "          Detalle: $($o.Error)"
    if ($o.Host) {
        Write-Host "          La variable OLLAMA_HOST vale '$($o.Host)'. Tipo necesita"
        Write-Host "          Ollama en 127.0.0.1:11434: quita esa variable o ponle"
        Write-Host "          127.0.0.1:11434 (nunca 0.0.0.0), reinicia Ollama y vuelve"
        Write-Host "          a ejecutar este instalador."
    } else {
        Write-Host "          Puede bloquearlo un antivirus o un cortafuegos local."
        Write-Host "          Reinicia Ollama y vuelve a ejecutar este instalador."
    }
    exit 3
}
if ($null -eq $o.Version) {
    Write-Host "   ERROR: Ollama responde, pero no informa de su version."
    Write-Host "          Tipo necesita Ollama $VersionMinima o posterior."
    Write-Host "          Comprueba la version con:  ollama --version"
    Write-Host "          y, si es anterior, actualizalo desde https://ollama.com/download"
    Write-Host "          Despues reinicia Ollama y vuelve a ejecutar este instalador."
    exit 1
}
if ($o.Version -lt $VersionMinima) {
    Write-Host "   ERROR: el Ollama de este equipo es la version $($o.Version), afectada por un"
    Write-Host "          aviso de seguridad (CVE-2026-103663). Tipo necesita Ollama"
    Write-Host "          $VersionMinima o posterior."
    Write-Host "          Actualizalo desde https://ollama.com/download (tus modelos se"
    Write-Host "          conservan), reinicialo y vuelve a ejecutar este instalador."
    exit 1
}
Write-Host "   OK - Ollama del equipo: version $($o.Version)"
exit 0
