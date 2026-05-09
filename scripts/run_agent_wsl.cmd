@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_agent_wsl.ps1" %*
exit /b %ERRORLEVEL%
