#!/usr/bin/env bash
# Photo Match PWA — deploy script (run on the server)
# Pulls latest code and restarts the server.
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo "=== Pulling latest ==="
git pull

echo "=== Installing/updating dependencies ==="
if [ -d "venv" ]; then
    venv/bin/pip install -r requirements.txt --quiet
else
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt --quiet
fi

echo "=== Restarting server ==="
# Systemd
if systemctl is-active --quiet photo-match 2>/dev/null; then
    sudo systemctl restart photo-match
    echo "Restarted via systemd"
else
    pkill -f "python.*app.py" 2>/dev/null || true
    sleep 1
    PORT="${PORT:-5000}"
    CERT_ARG=""
    if [ -n "$CERT_PATH" ] && [ -n "$KEY_PATH" ]; then
        CERT_ARG="--cert $CERT_PATH --key $KEY_PATH"
    fi
    nohup venv/bin/python app.py --host 0.0.0.0 --port "$PORT" $CERT_ARG >> app.log 2>&1 &
    echo "Restarted (PID $!), logs in app.log"
fi

echo "=== Done ==="
