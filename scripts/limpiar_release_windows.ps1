# Limpieza local previa a commit/release en Windows PowerShell.
# Ejecutar desde la raíz del proyecto Tipo.

$ErrorActionPreference = "Stop"

Write-Host "Limpiando caches Python..."
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -File -Filter "*.pyc" | Remove-Item -Force

if (Test-Path ".env") {
    Write-Host "Aviso: .env existe localmente. Es normal para ejecutar Tipo, pero no debe subirse a Git."
    git ls-files --error-unmatch .env *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "ERROR: .env está rastreado por Git. Ejecuta: git rm --cached .env" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Comprobando sintaxis Python..."
python -S -m py_compile backend/app/*.py tests/*.py

Write-Host "Limpieza y comprobación básica completadas."
