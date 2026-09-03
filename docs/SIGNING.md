# Apple signing & notarization (AYUAKSHU Audio)

## Status on this Mac

`security find-identity -v -p codesigning` currently reports **0 valid identities**.
Full Gatekeeper distribution (Developer ID + notarization) needs an Apple Developer
Program certificate. Until then we ship an **ad-hoc signed** local build.

## Local / internal builds (no Apple Developer account)

```bash
export PATH="$HOME/.cargo/bin:$HOME/.local/node/bin:$PATH"
SKIP_BUNDLE=0 ./scripts/build_dmg.sh   # or SKIP_BUNDLE=1 if backend already bundled
./scripts/sign_mac.sh "dist/AYUAKSHU Audio.app" --adhoc
```

First open may still need: **Right-click → Open** (or System Settings → Privacy & Security).

## Distribution builds (Developer ID)

1. Install **Developer ID Application** certificate in Keychain.
2. Create a notarytool profile once:

```bash
xcrun notarytool store-credentials "ayuakshu-notary" \
  --apple-id "you@example.com" \
  --team-id "TEAMID" \
  --password "@keychain:AC_PASSWORD"
```

3. Sign + notarize:

```bash
export OFFLINEVOICE_SIGN_IDENTITY='Developer ID Application: Your Name (TEAMID)'
export OFFLINEVOICE_NOTARY_PROFILE='ayuakshu-notary'
./scripts/build_dmg.sh
./scripts/sign_mac.sh "dist/AYUAKSHU Audio.app"
./scripts/sign_mac.sh dist/AYUAKSHU-Audio.dmg
./scripts/notarize_mac.sh dist/AYUAKSHU-Audio.dmg
```

`build_dmg.sh` also runs these automatically when the env vars are set.
