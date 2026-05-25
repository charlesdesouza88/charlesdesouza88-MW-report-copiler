#!/usr/bin/env python3
"""Quick live smoke test — email/password login. Usage: ./scripts/smoke_journey.py [base_url]"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as web_app  # noqa: E402


def _load_dotenv():
    env_path = ROOT / '.env'
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    _load_dotenv()
    base = (sys.argv[1] if len(sys.argv) > 1 else '').rstrip('/')
    email = os.environ.get('SUPERADMIN_EMAIL', '').strip()
    password = os.environ.get('SUPERADMIN_PASSWORD') or os.environ.get('ADMIN_PASSWORD', '')

    if not email or not password:
        print('FAIL: set SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD in .env')
        sys.exit(1)

    if base:
        import urllib.error
        import urllib.parse
        import http.cookiejar

        jar = http.cookiejar.CookieJar()
        from urllib.request import HTTPCookieProcessor, Request, build_opener

        opener = build_opener(HTTPCookieProcessor(jar))
        data = urllib.parse.urlencode({'email': email, 'password': password}).encode()
        req = Request(f'{base}/login', data=data, method='POST')
        try:
            resp = opener.open(req)
        except urllib.error.HTTPError as exc:
            resp = exc
        code = getattr(resp, 'status', resp.code)
        print(f'[live] login -> {code}')
        if code not in (200, 302):
            sys.exit(1)
        for path in ('/', '/students', '/upload', '/admin/teachers', '/reports'):
            r = opener.open(f'{base}{path}')
            print(f'[live] GET {path} -> {r.status}')
        print(f'PASS: live smoke OK for {base}')
        return

    client = web_app.app.test_client()
    steps = []

    r = client.post('/login', data={'email': email, 'password': password})
    steps.append(('login', r.status_code == 302))
    for path in ('/', '/students', '/upload', '/admin/teachers', '/reports'):
        r = client.get(path)
        steps.append((path, r.status_code == 200))

    failed = [name for name, ok in steps if not ok]
    for name, ok in steps:
        print(f'  {"OK" if ok else "FAIL"}  {name}')

    if failed:
        print(f'FAIL: {", ".join(failed)}')
        sys.exit(1)
    print('PASS: local journey smoke (in-process)')


if __name__ == '__main__':
    main()
