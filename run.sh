#!/usr/bin/env bash
# Photo Match PWA — run
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

# Auto-setup venv if missing
if [ ! -d "$APP_DIR/venv" ]; then
    echo "→ No venv found, running setup first..."
    bash "$APP_DIR/setup.sh"
fi

PYTHON="$APP_DIR/venv/bin/python"

echo "📷 Starting Photo Match PWA..."
exec "$PYTHON" "$APP_DIR/app.py" \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-5000}" \
    "$@"
