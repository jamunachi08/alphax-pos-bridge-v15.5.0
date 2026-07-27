@echo off
title AlphaX POS Bridge Uninstall
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Unregister-ScheduledTask -TaskName 'AlphaX POS Bridge' -Confirm:$false -ErrorAction SilentlyContinue;" ^
  "Get-Process alphax-bridge*,python* -ErrorAction SilentlyContinue | Where-Object {$_.Path -like '*AlphaXBridge*'} | Stop-Process -Force -ErrorAction SilentlyContinue;" ^
  "Remove-NetFirewallRule -DisplayName 'AlphaX POS Bridge' -ErrorAction SilentlyContinue;" ^
  "Remove-Item -Recurse -Force (Join-Path $env:ProgramData 'AlphaXBridge') -ErrorAction SilentlyContinue;" ^
  "Write-Host 'AlphaX POS Bridge removed.'"
pause
