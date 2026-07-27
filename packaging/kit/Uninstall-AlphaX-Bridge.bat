@echo off
title AlphaX POS Bridge Uninstall
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Unregister-ScheduledTask -TaskName 'AlphaX POS Bridge' -Confirm:$false -ErrorAction SilentlyContinue;" ^
  "Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'AlphaXPOSBridge' -ErrorAction SilentlyContinue;" ^
  "Get-Process alphax-bridge*,python* -ErrorAction SilentlyContinue | Where-Object {$_.Path -like '*AlphaXBridge*'} | Stop-Process -Force -ErrorAction SilentlyContinue;" ^
  "Remove-NetFirewallRule -DisplayName 'AlphaX POS Bridge' -ErrorAction SilentlyContinue;" ^
  "foreach ($d in @((Join-Path $env:ProgramData 'AlphaXBridge'),(Join-Path $env:LOCALAPPDATA 'AlphaXBridge'))) { Remove-Item -Recurse -Force $d -ErrorAction SilentlyContinue };" ^
  "Write-Host 'AlphaX POS Bridge removed.';" ^
  "Write-Host 'Printer setup and auth token kept in ~\.alphax-bridge - delete that folder for a clean slate.' -ForegroundColor Gray"
pause
