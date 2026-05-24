@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_agent_ui_wsl.ps1" %*
exit /b %ERRORLEVEL%
