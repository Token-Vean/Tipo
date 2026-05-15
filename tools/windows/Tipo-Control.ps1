# =============================================================================
# Tipo - panel grafico de instalacion/control para Windows
# =============================================================================
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..\..")
Set-Location $Root

function Get-Port {
    $port = "8082"
    $envFile = Join-Path $Root ".env"
    if (Test-Path $envFile) {
        $line = Get-Content $envFile -ErrorAction SilentlyContinue | Where-Object { $_ -match '^PUERTO=' } | Select-Object -First 1
        if ($line) { $port = ($line -replace '^PUERTO=', '').Trim() }
    }
    return $port
}

function Get-ProfileName {
    $profile = "bundled"
    $envFile = Join-Path $Root ".env"
    if (Test-Path $envFile) {
        $line = Get-Content $envFile -ErrorAction SilentlyContinue | Where-Object { $_ -match '^PERFIL=' } | Select-Object -First 1
        if ($line) { $profile = ($line -replace '^PERFIL=', '').Trim() }
    }
    if ($profile -notin @("bundled", "external")) { $profile = "bundled" }
    return $profile
}

function Get-AppServiceName {
    $profile = Get-ProfileName
    if ($profile -eq "external") { return "app-external" }
    return "app"
}

function Write-OutputBox {
    param([string]$Text)
    $timestamp = Get-Date -Format "HH:mm:ss"
    if ($null -ne $script:OutputBox) {
        $script:OutputBox.AppendText("[$timestamp] $Text`r`n")
        $script:OutputBox.SelectionStart = $script:OutputBox.TextLength
        $script:OutputBox.ScrollToCaret()
    }
}

function Get-CommandPathSafe {
    param([string]$Name, [string[]]$Fallbacks = @())
    try {
        $cmd = Get-Command $Name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) { return $cmd.Source }
    } catch {}
    foreach ($candidate in $Fallbacks) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

function Get-DockerExe {
    $fallbacks = @()
    if ($Env:ProgramFiles) { $fallbacks += (Join-Path $Env:ProgramFiles "Docker\Docker\resources\bin\docker.exe") }
    if (${Env:ProgramFiles(x86)}) { $fallbacks += (Join-Path ${Env:ProgramFiles(x86)} "Docker\Docker\resources\bin\docker.exe") }
    return Get-CommandPathSafe "docker.exe" $fallbacks
}

function Get-OllamaExe {
    $fallbacks = @()
    if ($Env:LOCALAPPDATA) { $fallbacks += (Join-Path $Env:LOCALAPPDATA "Programs\Ollama\ollama.exe") }
    if ($Env:ProgramFiles) { $fallbacks += (Join-Path $Env:ProgramFiles "Ollama\ollama.exe") }
    return Get-CommandPathSafe "ollama.exe" $fallbacks
}

function Invoke-ExecutableOk {
    param(
        [Parameter(Mandatory=$true)][string]$Exe,
        [Parameter(Mandatory=$true)][string[]]$Args,
        [int]$TimeoutSeconds = 8
    )
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $Exe
        # Compatible con Windows PowerShell 5.1: no usar ProcessStartInfo.ArgumentList.
        $psi.Arguments = ($Args | ForEach-Object { $_ }) -join " "
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        [void]$proc.Start()
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            try { $proc.Kill() } catch {}
            return $false
        }
        return ($proc.ExitCode -eq 0)
    } catch {
        return $false
    }
}

function Test-DockerCli {
    $docker = Get-DockerExe
    if (-not $docker) { return $false }
    return Invoke-ExecutableOk -Exe $docker -Args @("--version")
}

function Test-DockerRunning {
    $docker = Get-DockerExe
    if (-not $docker) { return $false }
    return Invoke-ExecutableOk -Exe $docker -Args @("info") -TimeoutSeconds 12
}

function Test-DockerCompose {
    $docker = Get-DockerExe
    if (-not $docker) { return $false }
    return Invoke-ExecutableOk -Exe $docker -Args @("compose", "version")
}

function Test-OllamaInstalled {
    return [bool](Get-OllamaExe)
}

function Test-OllamaNative {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -eq 200)
    } catch { return $false }
}

function Invoke-ConsoleScript {
    param(
        [Parameter(Mandatory=$true)][string]$ScriptName,
        [string]$Title = "Tipo"
    )
    $scriptPath = Join-Path $Root $ScriptName
    if (-not (Test-Path $scriptPath)) {
        [System.Windows.Forms.MessageBox]::Show("No se encuentra $ScriptName en la carpeta de Tipo.", "Tipo", "OK", "Error") | Out-Null
        return
    }
    Write-OutputBox "Abriendo consola para: $ScriptName"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"title $Title && `"$scriptPath`"`"" -WorkingDirectory $Root
}

function Invoke-Capture {
    param([Parameter(Mandatory=$true)][string]$Command)
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = "cmd.exe"
        $psi.Arguments = "/c $Command"
        $psi.WorkingDirectory = $Root
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.Environment["COMPOSE_PROFILES"] = Get-ProfileName
        $p = [System.Diagnostics.Process]::Start($psi)
        $stdout = $p.StandardOutput.ReadToEnd()
        $stderr = $p.StandardError.ReadToEnd()
        $p.WaitForExit()
        if ($stdout.Trim()) { Write-OutputBox $stdout.Trim() }
        if ($stderr.Trim()) { Write-OutputBox $stderr.Trim() }
        Write-OutputBox "Codigo de salida: $($p.ExitCode)"
    } catch {
        Write-OutputBox "ERROR: $($_.Exception.Message)"
    }
}

function Repair-DataPermissions {
    if (-not (Test-DockerCli) -or -not (Test-DockerRunning) -or -not (Test-DockerCompose)) {
        [System.Windows.Forms.MessageBox]::Show("Docker Desktop debe estar instalado y arrancado para reparar permisos.", "Tipo", "OK", "Warning") | Out-Null
        return
    }
    $profile = Get-ProfileName
    $service = Get-AppServiceName
    Write-OutputBox "Reparando permisos del volumen local de usuarios con perfil '$profile'..."
    Invoke-Capture "set COMPOSE_PROFILES=$profile && docker compose build $service && docker compose run --rm --no-deps --user root --entrypoint sh $service -c `"mkdir -p /app/data && chown -R 10001:10001 /app/data && chmod 700 /app/data`""
    Write-OutputBox "Reparacion de permisos finalizada. Si Tipo estaba abierto, reinicialo."
}


function Show-ResetAdminDialog {
    if (-not (Test-DockerCli) -or -not (Test-DockerRunning) -or -not (Test-DockerCompose)) {
        [System.Windows.Forms.MessageBox]::Show("Docker Desktop debe estar instalado y arrancado para restablecer el acceso.", "Tipo", "OK", "Warning") | Out-Null
        return
    }

    $dlg = New-Object System.Windows.Forms.Form
    $dlg.Text = "Tipo - recuperar acceso administrador"
    $dlg.Size = New-Object System.Drawing.Size(470, 275)
    $dlg.StartPosition = "CenterParent"
    $dlg.Font = New-Object System.Drawing.Font("Segoe UI", 9)

    $lbl = New-Object System.Windows.Forms.Label
    $lbl.Text = "Crea o restablece un usuario administrador local. Esta operación requiere acceso físico al equipo y Docker arrancado."
    $lbl.Location = New-Object System.Drawing.Point(18, 18)
    $lbl.Size = New-Object System.Drawing.Size(420, 42)
    $dlg.Controls.Add($lbl)

    $uLbl = New-Object System.Windows.Forms.Label
    $uLbl.Text = "Usuario administrador"
    $uLbl.Location = New-Object System.Drawing.Point(20, 75)
    $uLbl.Size = New-Object System.Drawing.Size(160, 22)
    $dlg.Controls.Add($uLbl)

    $uBox = New-Object System.Windows.Forms.TextBox
    $uBox.Text = "admin"
    $uBox.Location = New-Object System.Drawing.Point(190, 72)
    $uBox.Size = New-Object System.Drawing.Size(230, 24)
    $dlg.Controls.Add($uBox)

    $pLbl = New-Object System.Windows.Forms.Label
    $pLbl.Text = "Nueva contraseña"
    $pLbl.Location = New-Object System.Drawing.Point(20, 112)
    $pLbl.Size = New-Object System.Drawing.Size(160, 22)
    $dlg.Controls.Add($pLbl)

    $pBox = New-Object System.Windows.Forms.TextBox
    $pBox.UseSystemPasswordChar = $true
    $pBox.Location = New-Object System.Drawing.Point(190, 109)
    $pBox.Size = New-Object System.Drawing.Size(230, 24)
    $dlg.Controls.Add($pBox)

    $hint = New-Object System.Windows.Forms.Label
    $hint.Text = "Mínimo 10 caracteres y al menos tres tipos: minúsculas, mayúsculas, números o símbolos."
    $hint.Location = New-Object System.Drawing.Point(20, 145)
    $hint.Size = New-Object System.Drawing.Size(400, 34)
    $hint.ForeColor = [System.Drawing.Color]::DimGray
    $dlg.Controls.Add($hint)

    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = "Restablecer"
    $ok.Location = New-Object System.Drawing.Point(190, 190)
    $ok.Size = New-Object System.Drawing.Size(110, 32)
    $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $dlg.Controls.Add($ok)
    $dlg.AcceptButton = $ok

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = "Cancelar"
    $cancel.Location = New-Object System.Drawing.Point(310, 190)
    $cancel.Size = New-Object System.Drawing.Size(110, 32)
    $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $dlg.Controls.Add($cancel)
    $dlg.CancelButton = $cancel

    $result = $dlg.ShowDialog($form)
    if ($result -ne [System.Windows.Forms.DialogResult]::OK) { return }
    $username = $uBox.Text.Trim()
    $password = $pBox.Text
    if (-not $username -or -not $password) {
        [System.Windows.Forms.MessageBox]::Show("Debe indicar usuario y contraseña.", "Tipo", "OK", "Warning") | Out-Null
        return
    }

    $confirm = [System.Windows.Forms.MessageBox]::Show(
        "Se restablecerá el acceso administrador local. Las sesiones de ese usuario se invalidarán al reiniciar la aplicación. ¿Continuar?",
        "Tipo - recuperar acceso",
        "YesNo",
        "Warning"
    )
    if ($confirm -ne [System.Windows.Forms.DialogResult]::Yes) { return }

    $profile = Get-ProfileName
    $service = Get-AppServiceName
    $tmpEnv = Join-Path ([System.IO.Path]::GetTempPath()) ("tipo-recovery-" + [System.Guid]::NewGuid().ToString("N") + ".env")
    try {
        "TIPO_RECOVERY_PASSWORD=$password" | Set-Content -Encoding UTF8 $tmpEnv
        Write-OutputBox "Preparando recuperación de acceso con perfil '$profile'..."
        Invoke-Capture "set COMPOSE_PROFILES=$profile && docker compose build $service"
        Invoke-Capture "set COMPOSE_PROFILES=$profile && docker compose run --rm --no-deps --user root --entrypoint sh $service -c `"mkdir -p /app/data && chown -R 10001:10001 /app/data && chmod 700 /app/data`""
        Invoke-Capture "set COMPOSE_PROFILES=$profile && docker compose run --rm --no-deps --env-file `"$tmpEnv`" $service python -m app.auth_cli reset-admin --username `"$username`" --password-env TIPO_RECOVERY_PASSWORD"
        [System.Windows.Forms.MessageBox]::Show("Acceso administrador restablecido. Reinicia Tipo e inicia sesión con la nueva contraseña.", "Tipo", "OK", "Information") | Out-Null
    } finally {
        if (Test-Path $tmpEnv) { Remove-Item $tmpEnv -Force -ErrorAction SilentlyContinue }
    }
}

function Show-PrerequisitesHelp {
    $msg = "Requisitos de Tipo:`n`n" +
           "1. Docker Desktop instalado y arrancado. Es obligatorio.`n" +
           "   https://www.docker.com/products/docker-desktop/`n`n" +
           "2. Ollama es opcional. Si no esta instalado, Tipo puede usar Ollama dentro de Docker.`n" +
           "   https://ollama.com/download`n`n" +
           "Tras instalar Docker, abre Docker Desktop y vuelve a ejecutar este panel."
    [System.Windows.Forms.MessageBox]::Show($msg, "Tipo - requisitos", "OK", "Information") | Out-Null
}

function Update-Status {
    $port = Get-Port
    $url = "http://localhost:$port"

    if (Test-DockerCli) {
        if (Test-DockerRunning) {
            $dockerLabel.Text = "Docker: disponible y arrancado"
            $dockerLabel.ForeColor = [System.Drawing.Color]::DarkGreen
        } else {
            $dockerLabel.Text = "Docker: instalado, pero no arrancado"
            $dockerLabel.ForeColor = [System.Drawing.Color]::DarkOrange
        }
    } else {
        $dockerLabel.Text = "Docker: no instalado"
        $dockerLabel.ForeColor = [System.Drawing.Color]::DarkRed
    }

    if (Test-OllamaNative) {
        $ollamaLabel.Text = "Ollama: instalado y arrancado"
        $ollamaLabel.ForeColor = [System.Drawing.Color]::DarkGreen
    } elseif (Test-OllamaInstalled) {
        $ollamaLabel.Text = "Ollama: instalado, no arrancado"
        $ollamaLabel.ForeColor = [System.Drawing.Color]::DarkOrange
    } else {
        $ollamaLabel.Text = "Ollama: no instalado; se usara Docker"
        $ollamaLabel.ForeColor = [System.Drawing.Color]::DimGray
    }

    if (Test-DockerCompose) {
        $composeLabel.Text = "Compose: disponible"
        $composeLabel.ForeColor = [System.Drawing.Color]::DarkGreen
    } else {
        $composeLabel.Text = "Compose: no disponible"
        $composeLabel.ForeColor = [System.Drawing.Color]::DarkRed
    }

    try {
        $response = Invoke-WebRequest -Uri "$url/api/estado" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $appLabel.Text = "Tipo: en ejecucion ($url)"
            $appLabel.ForeColor = [System.Drawing.Color]::DarkGreen
        } else {
            $appLabel.Text = "Tipo: respuesta inesperada ($($response.StatusCode))"
            $appLabel.ForeColor = [System.Drawing.Color]::DarkOrange
        }
    } catch {
        $appLabel.Text = "Tipo: detenido o iniciandose"
        $appLabel.ForeColor = [System.Drawing.Color]::DimGray
    }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Tipo - Instalador y panel de control"
$form.Size = New-Object System.Drawing.Size(840, 690)
$form.StartPosition = "CenterScreen"
$form.MinimumSize = New-Object System.Drawing.Size(760, 650)
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$iconPath = Join-Path $Root "Tipo.ico"
if (Test-Path $iconPath) { try { $form.Icon = New-Object System.Drawing.Icon($iconPath) } catch {} }

$title = New-Object System.Windows.Forms.Label
$title.Text = "Tipo 0.2.0-beta.4 - instalacion local segura"
$title.Font = New-Object System.Drawing.Font("Segoe UI", 17, [System.Drawing.FontStyle]::Bold)
$title.Location = New-Object System.Drawing.Point(22, 18)
$title.Size = New-Object System.Drawing.Size(780, 34)
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = "Desde esta ventana puedes instalar, iniciar, detener, reparar permisos y recuperar acceso. Beta orientada a monografia moderna impresa."
$subtitle.Location = New-Object System.Drawing.Point(24, 58)
$subtitle.Size = New-Object System.Drawing.Size(780, 26)
$form.Controls.Add($subtitle)

$dockerLabel = New-Object System.Windows.Forms.Label
$dockerLabel.Location = New-Object System.Drawing.Point(26, 96)
$dockerLabel.Size = New-Object System.Drawing.Size(310, 24)
$dockerLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($dockerLabel)

$composeLabel = New-Object System.Windows.Forms.Label
$composeLabel.Location = New-Object System.Drawing.Point(346, 96)
$composeLabel.Size = New-Object System.Drawing.Size(190, 24)
$composeLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($composeLabel)

$ollamaLabel = New-Object System.Windows.Forms.Label
$ollamaLabel.Location = New-Object System.Drawing.Point(546, 96)
$ollamaLabel.Size = New-Object System.Drawing.Size(260, 24)
$ollamaLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($ollamaLabel)

$appLabel = New-Object System.Windows.Forms.Label
$appLabel.Location = New-Object System.Drawing.Point(26, 124)
$appLabel.Size = New-Object System.Drawing.Size(780, 24)
$appLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($appLabel)

function New-Button {
    param([string]$Text, [int]$X, [int]$Y, [scriptblock]$OnClick)
    $btn = New-Object System.Windows.Forms.Button
    $btn.Text = $Text
    $btn.Location = New-Object System.Drawing.Point($X, $Y)
    $btn.Size = New-Object System.Drawing.Size(185, 44)
    $btn.Add_Click($OnClick)
    $form.Controls.Add($btn)
    return $btn
}

New-Button "Comprobar requisitos" 26 164 { Update-Status; Show-PrerequisitesHelp; Write-OutputBox "Comprobacion de requisitos ejecutada." }
New-Button "Instalar / iniciar" 222 164 { Invoke-ConsoleScript "instalar.bat" "Tipo - instalacion" }
New-Button "Abrir Tipo" 418 164 {
    $port = Get-Port
    Start-Process "http://localhost:$port"
    Write-OutputBox "Abriendo http://localhost:$port"
}
New-Button "Detener" 614 164 { Invoke-ConsoleScript "detener.bat" "Tipo - detener" }

New-Button "Gestionar acceso" 26 220 { Show-ResetAdminDialog; Update-Status }
New-Button "Reparar permisos" 222 220 { Repair-DataPermissions; Update-Status }
New-Button "Ver estado Docker" 418 220 { Invoke-Capture "docker compose ps"; Update-Status }
New-Button "Ver logs" 614 220 { Invoke-Capture "docker compose logs --tail=160" }

New-Button "Desinstalar" 26 276 {
    $confirm = [System.Windows.Forms.MessageBox]::Show(
        "Se abrira el desinstalador de Tipo. No elimina Docker ni Ollama del equipo. ¿Continuar?",
        "Tipo - desinstalar",
        "YesNo",
        "Warning"
    )
    if ($confirm -eq [System.Windows.Forms.DialogResult]::Yes) {
        Invoke-ConsoleScript "desinstalar.bat" "Tipo - desinstalar"
    }
}

$script:OutputBox = New-Object System.Windows.Forms.TextBox
$script:OutputBox.Location = New-Object System.Drawing.Point(26, 336)
$script:OutputBox.Size = New-Object System.Drawing.Size(772, 230)
$script:OutputBox.Multiline = $true
$script:OutputBox.ScrollBars = "Vertical"
$script:OutputBox.ReadOnly = $true
$script:OutputBox.Font = New-Object System.Drawing.Font("Consolas", 9)
$form.Controls.Add($script:OutputBox)

$note = New-Object System.Windows.Forms.Label
$note.Text = "Instalacion local: la aplicacion se publica solo en localhost. En el primer arranque se crea un usuario administrador local. Si no puedes crearlo, usa 'Reparar permisos'. Si pierdes la contraseña, usa 'Gestionar acceso'."
$note.Location = New-Object System.Drawing.Point(26, 585)
$note.Size = New-Object System.Drawing.Size(772, 38)
$form.Controls.Add($note)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 9000
$timer.Add_Tick({ Update-Status })
$timer.Start()

$form.Add_Shown({
    Write-OutputBox "Panel iniciado en: $Root"
    Write-OutputBox "Usa 'Instalar / iniciar' para preparar Docker, comprobar Ollama y abrir Tipo."
    Update-Status
})

[void]$form.ShowDialog()
