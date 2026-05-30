#!/usr/bin/env bash
# Start local dev server with checks. Usage: ./scripts/dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
fi

echo "Installing dependencies..."
.venv/bin/pip install -q -r requirements-dev.txt

echo ""
echo "Running tests..."
.venv/bin/python -m pytest -q --tb=line

echo ""
.venv/bin/python - <<PY
import os
from pathlib import Path

base = Path("${ROOT}")
env_path = base / '.env'
if env_path.exists():
    for raw in env_path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

email = os.environ.get('SUPERADMIN_EMAIL', 'admin@misterwiz.local')
has_pw = bool(os.environ.get('SUPERADMIN_PASSWORD') or os.environ.get('ADMIN_PASSWORD'))
users = base / 'data' / 'users.json'
accounts = 'configured' if users.exists() and users.read_text().strip() not in ('', '[]') else 'will bootstrap on start'

print('── Local login ─────────────────────────────')
print(f'  E-mail:  {email}')
print(f'  Senha:   value of SUPERADMIN_PASSWORD in .env')
print(f'  Contas:  {accounts}')
if not has_pw:
    print('  WARNING: SUPERADMIN_PASSWORD is empty in .env — login will fail.')
print('────────────────────────────────────────────')
PY

export FLASK_DEBUG="${FLASK_DEBUG:-1}"
echo ""
echo "Starting Flask (auto-picks port if 5000 is busy — common on macOS)..."
echo "Press Ctrl+C to stop."
echo ""

exec .venv/bin/python app.py
