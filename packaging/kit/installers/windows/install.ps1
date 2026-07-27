# =============================================================================
# AlphaX POS Bridge - Windows installer            (invoked by the .bat wrapper)
#
# v15.5.2 - non-admin capable.
#
# What changed from 15.5.1 and why:
#
#   1. PORT. Was $Port = 8720 while the daemon, the wizard and every doc use
#      8420. The firewall was opened on a port nothing listened to. Loopback
#      ignores the firewall, so a cashier on the same PC never noticed - it
#      only broke when a second device tried to reach the bridge over the LAN.
#
#   2. CONFIG. The installer wrote none. `python -m alphax_bridge` exits 1
#      with "No config found" when there is no config.yaml/json, so if the
#      cashier closed the wizard the logon task launched a tray app that died
#      instantly, every time, with no visible error. We now always write a
#      minimal config first; the wizard edits it afterwards.
#
#   3. BIND HOST. Default is 127.0.0.1, so the bridge is unreachable from any
#      other device no matter what the firewall says. -LanAccess switches it
#      to 0.0.0.0 AND opens the firewall - the two must move together or
#      neither does anything.
#
#   4. NON-ADMIN. Register-ScheduledTask had no explicit principal, and
#      ProgramData was assumed writable. On locked-down tills both fail. We
#      now register an explicitly interactive, limited-privilege task and fall
#      back to the HKCU Run key when Task Scheduler is denied. Install dir
#      falls back to LOCALAPPDATA.
#
#   5. PAIRING. -PairUrl / -PairToken are written into the config so the
#      bridge calls home to the POS on first start and the onboarding wizard's
#      "waiting for bridge" step resolves without anyone copying a token.
#
# Usage:
#   .\install.ps1
#   .\install.ps1 -LanAccess                       # serve tablet registers
#   .\install.ps1 -Port 8421                       # 8420 already taken
#   .\install.ps1 -PairUrl https://pos.example.com -PairToken abc123
# =============================================================================

[CmdletBinding()]
param(
    [int]    $Port      = 8420,
    [switch] $LanAccess,
    [string] $PairUrl   = '',
    [string] $PairToken = '',
    [string] $AuthToken = ''
)

$ErrorActionPreference = 'Stop'
$AppName  = 'AlphaX POS Bridge'
$TaskName = 'AlphaX POS Bridge'
$RunKey   = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$RunName  = 'AlphaXPOSBridge'

$KitRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Wheel   = Get-ChildItem -Path $KitRoot -Filter 'alphax_pos_bridge-*.whl' |
           Sort-Object Name -Descending | Select-Object -First 1

Write-Host ''
Write-Host "=== $AppName Setup ===" -ForegroundColor Cyan
if (-not $Wheel) {
    throw 'Bridge package (.whl) not found next to the installer. Keep the setup folder together.'
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}
$IsAdmin = Test-Admin
Write-Host ("Running as {0}." -f $(if ($IsAdmin) { 'Administrator' } else { 'standard user' }))

# --- 0. Install location ------------------------------------------------------
# ProgramData looks shared but a standard user's new folder there ends up owned
# by them anyway, which breaks the NEXT user on a shared till. Prefer it only
# when we can actually write; otherwise go per-user and be honest about it.
function Resolve-InstallDir {
    $shared = Join-Path $env:ProgramData 'AlphaXBridge'
    try {
        New-Item -ItemType Directory -Force -Path $shared -ErrorAction Stop | Out-Null
        $probe = Join-Path $shared '.writetest'
        Set-Content -Path $probe -Value 'x' -ErrorAction Stop
        Remove-Item $probe -Force -ErrorAction SilentlyContinue
        return $shared
    } catch {
        $perUser = Join-Path $env:LOCALAPPDATA 'AlphaXBridge'
        New-Item -ItemType Directory -Force -Path $perUser | Out-Null
        Write-Host "ProgramData not writable - installing for this user only:" -ForegroundColor Yellow
        Write-Host "  $perUser" -ForegroundColor Yellow
        return $perUser
    }
}
$InstallDir = Resolve-InstallDir
Write-Host "Install location: $InstallDir"

# --- 1. Python ----------------------------------------------------------------
function Find-Python {
    foreach ($cmd in @('py -3', 'python3', 'python')) {
        try {
            $v = & cmd /c "$cmd -c ""import sys;print(sys.version_info[:2])""" 2>$null
            if ($v -match '\((\d+), (\d+)\)' -and
                ([int]$Matches[1] -gt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -ge 10))) {
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
            winget install --id Python.Python.3.12 -e --silent `
                   --accept-package-agreements --accept-source-agreements
            $installed = $true
        } catch { Write-Host 'winget failed, falling back to direct download...' }
    }
    if (-not $installed) {
        # Older Windows 10 / LTSC has no winget. Per-user silent install needs
        # no elevation, which is the whole point on a locked-down till.
        $pyUrl = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
        $pyExe = Join-Path $env:TEMP 'python-3.12.10-amd64.exe'
        Write-Host 'Downloading Python from python.org...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $pyUrl -OutFile $pyExe -UseBasicParsing
        Write-Host 'Installing Python silently (about a minute)...'
        Start-Process -FilePath $pyExe -Wait -ArgumentList `
            '/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_tcltk=1 Include_test=0'
    }
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
    $py = Find-Python
    if (-not $py) {
        throw 'Python did not install. Install Python 3.12 from python.org manually, then re-run.'
    }
}
Write-Host "Python: $py"

# --- 2. Private environment + bridge ------------------------------------------
$Venv = Join-Path $InstallDir 'env'
$VPy  = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $VPy)) {
    Write-Host 'Creating private environment...'
    & cmd /c "$py -m venv `"$Venv`""
}
if (-not (Test-Path $VPy)) { throw "Virtual environment was not created at $Venv" }

Write-Host 'Installing the bridge (this may take a minute)...'
& $VPy -m pip install --upgrade pip --quiet
& $VPy -m pip install --upgrade "$($Wheel.FullName)[all]" --quiet
if ($LASTEXITCODE -ne 0) { throw 'pip failed to install the bridge wheel.' }

Copy-Item -Path (Join-Path $KitRoot 'profiles') -Destination $InstallDir `
          -Recurse -Force -ErrorAction SilentlyContinue

# --- 3. Config ----------------------------------------------------------------
# Written BEFORE first launch. Without this the daemon exits 1 on startup and
# the logon task fails invisibly. The wizard edits this file afterwards; we
# never overwrite an existing one.
$CfgDir  = Join-Path $env:USERPROFILE '.alphax-bridge'
$CfgFile = Join-Path $CfgDir 'config.json'
New-Item -ItemType Directory -Force -Path $CfgDir | Out-Null

if (-not $AuthToken) {
    $bytes = New-Object byte[] 24
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $AuthToken = ([Convert]::ToBase64String($bytes) -replace '[^A-Za-z0-9]', '').Substring(0, 24)
}

$BindHost = if ($LanAccess) { '0.0.0.0' } else { '127.0.0.1' }

if (Test-Path $CfgFile) {
    Write-Host "Existing config kept: $CfgFile"
    try {
        $existing = Get-Content $CfgFile -Raw | ConvertFrom-Json
        if ($existing.bridge.auth_token) { $AuthToken = $existing.bridge.auth_token }
        if ($existing.bridge.bind_port)  { $Port      = [int]$existing.bridge.bind_port }
    } catch { Write-Host 'Existing config unreadable - leaving it alone.' -ForegroundColor Yellow }
} else {
    $bridge = [ordered]@{
        bind_host   = $BindHost
        bind_port   = $Port
        auth_token  = $AuthToken
        cors_origin = '*'
    }
    if ($PairUrl -and $PairToken) {
        $bridge.pair_url   = $PairUrl
        $bridge.pair_token = $PairToken
    }
    ([ordered]@{ bridge = $bridge; devices = @() } | ConvertTo-Json -Depth 6) |
        Set-Content -Path $CfgFile -Encoding UTF8
    Write-Host "Config written: $CfgFile"
}

# --- 4. Autostart -------------------------------------------------------------
# Scheduled task first: it survives a locked screen and reports failures.
# Explicitly Interactive + Limited so a standard user can register it for
# themselves without elevation. If Task Scheduler is denied by policy, fall
# back to the HKCU Run key, which needs no privileges at all.
$TrayExe = Join-Path $Venv 'Scripts\alphax-bridge-tray.exe'
$autostart = 'none'

try {
    $action  = New-ScheduledTaskAction -Execute $TrayExe
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $principal = New-ScheduledTaskPrincipal `
                    -UserId "$env:USERDOMAIN\$env:USERNAME" `
                    -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet `
                    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                    -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
                           -Principal $principal -Settings $settings -Force `
                           -ErrorAction Stop | Out-Null
    $autostart = 'task'
    Write-Host 'Autostart registered as a scheduled task (runs at your logon).'
} catch {
    Write-Host "Scheduled task refused ($($_.Exception.Message.Split([Environment]::NewLine)[0]))." -ForegroundColor Yellow
    try {
        New-Item -Path $RunKey -Force -ErrorAction SilentlyContinue | Out-Null
        Set-ItemProperty -Path $RunKey -Name $RunName -Value ('"{0}"' -f $TrayExe) -ErrorAction Stop
        $autostart = 'runkey'
        Write-Host 'Autostart registered via the user Run key instead.'
    } catch {
        Write-Host 'Could not register autostart. Start the bridge from the Start menu after each logon.' -ForegroundColor Red
    }
}

# --- 5. Firewall --------------------------------------------------------------
# Only meaningful when we are actually listening beyond loopback. Opening a
# port while bound to 127.0.0.1 achieves nothing, which is what 15.5.1 did.
if ($LanAccess) {
    if ($IsAdmin) {
        try {
            Get-NetFirewallRule -DisplayName $AppName -ErrorAction SilentlyContinue |
                Remove-NetFirewallRule -ErrorAction SilentlyContinue
            New-NetFirewallRule -DisplayName $AppName -Direction Inbound -Action Allow `
                -Protocol TCP -LocalPort $Port -Profile Private,Domain -ErrorAction Stop | Out-Null
            Write-Host "Firewall opened for port $Port on private networks."
        } catch {
            Write-Host "Could not add the firewall rule: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } else {
        Write-Host '' 
        Write-Host 'LAN access needs a firewall rule, which requires Administrator.' -ForegroundColor Yellow
        Write-Host 'Ask IT to run this once in an elevated PowerShell:' -ForegroundColor Yellow
        Write-Host ("  New-NetFirewallRule -DisplayName '$AppName' -Direction Inbound " +
                    "-Action Allow -Protocol TCP -LocalPort $Port -Profile Private,Domain") -ForegroundColor Gray
    }
} else {
    Write-Host 'Listening on this PC only. Re-run with -LanAccess to serve tablet registers.'
}

# --- 6. First run -------------------------------------------------------------
Write-Host ''
Write-Host 'Launching the setup wizard - add your receipt and kitchen printers there.' -ForegroundColor Green
Start-Process -FilePath (Join-Path $Venv 'Scripts\alphax-bridge-wizard.exe') `
              -ArgumentList "--port $Port"
Start-Process -FilePath $TrayExe

Write-Host ''
Write-Host '--- Summary -------------------------------------------------' -ForegroundColor Cyan
Write-Host ("  URL        : http://localhost:{0}" -f $Port)
Write-Host ("  Bind host  : {0}" -f $BindHost)
Write-Host ("  Config     : {0}" -f $CfgFile)
Write-Host ("  Auth token : {0}" -f $AuthToken)
Write-Host ("  Autostart  : {0}" -f $autostart)
Write-Host '-------------------------------------------------------------' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Write the auth token down - the POS asks for it once.' -ForegroundColor Yellow
Write-Host 'To remove the bridge later, run Uninstall-AlphaX-Bridge.bat from this folder.'
