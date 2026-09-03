#!/usr/bin/env bash
# Codesign AYUAKSHU Audio.app / .dmg when a Developer ID is configured.
# Credentials must come from env/keychain — never commit secrets.
#
# Developer ID (distribution):
#   export OFFLINEVOICE_SIGN_IDENTITY='Developer ID Application: Your Name (TEAMID)'
#   ./scripts/sign_mac.sh "dist/AYUAKSHU Audio.app"
#
# Ad-hoc local sign (no Apple Developer account — removes some Gatekeeper friction locally):
#   ./scripts/sign_mac.sh "dist/AYUAKSHU Audio.app" --adhoc
set -euo pipefail

TARGET="${1:-}"
MODE="${2:-}"
if [[ -z "$TARGET" ]]; then
  echo "Usage: $0 /path/to/AYUAKSHU\\ Audio.app|.dmg [--adhoc]" >&2
  exit 1
fi

ENTITLEMENTS="$(cd "$(dirname "$0")/.." && pwd)/installer/entitlements.plist"

if [[ "$MODE" == "--adhoc" || "${OFFLINEVOICE_SIGN_IDENTITY:-}" == "-" ]]; then
  IDENTITY="-"
  echo "Ad-hoc signing (local only; not notarizable)"
else
  IDENTITY="${OFFLINEVOICE_SIGN_IDENTITY:-}"
  if [[ -z "$IDENTITY" ]]; then
    echo "ERROR: set OFFLINEVOICE_SIGN_IDENTITY, e.g." >&2
    echo "  export OFFLINEVOICE_SIGN_IDENTITY='Developer ID Application: Your Name (TEAMID)'" >&2
    echo "Or pass --adhoc for local unsigned-machine testing." >&2
    exit 1
  fi
fi

ARGS=(--force --sign "$IDENTITY")
if [[ "$IDENTITY" != "-" ]]; then
  ARGS+=(--timestamp --options runtime)
  if [[ -f "$ENTITLEMENTS" ]]; then
    ARGS+=(--entitlements "$ENTITLEMENTS")
  fi
fi

if [[ "$TARGET" == *.app || -d "$TARGET" ]]; then
  echo "Signing app bundle: $TARGET"
  # Sign nested Mach-O first for hardened runtime when using Developer ID.
  if [[ "$IDENTITY" != "-" ]]; then
    find "$TARGET/Contents" -type f \( -name '*.dylib' -o -name '*.so' -o -perm +111 \) 2>/dev/null \
      | while read -r bin; do
          file "$bin" 2>/dev/null | grep -q 'Mach-O' || continue
          codesign --force --timestamp --options runtime --sign "$IDENTITY" \
            ${ENTITLEMENTS:+--entitlements "$ENTITLEMENTS"} "$bin" 2>/dev/null || true
        done
  fi
  codesign "${ARGS[@]}" --deep "$TARGET"
  codesign --verify --deep --strict --verbose=2 "$TARGET" || true
else
  echo "Signing file: $TARGET"
  codesign "${ARGS[@]}" "$TARGET"
  codesign --verify --verbose=2 "$TARGET" || true
fi

echo "Signed: $TARGET"
