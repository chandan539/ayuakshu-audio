#!/usr/bin/env bash
# PHASE 7 — Offline QA harness.
# Verifies launch/backend/model/voice/Hindi/English/export with outbound
# network blocked in-process (except loopback).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:${PATH:-}"

PY="${ROOT}/backend/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: missing venv at backend/.venv — run ./scripts/setup_dev.sh" >&2
  exit 1
fi

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1
export OFFLINEVOICE_MODELS_DIR="${OFFLINEVOICE_MODELS_DIR:-$ROOT/models}"

echo "=== OfflineVoice offline QA ==="
echo "Models: $OFFLINEVOICE_MODELS_DIR"
echo

ok=0
fail=0
check() {
  local name="$1"
  shift
  echo "--- $name ---"
  if "$@"; then
    echo "PASS: $name"
    ok=$((ok + 1))
  else
    echo "FAIL: $name"
    fail=$((fail + 1))
  fi
  echo
}

# 1) Unit / API regression (offline env already set)
check "pytest (offline flags)" \
  env PYTHONPATH=backend "$PY" -m pytest backend/tests -q --tb=line

# 2) Packaged app present (optional soft-check)
if [[ -d "$ROOT/dist/OfflineVoice.app" ]]; then
  check "production .app exists" test -x "$ROOT/dist/OfflineVoice.app/Contents/MacOS/offlinevoice"
  check "no model weights in .app" \
    bash -c "! find \"$ROOT/dist/OfflineVoice.app\" -name 't3_mtl*.safetensors' | grep -q ."
  BACKEND_BIN="$ROOT/dist/OfflineVoice.app/Contents/Resources/resources/backend/offlinevoice-backend/offlinevoice-backend"
  if [[ -x "$BACKEND_BIN" ]]; then
    check "bundled backend --help" "$BACKEND_BIN" --help
  fi
else
  echo "WARN: dist/OfflineVoice.app missing — skip app bundle checks (run Phase 6 first)"
  echo
fi

# 3) Core offline generation (network guard inside Python)
check "offline Hindi+English generate + export" \
  "$PY" "$ROOT/backend/scripts/offline_qa.py"

# 4) Network audit (static)
check "network audit" "$ROOT/scripts/network_audit.sh"

echo "=== Summary: $ok passed, $fail failed ==="
if (( fail > 0 )); then
  exit 1
fi
echo "PHASE 7 offline QA: ALL CHECKS PASSED"
