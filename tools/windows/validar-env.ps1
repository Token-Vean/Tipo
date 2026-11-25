# =============================================================================
# Tipo — validación del fichero .env antes de usarlo
# -----------------------------------------------------------------------------
# instalar.bat y el panel de control leen algunos valores de .env y los usan
# en órdenes de PowerShell, en la URL de comprobación o como imagen base del
# contenedor que procesa los documentos. Un .env copiado de otra persona o de
# un foro podía colar código (PUERTO con comillas) o una imagen base ajena
# (PYTHON_IMAGE). Este script comprueba esos valores y sale con código 1, con
# un mensaje claro, si alguno no es válido. Sin .env no hay nada que validar.
#
# Uso: powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\validar-env.ps1 [-Ruta .env]
# =============================================================================
param([string]$Ruta = ".env")

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Ruta)) { exit 0 }

$reglas = [ordered]@{
    "PUERTO"        = @{ Patron = '^[0-9]{2,5}$'; Ayuda = "un numero de puerto (por ejemplo 8769)" }
    "PYTHON_IMAGE"  = @{ Patron = '^python:3\.12-slim(@sha256:[0-9a-f]{64})?$'; Ayuda = "python:3.12-slim, con o sin @sha256:<digest>" }
    "MODELO_BASE"   = @{ Patron = '^[A-Za-z0-9._:/@+-]{1,160}$'; Ayuda = "un nombre de modelo de Ollama (por ejemplo gemma4:e4b)" }
    "MODELO_NOMBRE" = @{ Patron = '^[A-Za-z0-9._:/@+-]{1,160}$'; Ayuda = "un nombre de modelo de Ollama (por ejemplo gemma4:e4b)" }
    "PERFIL"        = @{ Patron = '^(bundled|external)$'; Ayuda = "bundled o external" }
}

$errores = @()
foreach ($linea in Get-Content -LiteralPath $Ruta) {
    $l = $linea.TrimStart([char]0xFEFF)
    if ($l -match '^\s*#' -or $l -notmatch '=') { continue }
    $clave, $valor = $l -split '=', 2
    $clave = $clave.Trim()
    if (-not $reglas.Contains($clave)) { continue }
    $valor = $valor.Trim()
    if ($valor -notmatch $reglas[$clave].Patron) {
        $errores += "  - $clave no es valido. Debe ser $($reglas[$clave].Ayuda)."
    } elseif ($clave -eq "PUERTO") {
        $n = [int]$valor
        if ($n -lt 1024 -or $n -gt 65535) { $errores += "  - PUERTO debe estar entre 1024 y 65535." }
        elseif ($n -eq 8082) { $errores += "  - PUERTO no puede ser 8082: es el puerto de PlumA. Use 8769, el de Tipo." }
    }
}

if ($errores.Count -gt 0) {
    Write-Host "ERROR: el fichero .env contiene valores no validos:"
    $errores | ForEach-Object { Write-Host $_ }
    Write-Host "Corrijalos (o borre .env para que se cree de nuevo desde .env.example) y vuelva a intentarlo."
    exit 1
}
exit 0
