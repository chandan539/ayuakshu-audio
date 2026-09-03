#!/usr/bin/env bash
# Build "AYUAKSHU Audio.app" + DMG for Apple Silicon (aarch64).
# Does NOT embed multi-GB model weights.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:${PATH:-}"

APP_NAME="AYUAKSHU Audio"
DMG_NAME="AYUAKSHU-Audio"

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
  echo "WARN: This MVP packaging path targets Apple Silicon (arm64). Detected: $ARCH"
fi

echo "=== 1) Clean old builds ==="
rm -rf "$ROOT/dist/${APP_NAME}.app" "$ROOT/dist/${DMG_NAME}.dmg"
rm -rf "$ROOT/dist/OfflineVoice.app" "$ROOT/dist/OfflineVoice.dmg"
rm -rf "$ROOT/src-tauri/target/release/bundle" 2>/dev/null || true
mkdir -p "$ROOT/dist"

echo "=== 2) Bundle Python backend ==="
BACKEND_BIN="$ROOT/src-tauri/resources/backend/offlinevoice-backend/offlinevoice-backend"
if [[ "${SKIP_BUNDLE:-0}" == "1" && -x "$BACKEND_BIN" ]]; then
  echo "SKIP_BUNDLE=1 — reusing existing backend at $BACKEND_BIN"
else
  chmod +x "$ROOT/scripts/bundle_backend.sh"
  "$ROOT/scripts/bundle_backend.sh"
fi

if [[ ! -x "$BACKEND_BIN" ]]; then
  echo "ERROR: backend bundle missing" >&2
  exit 1
fi

echo "=== 3) Validate model paths policy ==="
if [[ -d "$ROOT/src-tauri/resources/backend/offlinevoice-backend" ]]; then
  if find "$ROOT/src-tauri/resources/backend" -name 't3_mtl*.safetensors' | grep -q .; then
    echo "ERROR: model weights were accidentally included in the app bundle" >&2
    exit 1
  fi
fi
echo "OK: no chatterbox weight files inside app resources"

echo "=== 4) Build frontend + Tauri (aarch64-apple-darwin) ==="
export CARGO_TARGET_DIR="$ROOT/src-tauri/target"
npm --prefix frontend run build
npm run tauri build -- --target aarch64-apple-darwin

BUNDLE_DIR="$CARGO_TARGET_DIR/aarch64-apple-darwin/release/bundle"
if [[ ! -d "$BUNDLE_DIR/macos" && -d "$CARGO_TARGET_DIR/release/bundle/macos" ]]; then
  BUNDLE_DIR="$CARGO_TARGET_DIR/release/bundle"
fi

APP_SRC="$(find "$BUNDLE_DIR" -maxdepth 3 -name "${APP_NAME}.app" -print -quit || true)"
if [[ -z "$APP_SRC" ]]; then
  # Fallback: any .app Tauri produced
  APP_SRC="$(find "$BUNDLE_DIR" -maxdepth 3 -name '*.app' -print -quit || true)"
fi

if [[ -z "$APP_SRC" ]]; then
  echo "ERROR: ${APP_NAME}.app not found under $BUNDLE_DIR" >&2
  ls -laR "$BUNDLE_DIR" 2>/dev/null || true
  exit 1
fi

echo "=== 5) Copy app + create DMG ==="
rm -rf "$ROOT/dist/${APP_NAME}.app" "$ROOT/dist/${DMG_NAME}.dmg"
cp -R "$APP_SRC" "$ROOT/dist/${APP_NAME}.app"

if find "$ROOT/dist/${APP_NAME}.app" -name 't3_mtl*.safetensors' | grep -q .; then
  echo "ERROR: model weights found inside ${APP_NAME}.app" >&2
  exit 1
fi

STAGE="$ROOT/dist/dmg_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$ROOT/dist/${APP_NAME}.app" "$STAGE/"
ln -sf /Applications "$STAGE/Applications"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  "$ROOT/dist/${DMG_NAME}.dmg"
rm -rf "$STAGE"

echo "=== 6) Optional signing ==="
if [[ -n "${OFFLINEVOICE_SIGN_IDENTITY:-}" ]]; then
  "$ROOT/scripts/sign_mac.sh" "$ROOT/dist/${APP_NAME}.app" || true
  if [[ -f "$ROOT/dist/${DMG_NAME}.dmg" ]]; then
    "$ROOT/scripts/sign_mac.sh" "$ROOT/dist/${DMG_NAME}.dmg" || true
  fi
else
  echo "Skipping codesign (set OFFLINEVOICE_SIGN_IDENTITY to enable)"
fi

echo "=== 7) Optional notarization ==="
if [[ -n "${OFFLINEVOICE_NOTARY_PROFILE:-}" && -f "$ROOT/dist/${DMG_NAME}.dmg" ]]; then
  "$ROOT/scripts/notarize_mac.sh" "$ROOT/dist/${DMG_NAME}.dmg" || true
else
  echo "Skipping notarization (set OFFLINEVOICE_NOTARY_PROFILE to enable)"
fi

echo
echo "=== Build complete ==="
echo "App:  $ROOT/dist/${APP_NAME}.app"
echo "DMG:  $ROOT/dist/${DMG_NAME}.dmg"
ls -lah "$ROOT/dist/${APP_NAME}.app" "$ROOT/dist/${DMG_NAME}.dmg" 2>/dev/null || true
du -sh "$ROOT/dist/${APP_NAME}.app" "$ROOT/dist/${DMG_NAME}.dmg" 2>/dev/null || true
echo
echo "Models are NOT inside the DMG. They install to:"
echo "  ~/Library/Application Support/AYUAKSHU Audio/models/"
echo "Package: dist/OfflineVoice-Models/"
