@echo off
:: ===========================================================================
:: AlphaX POS Bridge — one-click Windows installer
:: Double-click this file. It will:
::   1. Find Python 3.9+ (or install it silently via winget)
::   2. Install the bridge into its own private environment
::   3. Register autostart (runs in the tray on every logon)
::   4. Open the Windows Firewall for the bridge port (LAN only)
::   5. Launch the setup wizard to add your printers
:: Safe to re-run: upgrades in place, never duplicates.
:: ===========================================================================
title AlphaX POS Bridge Setup
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installers\windows\install.ps1"
if errorlevel 1 (
  echo.
  echo Installation did not complete. See the messages above.
  pause
)
