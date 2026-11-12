@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_windows.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" pause
endlocal & exit /b %EXITCODE%
