#!/usr/bin/env bash
# Start OfflineVoice local backend on 127.0.0.1 (ephemeral port by default).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/backend/.venv/bin/activate"
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export HF_DATASETS_OFFLINE="${HF_DATASETS_OFFLINE:-1}"
export OFFLINEVOICE_MODELS_DIR="${OFFLINEVOICE_MODELS_DIR:-$ROOT/models}"
ARGS=(--host 127.0.0.1 --port "${PORT:-0}")
if [[ -n "${OFFLINEVOICE_DATA_DIR:-}" ]]; then
  ARGS+=(--data-dir "$OFFLINEVOICE_DATA_DIR")
fi
cd "$ROOT/backend"
exec python -m app.main "${ARGS[@]}"
