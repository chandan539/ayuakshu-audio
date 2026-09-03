#!/usr/bin/env bash
# Notarize and staple a DMG using notarytool.
# Requires a keychain profile created ahead of time, e.g.:
#   xcrun notarytool store-credentials "offlinevoice-notary" \
#     --apple-id "you@example.com" --team-id "TEAMID" --password "@keychain:AC_PASSWORD"
set -euo pipefail

DMG="${1:-}"
if [[ -z "$DMG" || ! -f "$DMG" ]]; then
  echo "Usage: $0 /path/to/OfflineVoice.dmg" >&2
  exit 1
fi

PROFILE="${OFFLINEVOICE_NOTARY_PROFILE:-}"
if [[ -z "$PROFILE" ]]; then
  echo "ERROR: set OFFLINEVOICE_NOTARY_PROFILE to your notarytool keychain profile name" >&2
  exit 1
fi

echo "Submitting $DMG for notarization (profile=$PROFILE)…"
xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait
echo "Stapling…"
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"
echo "Notarized + stapled: $DMG"
