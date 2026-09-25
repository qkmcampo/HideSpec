#!/usr/bin/env bash

set -u

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$BASE_DIR/../Leather-Inspection-Web"
cd "$BASE_DIR"

if [ ! -x "$BASE_DIR/venv/bin/python" ]; then
  echo "Virtual environment not found: $BASE_DIR/venv/bin/python"
  exit 1
fi

if [ ! -f "$FRONTEND_DIR/package.json" ]; then
  echo "Frontend not found: $FRONTEND_DIR"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to start the web app"
  exit 1
fi

source "$BASE_DIR/venv/bin/activate"

echo "Starting HideSpec API server on port 5001..."
python3 api_server.py &
API_PID=$!

echo "Starting web app on port 5173..."
(
  cd "$FRONTEND_DIR"
  npm run dev -- --host 0.0.0.0 --port 5173
) &
WEB_PID=$!

cleanup() {
  echo
  echo "Stopping HideSpec services..."
  kill "$API_PID" 2>/dev/null || true
  kill "$WEB_PID" 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
  wait "$WEB_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

sleep 2

echo "Starting leather inspection and camera stream on port 5000..."
python3 app5.py
