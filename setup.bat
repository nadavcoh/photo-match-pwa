@echo off
setlocal
echo.
echo  *** Photo Match PWA - Setup ***
echo.

cd /d "%~dp0"

REM Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install from https://python.org ^(tick "Add to PATH"^)
    pause
    exit /b 1
)

echo -- Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create venv.
    pause
    exit /b 1
)

echo -- Installing dependencies...
venv\Scripts\pip install --upgrade pip --quiet
venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

REM Check for config
if not exist config.json (
    echo.
    echo  ^! No config.json found.
    echo    Copy config.example.json and fill in your database credentials:
    echo      copy config.example.json config.json
    echo      notepad config.json
)

echo.
echo  Setup complete^^!  Run the app with:
echo    run.bat
echo.
echo  With HTTPS ^(Tailscale cert^):
echo    run.bat --cert hostname.crt --key hostname.key
echo.
pause
