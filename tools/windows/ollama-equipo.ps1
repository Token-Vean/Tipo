# =============================================================================
# Tipo - deteccion del Ollama del equipo (Windows)
# -----------------------------------------------------------------------------
# La usan el panel (Tipo-Control.ps1) y el instalador (comprobar-ollama.ps1):
# los dos tienen que llegar a la misma conclusion.
#
# Antes se comprobaba con Invoke-WebRequest contra
# http://localhost:11434 y 2-3 segundos de espera. Con Ollama arrancado podia
# fallar igualmente:
#   - Invoke-WebRequest usa el proxy del sistema y, con deteccion automatica
#     (WPAD) o un script PAC de empresa, la busqueda del proxy puede consumir
#     por si sola esos segundos;
#   - "localhost" puede resolverse primero a ::1 (IPv6) y Ollama solo escucha
#     en 127.0.0.1;
#   - el panel daba Ollama por "no arrancado" y el instalador, en silencio,
#     pasaba a Ollama en Docker y descargaba de nuevo el modelo (3-5 GB).
# Ahora: 127.0.0.1, sin proxy, 5 segundos, /api/version (respuesta minima) y,
# si falla, se pregunta al propio programa de Ollama (ollama --version) para
# distinguir "no arrancado" de "arrancado pero no responde en 127.0.0.1:11434".
# =============================================================================

$script:OllamaEquipoUrl = 'http://127.0.0.1:11434'

function Get-OllamaEquipoExe {
    try {
        $cmd = Get-Command "ollama.exe" -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) { return $cmd.Source }
    } catch {}
    $candidatos = @()
    if ($Env:LOCALAPPDATA) { $candidatos += (Join-Path $Env:LOCALAPPDATA "Programs\Ollama\ollama.exe") }
    if ($Env:ProgramFiles) { $candidatos += (Join-Path $Env:ProgramFiles "Ollama\ollama.exe") }
    foreach ($c in $candidatos) { if (Test-Path $c) { return $c } }
    return $null
}

function ConvertTo-OllamaVersion {
    param([string]$Texto)
    if ($Texto -match '(\d+)\.(\d+)\.(\d+)') {
        return [version]("{0}.{1}.{2}" -f $Matches[1], $Matches[2], $Matches[3])
    }
    return $null
}

# GET a un servicio de este equipo (Ollama o el propio Tipo) sin pasar por el
# proxy del sistema. Devuelve el cuerpo; lanza una excepcion si no responde o
# si responde con un error HTTP.
function Invoke-HttpLocalGet {
    param([string]$Url, [int]$TimeoutMs = 5000)
    $req = [System.Net.HttpWebRequest]::Create($Url)
    $req.Method = "GET"
    $req.Proxy = $null              # sin proxy del sistema ni WPAD
    $req.Timeout = $TimeoutMs
    $req.ReadWriteTimeout = $TimeoutMs
    $req.KeepAlive = $false
    $resp = $req.GetResponse()
    try {
        $lector = New-Object System.IO.StreamReader($resp.GetResponseStream())
        return $lector.ReadToEnd()
    } finally {
        $resp.Close()
    }
}

function Invoke-OllamaEquipoGet {
    param([string]$Ruta, [int]$TimeoutMs = 5000)
    return Invoke-HttpLocalGet -Url "$($script:OllamaEquipoUrl)$Ruta" -TimeoutMs $TimeoutMs
}

function Invoke-OllamaEquipoCli {
    param([string]$Exe, [int]$TimeoutSeconds = 8)
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $Exe
        $psi.Arguments = "--version"
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $p = [System.Diagnostics.Process]::Start($psi)
        $errTask = $p.StandardError.ReadToEndAsync()
        $outTask = $p.StandardOutput.ReadToEndAsync()
        if (-not $p.WaitForExit($TimeoutSeconds * 1000)) {
            try { $p.Kill() } catch {}
            return ""
        }
        return ($outTask.Result + "`n" + $errTask.Result)
    } catch {
        return ""
    }
}

function Get-OllamaHostConfigurado {
    foreach ($ambito in @("Process", "User", "Machine")) {
        $valor = [Environment]::GetEnvironmentVariable("OLLAMA_HOST", $ambito)
        if ($valor) { return $valor }
    }
    return $null
}

# Estado del Ollama del equipo:
#   Estado   "arrancado"     responde en 127.0.0.1:11434 (Version puede ser $null
#                            si no informa de ella)
#            "no_responde"   el programa dice que hay un servidor arrancado,
#                            pero no responde en 127.0.0.1:11434
#            "no_arrancado"  instalado, sin servidor
#            "no_instalado"
#   Version  [version] o $null
#   Error    motivo del fallo de la peticion HTTP, para diagnostico
function Get-OllamaEquipo {
    $r = [pscustomobject]@{
        Estado  = "no_instalado"
        Version = $null
        Error   = $null
        Exe     = (Get-OllamaEquipoExe)
        Host    = (Get-OllamaHostConfigurado)
    }
    try {
        $json = (Invoke-OllamaEquipoGet "/api/version") | ConvertFrom-Json
        $r.Estado = "arrancado"
        $r.Version = ConvertTo-OllamaVersion ([string]$json.version)
        return $r
    } catch {
        $r.Error = $_.Exception.GetBaseException().Message
    }
    if (-not $r.Exe) { return $r }
    $r.Estado = "no_arrancado"
    $salida = Invoke-OllamaEquipoCli $r.Exe
    $conectado = ($salida -notmatch 'could not connect') -and ($salida -match 'ollama version is\s+v?(\d+\.\d+\.\d+)')
    if ($conectado) {
        $r.Estado = "no_responde"
        $r.Version = ConvertTo-OllamaVersion $Matches[1]
    }
    return $r
}
