# AlphaX POS Bridge - Windows installer (invoked by Install-AlphaX-Bridge.bat)
$ErrorActionPreference = 'Stop'
$AppName   = 'AlphaX POS Bridge'
$InstallDir = Join-Path $env:ProgramData 'AlphaXBridge'
$KitRoot    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)  # setup kit root
$Wheel      = Get-ChildItem -Path $KitRoot -Filter 'alphax_pos_bridge-*.whl' | Select-Object -First 1
$Port       = 8720

Write-Host ''
Write-Host '=== AlphaX POS Bridge Setup ===' -ForegroundColor Cyan
if (-not $Wheel) { throw 'Bridge package (.whl) not found next to the installer. Keep the setup folder together.' }

# --- 1. Python ---------------------------------------------------------------
function Find-Python {
    foreach ($cmd in @('py -3', 'python3', 'python')) {
        try {
            $v = & cmd /c "$cmd -c ""import sys;print(sys.version_info[:2])""" 2>$null
            if ($v -match '\((\d+), (\d+)\)' -and ([int]$Matches[1] -gt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -ge 9))) {
                return $cmd
            }
        } catch {}
    }
    return $null
}
$py = Find-Python
if (-not $py) {
    Write-Host 'Python not found - installing Python 3.12 (one time)...'
    $installed = $false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        try {
            winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
            $installed = $true
        } catch { Write-Host 'winget install failed, falling back to direct download...' }
    }
    if (-not $installed) {
        # No winget (older Windows 10 / LTSC): fetch the official
        # python.org installer and run it silently, per-user, with Tk.
        $pyUrl = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
        $pyExe = Join-Path $env:TEMP 'python-3.12.10-amd64.exe'
        Write-Host "Downloading Python from python.org..."
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $pyUrl -OutFile $pyExe -UseBasicParsing
        Write-Host 'Installing Python silently (about a minute)...'
        Start-Process -FilePath $pyExe -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_tcltk=1 Include_test=0' -Wait
    }
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    $py = Find-Python
    if (-not $py) { throw 'Python installation did not complete. Install Python 3.12 from python.org manually, then re-run this installer.' }
}
Write-Host "Python found: $py"

# --- 2. Private environment + bridge -----------------------------------------
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Venv = Join-Path $InstallDir 'env'
if (-not (Test-Path (Join-Path $Venv 'Scripts\python.exe'))) {
    Write-Host 'Creating private environment...'
    & cmd /c "$py -m venv `"$Venv`""
}
$VPy = Join-Path $Venv 'Scripts\python.exe'
Write-Host 'Installing the bridge (this may take a minute)...'
& $VPy -m pip install --upgrade pip --quiet
& $VPy -m pip install --upgrade "$($Wheel.FullName)[all]" --quiet
Copy-Item -Path (Join-Path $KitRoot 'profiles') -Destination $InstallDir -Recurse -Force -ErrorAction SilentlyContinue

# --- 3. Autostart (Scheduled Task at logon, tray app) -------------------------
$TrayExe = Join-Path $Venv 'Scripts\alphax-bridge-tray.exe'
$Action  = New-ScheduledTaskAction -Execute $TrayExe
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName 'AlphaX POS Bridge' -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host 'Autostart registered (runs in the system tray at every logon).'

# --- 4. Firewall (LAN only) ---------------------------------------------------
try {
    New-NetFirewallRule -DisplayName 'AlphaX POS Bridge' -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $Port -Profile Private,Domain -ErrorAction SilentlyContinue | Out-Null
    Write-Host "Firewall opened for port $Port on private networks."
} catch { Write-Host 'Note: run once as Administrator if registers on other devices cannot reach the bridge.' -ForegroundColor Yellow }

# --- 5. First run: wizard then tray -------------------------------------------
Write-Host ''
Write-Host 'Launching the setup wizard - add your receipt and kitchen printers there.' -ForegroundColor Green
Start-Process -FilePath (Join-Path $Venv 'Scripts\alphax-bridge-wizard.exe')
Start-Process -FilePath $TrayExe
Write-Host ''
Write-Host "Done. The bridge runs at http://localhost:$Port and starts automatically with Windows."
Write-Host 'To remove it later, run Uninstall-AlphaX-Bridge.bat from this folder.'
