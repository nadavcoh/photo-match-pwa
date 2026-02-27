@echo off
REM  Photo Match PWA — deploy.bat
REM  Pulls latest from git, updates deps, restarts the server.
REM  Run this on the Windows server machine.
setlocal
cd /d "%~dp0"

echo.
echo  === Photo Match PWA — Deploy ===
echo.

REM -- Pull latest
echo -- Pulling latest from git...
git pull
if errorlevel 1 (
    echo ERROR: git pull failed.
    pause
    exit /b 1
)

REM -- Install / update deps
echo -- Installing dependencies...
if exist venv\Scripts\pip.exe (
    venv\Scripts\pip install -r requirements.txt --quiet
) else (
    echo  venv not found, running setup...
    call setup.bat
)

REM -- Kill existing instance
echo -- Stopping existing instance ^(if any^)...
taskkill /FI "WINDOWTITLE eq photo_match" /F >nul 2>&1
timeout /t 1 /nobreak >nul

REM -- Start new instance
echo -- Starting server...
set PORT=%PORT%
if "%PORT%"=="" set PORT=5000

set CERT_ARGS=
if defined CERT_PATH if defined KEY_PATH (
    set CERT_ARGS=--cert "%CERT_PATH%" --key "%KEY_PATH%"
)

start "photo_match" /B venv\Scripts\python.exe app.py --host 0.0.0.0 --port %PORT% %CERT_ARGS% >> app.log 2>&1

echo.
echo  === Done — server restarted on port %PORT% ===
echo  Logs: %~dp0app.log
echo.
