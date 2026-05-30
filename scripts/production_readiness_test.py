#!/usr/bin/env python3
"""Full production-readiness check: pytest + admin + teacher journeys + visibility.

Usage:
  .venv/bin/python scripts/production_readiness_test.py
  .venv/bin/python scripts/production_readiness_test.py --live http://127.0.0.1:5001
  .venv/bin/python scripts/production_readiness_test.py --live https://....railway.app
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as web_app  # noqa: E402
from auth import UserStore  # noqa: E402
from teacher_classes import save_registry  # noqa: E402

STUDENTS_CSV = (
    'teacher,turma,turma_display,nivel,horario,student_name,participacao,comportamento,'
    'speaking,listening,foco,writing,reading,gramatica,trabalho_equipe,organizacao,'
    'pontualidade,respeito_regras,faltas,missed_aulas,aula_extra,feedback_participacao,'
    'feedback_foco,feedback_trabalho_equipe,recomendacoes,observacao\n'
    'Chuck,MASTER,Masters,KIDS 1,Tue 19:00,Jane Doe,4,3,4,5,4,3,4,2,3,3,3,3,1,2,'
    'Reposicao,Good,Focus,Team,Practice speaking,\n'
    'Ana,SPARK,Spark,KIDS 2,Mon 10:00,Bob Smith,3,3,3,3,3,3,3,3,3,3,3,3,0,,,'
    ',,,,\n'
)

LESSONS_CSV = (
    'turma,aula_num,date,licao_conteudo,atividade_extra,habilidades\n'
    'MASTER,1,01/02/2026,Lesson 1,,\n'
    'SPARK,1,05/02/2026,Spark lesson,,\n'
)


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


class Runner:
    def __init__(self, label: str):
        self.label = label
        self.failures: list[str] = []

    def ok(self, name: str, cond: bool, detail: str = ''):
        mark = 'OK' if cond else 'FAIL'
        extra = f' — {detail}' if detail else ''
        print(f'  [{mark}] {name}{extra}')
        if not cond:
            self.failures.append(f'{name}{extra}')

    def done(self) -> int:
        if self.failures:
            print(f'\n✗ {self.label}: {len(self.failures)} failure(s)')
            for f in self.failures:
                print(f'    {f}')
            return 1
        print(f'\n✓ {self.label}: all checks passed')
        return 0


def _scores():
    return {f: '3' for f in (
        'participacao', 'comportamento', 'speaking', 'listening', 'foco',
        'writing', 'reading', 'gramatica', 'trabalho_equipe', 'organizacao',
        'pontualidade', 'respeito_regras',
    )}


def _pin_test_superadmin(admin_email: str, admin_password: str):
    """Keep in-process journeys off developer .env (app.py caches env at import)."""
    os.environ['SUPERADMIN_EMAIL'] = admin_email
    os.environ['SUPERADMIN_PASSWORD'] = admin_password
    os.environ['SUPERADMIN_SYNC_PASSWORD'] = ''
    web_app.SUPERADMIN_EMAIL = admin_email
    web_app.SUPERADMIN_PASSWORD = admin_password
    web_app.SUPERADMIN_SYNC_PASSWORD = False


def _setup_env(tmp: Path, admin_email: str = 'admin@test.local', admin_password: str = 'testpass'):
    """Isolated CSV mode with fixed test accounts (ignores developer .env email)."""
    _pin_test_superadmin(admin_email, admin_password)

    data_dir = tmp / 'data'
    out_dir = tmp / 'output'
    data_dir.mkdir()
    out_dir.mkdir()
    (data_dir / 'students.csv').write_text(STUDENTS_CSV, encoding='utf-8')
    (data_dir / 'lessons.csv').write_text(LESSONS_CSV, encoding='utf-8')

    store = UserStore(db_store=None, json_path=data_dir / 'users.json')
    store.initialize()
    store.ensure_bootstrap_superadmin(admin_email, admin_password)
    store.create_teacher('teacher@test.local', 'teachpass', 'Chuck')

    web_app.DATA_DIR = data_dir
    web_app.OUT_DIR = out_dir
    web_app.SNAPSHOTS_PATH = data_dir / 'student_snapshots.json'
    web_app.TEACHER_CLASSES_PATH = data_dir / 'teacher_classes.json'
    save_registry(web_app.TEACHER_CLASSES_PATH, {
        'Chuck': [{
            'turma': 'MASTER',
            'turma_display': 'Masters',
            'class_weekdays': ['Terça-feira', 'Quinta-feira'],
            'class_time_start': '19:00',
            'class_time_end': '20:00',
            'horario': 'Terça-feira e Quinta-feira 19:00 - 20:00',
        }],
    })
    web_app.db_store = None
    web_app.DB_ENABLED = False
    web_app.user_store = store
    return data_dir, out_dir, store


def run_pytest() -> int:
    print('\n=== Unit & integration tests (pytest) ===')
    proc = subprocess.run(
        [str(ROOT / '.venv/bin/python'), '-m', 'pytest', '-q', '--tb=line'],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if proc.returncode != 0:
        print('FAIL: pytest')
        return proc.returncode
    print('OK: pytest')
    return 0


def journey_admin(client, runner: Runner, out_dir: Path | None = None):
    print('\n=== Admin user journey ===')
    r = client.post('/login', data={'email': 'admin@test.local', 'password': 'testpass'})
    runner.ok('Admin login', r.status_code == 302)

    pages = {
        '/': ('Dashboard', 'Gerar'),
        '/students': ('Students', 'Jane Doe'),
        '/lessons': ('Lessons', 'MASTER'),
        '/upload': ('Upload', 'CSV'),
        '/reports': ('Reports', 'Relatório'),
        '/extra-sessions': ('Extra sessions', 'Atendimentos'),
        '/admin/teachers': ('Teachers admin', 'Professor'),
    }
    for path, (label, token) in pages.items():
        html = client.get(path).get_data(as_text=True)
        runner.ok(f'Admin {label}', token in html or 'relatório' in html.lower())

    html = client.get('/students/new').get_data(as_text=True)
    runner.ok('Admin new student form', 'Novo aluno' in html and 'KIDS 1' in html)

    r = client.post(
        '/students/new',
        data={
            'teacher': 'Chuck',
            'turma': 'ADMIN_TEST',
            'student_name': 'Admin Created',
            'nivel': 'TEENS 1',
            **_scores(),
            'faltas': '0',
        },
        follow_redirects=False,
    )
    runner.ok('Admin create student', r.status_code == 302)
    runner.ok('Admin student saved', 'Admin Created' in client.get('/students').get_data(as_text=True))

    r = client.post('/generate', follow_redirects=False)
    loc = r.headers.get('Location', '')
    runner.ok('Admin generate', r.status_code == 302 and '/reports' in loc)
    reports_dir = out_dir or web_app.OUT_DIR
    n_files = len(list(reports_dir.glob('*.html')))
    runner.ok('Report files written', n_files >= 2, f'{n_files} files')

    rep = client.get(loc)
    rep_html = rep.get_data(as_text=True)
    runner.ok('Reports list OK', rep.status_code == 200)
    runner.ok('Month filter UI', 'Filtrar por mês' in rep_html or 'Relatório' in rep_html)


def journey_teacher(client, runner: Runner):
    print('\n=== Teacher user journey & visibility ===')
    client.post('/logout')
    r = client.post('/login', data={'email': 'teacher@test.local', 'password': 'teachpass'})
    runner.ok('Teacher login', r.status_code == 302)

    students_html = client.get('/students').get_data(as_text=True)
    runner.ok('Teacher sees own student', 'Jane Doe' in students_html)
    runner.ok('Teacher hides other teacher', 'Bob Smith' not in students_html)

    admin_resp = client.get('/admin/teachers')
    runner.ok('Teacher blocked from admin', admin_resp.status_code == 403)

    dash_html = client.get('/').get_data(as_text=True)
    runner.ok('Teacher dashboard create turma', 'Criar turma' in dash_html)

    r = client.post(
        '/turmas/create',
        data={
            'turma_display': 'Teens class',
            'class_weekday_1': 'Terça-feira',
            'class_weekday_2': 'Quinta-feira',
            'turma_time_start': '18:00',
            'turma_time_end': '19:00',
        },
        follow_redirects=False,
    )
    runner.ok('Teacher create turma on dashboard', r.status_code == 302)

    form_html = client.get('/students/new').get_data(as_text=True)
    runner.ok('Teacher student turma dropdown', 'TEENS_CLASS' in form_html and 'Teens class' in form_html)

    r = client.post(
        '/students/new',
        data={
            'teacher': 'Chuck',
            'class_choice': 'TEENS_CLASS',
            'nivel': 'TEENS 3',
            'student_name': 'Teacher New Class Kid',
            **_scores(),
            'faltas': '0',
        },
        follow_redirects=False,
    )
    runner.ok('Teacher add student to turma', r.status_code == 302)
    csv = (web_app.DATA_DIR / 'students.csv').read_text(encoding='utf-8')
    runner.ok('Student in TEENS_CLASS', 'TEENS_CLASS' in csv and 'Teacher New Class Kid' in csv)

    r = client.post(
        '/students/new',
        data={
            'teacher': 'Chuck',
            'turma': 'SPARK',
            'student_name': 'Sneaky Bob',
            **_scores(),
            'faltas': '0',
        },
    )
    sneaky_html = r.get_data(as_text=True)
    runner.ok(
        'Teacher cannot use Ana turma',
        'Sneaky Bob' not in csv and ('não permitida' in sneaky_html or 'Dashboard' in sneaky_html),
    )


def run_inprocess() -> int:
    code = run_pytest()
    if code:
        return code

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _setup_env(tmp_path)
        client = web_app.app.test_client()

        admin_runner = Runner('Admin journey')
        journey_admin(client, admin_runner, web_app.OUT_DIR)
        code = admin_runner.done()

        teacher_runner = Runner('Teacher journey & visibility')
        journey_teacher(client, teacher_runner)
        code = code or teacher_runner.done()

    return code


def run_live(base: str) -> int:
    import http.cookiejar
    import urllib.error
    import urllib.parse
    from urllib.request import HTTPCookieProcessor, Request, build_opener

    env_path = ROOT / '.env'
    creds = {}
    if env_path.exists():
        for raw in env_path.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                creds[k.strip()] = v.strip().strip('"').strip("'")

    email = creds.get('SUPERADMIN_EMAIL', '')
    password = creds.get('SUPERADMIN_PASSWORD') or creds.get('ADMIN_PASSWORD', '')
    if not email or not password:
        print('SKIP live: no credentials in .env')
        return 0

    base = base.rstrip('/')
    runner = Runner(f'Live smoke ({base})')
    jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    no_redir = build_opener(HTTPCookieProcessor(jar), NoRedirect())

    def get(path):
        return opener.open(f'{base}{path}', timeout=60)

    def post(path, data, redir=True):
        req = Request(f'{base}{path}', urllib.parse.urlencode(data).encode(), method='POST')
        http = opener if redir else no_redir
        return http.open(req, timeout=120)

    print(f'\n=== Live checks ({base}) ===')
    try:
        r = opener.open(f'{base}/health', timeout=15)
        runner.ok('/health', r.read().decode().strip() == 'ok')
    except Exception as exc:
        runner.ok('/health', False, str(exc))

    try:
        db = get('/health/db')
        body = db.read().decode()
        runner.ok('/health/db', '"connected": true' in body or '"connected":true' in body, body[:80])
    except Exception as exc:
        runner.ok('/health/db', False, str(exc))

    post('/login', {'email': email, 'password': password})
    for path, label in [
        ('/', 'Dashboard'),
        ('/students', 'Students'),
        ('/lessons', 'Lessons'),
        ('/upload', 'Upload'),
        ('/reports', 'Reports'),
        ('/extra-sessions', 'Extra sessions'),
        ('/students/new', 'New student'),
    ]:
        try:
            html = get(path).read().decode('utf-8', errors='replace')
            is_login = 'Entrar' in html and 'drawer' not in html
            runner.ok(label, not is_login and len(html) > 1000, f'len={len(html)}')
        except Exception as exc:
            runner.ok(label, False, str(exc))

    try:
        post('/login', {'email': email, 'password': password})
        post('/generate', {'report_month': ''}, redir=False)
        gen_ok = False
    except urllib.error.HTTPError as e:
        gen_ok = e.code in (302, 303) and '/reports' in (e.headers.get('Location') or '')
    runner.ok('Generate reports', gen_ok)

    return runner.done()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', metavar='URL', help='Also run live HTTP checks against URL')
    parser.add_argument('--skip-pytest', action='store_true')
    args = parser.parse_args()

    print('Mister Wiz — production readiness check')
    code = 0
    if not args.skip_pytest:
        code = run_inprocess()
    else:
        with tempfile.TemporaryDirectory() as tmp:
            _setup_env(Path(tmp), 'admin@test.local', 'testpass')
            client = web_app.app.test_client()
            ar = Runner('Admin')
            journey_admin(client, ar, web_app.OUT_DIR)
            tr = Runner('Teacher')
            journey_teacher(client, tr)
            code = ar.done() or tr.done()

    if args.live:
        code = code or run_live(args.live)

    if code == 0:
        print('\n══════════════════════════════════════')
        print('  READY: all production readiness checks passed')
        print('══════════════════════════════════════')
    else:
        print('\n══════════════════════════════════════')
        print('  NOT READY: fix failures above before deploy')
        print('══════════════════════════════════════')
    return code


if __name__ == '__main__':
    sys.exit(main())
