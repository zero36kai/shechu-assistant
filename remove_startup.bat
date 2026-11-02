@echo off
pwsh -NoLogo -NoProfile -File "%~dp0tools\startup.ps1" -Action Remove
pause
