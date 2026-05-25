#!/usr/bin/env bash
# Live HTTP smoke test (email + password). Usage: ./scripts/smoke_check.sh <base_url>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <base_url>"
  echo "Example: $0 http://127.0.0.1:5001"
  echo "Reads SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD from .env"
  exit 1
fi

exec "$ROOT/.venv/bin/python" "$ROOT/scripts/smoke_journey.py" "$1"
