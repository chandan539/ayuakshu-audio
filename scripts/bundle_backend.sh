#!/usr/bin/env bash
# Bundle the Python backend for OfflineVoice.app (Apple Silicon).
# Output: src-tauri/resources/backend/offlinevoice-backend/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:${PATH:-}"
# shellcheck disable=SC1091
source "$ROOT/backend/.venv/bin/activate"

OUT_PARENT="$ROOT/src-tauri/resources/backend"
OUT_DIR="$OUT_PARENT/offlinevoice-backend"
WORK="$ROOT/backend/packaging"
BUILD_DIR="$WORK/build"
DIST_DIR="$WORK/dist"

echo "=== Bundling OfflineVoice backend (PyInstaller onedir) ==="
rm -rf "$BUILD_DIR" "$DIST_DIR" "$OUT_DIR"
mkdir -p "$OUT_PARENT" "$BUILD_DIR" "$DIST_DIR"

pushd "$WORK" >/dev/null
pyinstaller offlinevoice-backend.spec \
  --noconfirm \
  --clean \
  --distpath "$DIST_DIR" \
  --workpath "$BUILD_DIR"
popd >/dev/null

if [[ ! -x "$DIST_DIR/offlinevoice-backend/offlinevoice-backend" ]]; then
  echo "ERROR: PyInstaller did not produce offlinevoice-backend binary" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
rsync -a --delete "$DIST_DIR/offlinevoice-backend/" "$OUT_DIR/"

# Marker so Rust can detect production backend.
cat > "$OUT_PARENT/BACKEND_BUNDLE.txt" <<EOF
name=offlinevoice-backend
arch=aarch64-apple-darwin
built=$(date -u +%Y-%m-%dT%H:%M:%SZ)
note=Model weights are NOT included. Install OfflineVoice-Models separately.
EOF

SIZE="$(du -sh "$OUT_DIR" | awk '{print $1}')"
echo "Backend bundle ready: $OUT_DIR ($SIZE)"
echo "Smoke-launch check (help)…"
"$OUT_DIR/offlinevoice-backend" --help >/dev/null 2>&1 || true
echo "Done."
