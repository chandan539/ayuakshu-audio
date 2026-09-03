#!/usr/bin/env bash
# PHASE 7 — Static network / telemetry audit of OfflineVoice sources.
# Flags suspicious patterns; not every hit is a runtime cloud call.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REPORT="$ROOT/outputs/phase7_network_audit.txt"
mkdir -p "$ROOT/outputs"

# Scope: runtime app sources only (exclude venvs, node_modules, dist, audit script itself)
PATHS=(
  backend/app
  backend/scripts
  frontend/src
  src-tauri/src
)

echo "OfflineVoice network audit — $(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$REPORT"
echo "Scoped to: ${PATHS[*]}" >>"$REPORT"
echo >>"$REPORT"

PATTERNS=(
  'https?://'
  '\brequests\b'
  '\burllib\b'
  '\bhttpx\b'
  '\baiohttp\b'
  '\bcurl\b'
  '\bwget\b'
  'telemetry'
  'analytics'
  'tracking'
  'sentry'
  'segment\.io'
  'mixpanel'
  'huggingface\.co'
  'hf\.co'
  'openai\.com'
  'api\.openai'
  'googleapis'
  'auto.?update'
)

HITS=0
for pat in "${PATTERNS[@]}"; do
  echo "### pattern: $pat" >>"$REPORT"
  if command -v rg >/dev/null 2>&1; then
    matches="$(rg -n -i --no-heading -e "$pat" "${PATHS[@]}" 2>/dev/null || true)"
  else
    matches="$(grep -RInE -e "$pat" "${PATHS[@]}" 2>/dev/null || true)"
  fi
  if [[ -n "$matches" ]]; then
    echo "$matches" >>"$REPORT"
    count="$(printf '%s\n' "$matches" | wc -l | tr -d ' ')"
    HITS=$((HITS + count))
    echo "  found $count line(s) for /$pat/"
  else
    echo "(none)" >>"$REPORT"
  fi
  echo >>"$REPORT"
done

# Hard fail only on real cloud SDK / endpoint markers (not privacy copy saying "no telemetry")
CRITICAL=0
CRITICAL_PATTERNS=(
  'api\.openai\.com'
  'openai\.com/v1'
  'sentry\.io'
  '@sentry/'
  'segment\.io'
  'mixpanel\.com'
  'mixpanel\.track'
  'google-analytics\.com'
  'googletagmanager\.com'
  'amplitude\.com'
)

echo "## Critical scan" >>"$REPORT"
for pat in "${CRITICAL_PATTERNS[@]}"; do
  if command -v rg >/dev/null 2>&1; then
    hits="$(rg -n -i -e "$pat" backend/app frontend/src src-tauri/src 2>/dev/null || true)"
  else
    hits="$(grep -RInE -e "$pat" backend/app frontend/src src-tauri/src 2>/dev/null || true)"
  fi
  if [[ -n "$hits" ]]; then
    echo "CRITICAL: matched /$pat/" | tee -a "$REPORT"
    echo "$hits" >>"$REPORT"
    CRITICAL=$((CRITICAL + 1))
  fi
done

# Privacy page should affirm no telemetry (soft check)
if command -v rg >/dev/null 2>&1; then
  if rg -n -i 'No analytics / telemetry' frontend/src/pages/PrivacyPage.tsx >/dev/null 2>&1; then
    echo "OK: Privacy page documents no analytics/telemetry" | tee -a "$REPORT"
  fi
fi

cat >>"$REPORT" <<'EOF'

## Review notes (expected)

- Offline flags HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE are intentional.
- Model *installer* scripts may mention huggingface.co / snapshot_download for first-run only.
- huggingface_hub is patched in chatterbox_engine for local offline loads.
- FastAPI/httpx in tests talk to 127.0.0.1 only.
- Privacy UI may contain the words "telemetry" / "analytics" to state they are absent — not a SDK.

## Verdict policy

- CRITICAL cloud TTS / telemetry SDK/endpoint strings in runtime app sources => FAIL
- Installer / docs / privacy copy mentioning HF or "no telemetry" => OK
EOF

echo
echo "Audit report: $REPORT"
echo "Informational hits: $HITS"
echo "Critical hits: $CRITICAL"

if (( CRITICAL > 0 )); then
  exit 1
fi
echo "PASS: network audit (no critical cloud/telemetry markers in app runtime sources)"
