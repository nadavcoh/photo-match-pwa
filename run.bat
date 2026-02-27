@echo off
REM  Photo Match PWA
REM
REM  Usage:
REM    run.bat                                  Plain HTTP
REM    run.bat --port 5001                      Custom port
REM    run.bat --debug                          Debug / hot-reload
REM    run.bat --cert host.crt --key host.key   HTTPS (recommended for PWA)
REM
REM  To enable HTTPS with Tailscale (enables full PWA offline support):
REM    1. In PowerShell:  tailscale cert <your-machine-name>
REM    2. Run:  run.bat --cert <your-machine-name>.crt --key <your-machine-name>.key
REM    3. Open: https://<your-machine-name>:5000
REM
setlocal
cd /d "%~dp0"

if not exist venv\Scripts\python.exe (
    echo  venv not found — running setup first...
    call setup.bat
)

call venv\Scripts\activate.bat
python app.py %*
