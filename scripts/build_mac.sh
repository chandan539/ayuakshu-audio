#!/usr/bin/env bash
# Convenience wrapper used by docs / CI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/build_dmg.sh"
