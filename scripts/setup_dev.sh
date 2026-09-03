#!/usr/bin/env bash
# OfflineVoice — developer environment check (Phase 1+)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== OfflineVoice setup_dev ==="
echo "Project: $ROOT"
echo

ok() { echo "  OK  $1"; }
warn() { echo "  WARN $1"; }
fail() { echo "  FAIL $1"; }

# --- Architecture ---
ARCH="$(uname -m)"
echo "Architecture: $ARCH"
if [[ "$ARCH" == "arm64" ]]; then
  ok "Apple Silicon"
else
  warn "Intel Mac detected — TTS will be slower (CPU). Apple Silicon is recommended."
fi

# --- RAM ---
if MEM_BYTES="$(sysctl -n hw.memsize 2>/dev/null)"; then
  MEM_GB=$((MEM_BYTES / 1024 / 1024 / 1024))
  echo "Memory: ${MEM_GB} GB"
  if (( MEM_GB < 16 )); then
    warn "Recommended: Apple Silicon + 16 GB RAM or more. Your system may generate audio more slowly."
  else
    ok "RAM meets recommended minimum"
  fi
else
  warn "Could not read RAM via sysctl"
fi

# --- Python ---
PYTHON_BIN=""
for candidate in \
  "$ROOT/backend/.venv/bin/python" \
  /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
  /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  python3
do
  if [[ -x "$candidate" ]] && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  fail "Python >= 3.10 not found"
  exit 1
fi
ok "Python: $($PYTHON_BIN --version 2>&1)"

# --- Optional toolchain (needed for later Tauri phases) ---
command -v node >/dev/null && ok "Node: $(node --version)" || warn "Node not installed (needed for Phase 4+). Suggested: ~/.local/node or fnm"
command -v npm >/dev/null && ok "npm: $(npm --version)" || warn "npm not installed (needed for Phase 4+)"
command -v rustc >/dev/null && ok "Rust: $(rustc --version)" || warn "Rust not installed (needed for Phase 4+). Suggested: rustup"
command -v cargo >/dev/null && ok "Cargo: $(cargo --version)" || warn "Cargo not installed (needed for Phase 4+)"
command -v ffmpeg >/dev/null && ok "FFmpeg: $(ffmpeg -version | head -1)" || warn "FFmpeg not installed (MP3 uses lameenc; FFmpeg optional)"
command -v afconvert >/dev/null && ok "afconvert (macOS built-in)" || warn "afconvert missing"

# --- venv ---
VENV="$ROOT/backend/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo
  echo "Creating backend/.venv ..."
  "$PYTHON_BIN" -m venv "$VENV"
fi
# Prefer the venv interpreter going forward
# shellcheck disable=SC1091
source "$VENV/bin/activate"
ok "venv: $VENV ($(python --version))"

echo
echo "Installing Python dependencies into backend/.venv ..."
pip install --upgrade pip setuptools wheel
pip install -r "$ROOT/backend/requirements.txt"

echo
echo "=== Setup complete (Phase 1 Python env) ==="
echo "Next:"
echo "  1) python backend/scripts/install_chatterbox_model.py"
echo "  2) python test_tts.py"
echo "  3) (optional) turn Wi-Fi OFF and re-run test_tts.py"
