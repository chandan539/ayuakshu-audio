#!/usr/bin/env bash
# Development helper: start FastAPI + Vite UI (browser) without Tauri.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:$PATH"
# shellcheck disable=SC1091
source "$ROOT/backend/.venv/bin/activate"
export PYTHONPATH="$ROOT/backend"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export OFFLINEVOICE_MODELS_DIR="${OFFLINEVOICE_MODELS_DIR:-$ROOT/models}"
export OFFLINEVOICE_DATA_DIR="${OFFLINEVOICE_DATA_DIR:-$ROOT/outputs/app_data}"

PORT=8765
python -m app.main --host 127.0.0.1 --port "$PORT" --data-dir "$OFFLINEVOICE_DATA_DIR" &
BACKEND_PID=$!
cleanup() { kill "$BACKEND_PID" 2>/dev/null || true; }
trap cleanup EXIT

sleep 2
cd "$ROOT/frontend"
VITE_BACKEND_URL="http://127.0.0.1:$PORT" npm run dev -- --host 127.0.0.1 --port 1420
