#!/bin/bash
# Setup script for macOS — install dependencies and start the Laya server
set -e

echo "=== Laya Local Server — macOS Setup ==="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is required but not found."
    exit 1
fi

PYTHON=$(command -v python3)
echo "[1/4] Python found: $PYTHON ($($PYTHON --version))"

# Create and activate a virtual environment in the repo dir
$PYTHON -m venv .venv
source .venv/bin/activate
echo "[2/4] Virtual environment created."

# Install dependencies
pip install --quiet --upgrade pip
pip install -r requirements.txt
echo "[3/4] Dependencies installed."

# Download model on first run (done by server, but pre-warm it here)
echo "[4/4] Starting server (model will download on first run)..."
echo ""
echo "Server will be available at: http://localhost:8765"
echo "Press Ctrl+C to stop."
echo ""
uvicorn laya_server:app --host 127.0.0.1 --port 8765
