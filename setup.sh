#!/usr/bin/env bash
# Photo Match PWA — setup
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "📷 Setting up Photo Match PWA..."
echo ""

# Python venv
if [ ! -d "$APP_DIR/venv" ]; then
    echo "→ Creating virtual environment..."
    python3 -m venv "$APP_DIR/venv"
fi

echo "→ Installing dependencies..."
"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet

# Config
if [ ! -f "$APP_DIR/config.json" ]; then
    echo ""
    echo "⚠️  No config.json found."
    echo "   Copy config.example.json and fill in your database credentials:"
    echo "   cp config.example.json config.json && nano config.json"
fi

echo ""
echo "✅ Done! Run with:"
echo "   ./run.sh"
echo ""
echo "   Or with HTTPS (requires a certificate):"
echo "   ./run.sh --cert /path/to/cert.pem --key /path/to/key.pem"
