#!/usr/bin/env python3
"""Mister Wiz Report Compiler — Web Dashboard"""

import csv
import functools
import io
import json
import logging
import os
import time
import zipfile
from pathlib import Path

from flask import (Flask, abort, redirect, render_template, request,
                   send_file, session, url_for)
from jinja2 import Environment, FileSystemLoader

from compiler import (generate_class_diagnostics, generate_individual_reports,
                      group_by_turma, load_csv)

from auth import (ROLE_ADMIN, ROLE_LABELS, ROLE_SUPERADMIN, ROLE_TEACHER,
                  UserStore, can_manage_teachers, filter_lessons_for_user,
                  filter_reports_for_user, filter_students_for_user,
                  find_student_global_index, has_full_data_access,
                  normalize_teacher_name, user_public_dict)

try:
    from db_store import DatabaseStore
except Exception as exc:
    DatabaseStore = None
    DB_IMPORT_ERROR = exc
else:
    DB_IMPORT_ERROR = None

BASE = Path(__file__).parent


def _ensure_writable_dir(path, fallback):
    candidate = Path(path)
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / '.mw_write_probe'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
        return candidate
    except OSError:
        backup = Path(fallback)
        backup.mkdir(parents=True, exist_ok=True)
        return backup


def _load_local_env():
    env_path = BASE / '.env'
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if not DATABASE_URL:
    DATABASE_URL = os.environ.get('DATABASE_PRIVATE_URL', '').strip()
DB_ENABLED = bool(DATABASE_URL) and DatabaseStore is not None
db_store = None
DB_STARTUP_ERROR = None
if DB_ENABLED:
    last_exc = None
    for attempt in range(1, 4):
        try:
            db_store = DatabaseStore(DATABASE_URL)
            db_store.initialize()
            last_exc = None
            logger.info('Database connected on attempt %s', attempt)
            break
        except Exception as exc:
            last_exc = exc
            logger.warning('Database startup attempt %s failed: %s', attempt, exc)
            if attempt < 3:
                time.sleep(2)
    if last_exc is not None:
        logger.exception('Database startup failed; falling back to CSV mode')
        db_store = None
        DB_ENABLED = False
        DB_STARTUP_ERROR = str(last_exc)
elif DATABASE_URL and DB_IMPORT_ERROR is not None:
    logger.error('DATABASE_URL is set but database dependencies failed to import: %s', DB_IMPORT_ERROR)
    DB_STARTUP_ERROR = f'Database dependencies failed to import: {DB_IMPORT_ERROR}'


def _database_status():
    """Return connection diagnostics for /health/db and the dashboard."""
    if not DATABASE_URL:
        return {
            'configured': False,
            'connected': False,
            'mode': 'csv',
            'message': 'DATABASE_URL not set — using CSV files.',
        }
    if db_store is None:
        return {
            'configured': True,
            'connected': False,
            'mode': 'csv-fallback',
            'message': DB_STARTUP_ERROR or 'Database unavailable; using CSV fallback.',
        }
    try:
        db_store.check_connection()
        students = db_store.load_students()
        lessons = db_store.load_lessons()
        return {
            'configured': True,
            'connected': True,
            'mode': 'postgresql',
            'message': 'Connected to PostgreSQL.',
            'student_rows': len(students),
            'lesson_rows': len(lessons),
        }
    except Exception as exc:
        logger.exception('Database health check failed: %s', exc)
        return {
            'configured': True,
            'connected': False,
            'mode': 'postgresql',
            'message': f'Database ping failed: {exc}',
        }


default_data_dir = str(BASE / 'data')
default_out_dir = str(BASE / 'output')

TMPL_DIR = BASE / 'templates'
DATA_DIR = _ensure_writable_dir(
    os.environ.get('DATA_DIR', default_data_dir), '/tmp/mw/data')
OUT_DIR = _ensure_writable_dir(
    os.environ.get('OUT_DIR', default_out_dir), '/tmp/mw/output')

app = Flask(__name__, template_folder='web_templates')
app.secret_key = os.environ.get('SECRET_KEY', 'mw-dev-change-in-prod')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
SUPERADMIN_EMAIL = os.environ.get('SUPERADMIN_EMAIL', 'admin@misterwiz.local').strip()
SUPERADMIN_PASSWORD = os.environ.get('SUPERADMIN_PASSWORD', ADMIN_PASSWORD).strip()

user_store = UserStore(
    db_store=db_store,
    json_path=DATA_DIR / 'users.json',
)
try:
    user_store.initialize()
    user_store.ensure_bootstrap_superadmin(SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)
except Exception as exc:
    logger.exception('User store initialization failed: %s', exc)

STUDENT_FIELDS = [
    'teacher', 'turma', 'turma_display', 'nivel', 'horario', 'student_name',
    'participacao', 'comportamento', 'speaking', 'listening', 'foco',
    'writing', 'reading', 'gramatica', 'trabalho_equipe', 'organizacao',
    'pontualidade', 'respeito_regras', 'faltas', 'missed_aulas', 'aula_extra',
    'feedback_participacao', 'feedback_foco', 'feedback_trabalho_equipe',
    'recomendacoes', 'observacao',
]
SCORE_FIELDS = {
    'participacao', 'comportamento', 'speaking', 'listening', 'foco',
    'writing', 'reading', 'gramatica', 'trabalho_equipe', 'organizacao',
    'pontualidade', 'respeito_regras',
}
LESSON_FIELDS = [
    'turma', 'aula_num', 'date', 'licao_conteudo', 'atividade_extra', 'habilidades'
]

TEMPLATE_DIR = BASE / 'data' / 'templates'

STUDENT_FIELD_LABELS = {
    'teacher': 'Professor',
    'turma': 'Código turma',
    'turma_display': 'Nome exibido',
    'nivel': 'Nível / livro',
    'horario': 'Horário',
    'student_name': 'Nome do aluno',
    'participacao': 'Participação',
    'comportamento': 'Comportamento',
    'speaking': 'Fala',
    'listening': 'Audição',
    'foco': 'Foco',
    'writing': 'Escrita',
    'reading': 'Leitura',
    'gramatica': 'Gramática',
    'trabalho_equipe': 'Trabalho em equipe',
    'organizacao': 'Organização',
    'pontualidade': 'Pontualidade',
    'respeito_regras': 'Respeito às regras',
    'faltas': 'Faltas',
    'missed_aulas': 'Aulas perdidas',
    'aula_extra': 'Aula extra',
    'feedback_participacao': 'Feedback — participação',
    'feedback_foco': 'Feedback — foco',
    'feedback_trabalho_equipe': 'Feedback — equipe',
    'recomendacoes': 'Recomendações',
    'observacao': 'Observação',
}

LESSON_FIELD_LABELS = {
    'turma': 'Código turma',
    'aula_num': 'Nº da aula',
    'date': 'Data',
    'licao_conteudo': 'Conteúdo da lição',
    'atividade_extra': 'Atividade extra',
    'habilidades': 'Habilidades',
}

STUDENT_TEMPLATE_SECTIONS = [
    {'title': 'Identificação', 'fields': ['teacher', 'turma', 'turma_display', 'nivel', 'horario', 'student_name']},
    {'title': 'Notas (1–5)', 'fields': [
        'participacao', 'comportamento', 'speaking', 'listening', 'foco',
        'writing', 'reading', 'gramatica', 'trabalho_equipe', 'organizacao',
        'pontualidade', 'respeito_regras',
    ]},
    {'title': 'Presença', 'fields': ['faltas', 'missed_aulas', 'aula_extra']},
    {'title': 'Textos do relatório', 'fields': [
        'feedback_participacao', 'feedback_foco', 'feedback_trabalho_equipe',
        'recomendacoes', 'observacao',
    ]},
]

TEMPLATE_ROWS = {
    'students': {
        'teacher': 'Chuck',
        'turma': 'MASTER',
        'turma_display': 'Masters',
        'nivel': 'Adults Book 4',
        'horario': 'Terça e quinta, 19:00 - 20:00',
        'student_name': 'Jane Doe',
        'participacao': '4',
        'comportamento': '4',
        'speaking': '4',
        'listening': '5',
        'foco': '4',
        'writing': '3',
        'reading': '4',
        'gramatica': '3',
        'trabalho_equipe': '4',
        'organizacao': '4',
        'pontualidade': '4',
        'respeito_regras': '4',
        'faltas': '1',
        'missed_aulas': '2,5',
        'aula_extra': 'Reforço',
        'feedback_participacao': 'Participa bem em aula e responde quando solicitada.',
        'feedback_foco': 'Mantém foco na maior parte do tempo.',
        'feedback_trabalho_equipe': 'Colabora bem com colegas em atividades em grupo.',
        'recomendacoes': 'Praticar speaking em casa 2x por semana com frases da aula.',
        'observacao': 'Substitua este aluno de exemplo pelos dados reais da turma.',
    },
    'lessons': {
        'turma': 'MASTER',
        'aula_num': '1',
        'date': '10/02/2026',
        'licao_conteudo': 'Lesson 1: Introductions & syllabus',
        'atividade_extra': 'Syllabus / class rules',
        'habilidades': 'Speaking, Listening',
    },
}

LESSON_TEMPLATE_ROWS = [
    TEMPLATE_ROWS['lessons'],
    {
        'turma': 'MASTER',
        'aula_num': '2',
        'date': '12/02/2026',
        'licao_conteudo': 'Lesson 2: Daily routines',
        'atividade_extra': 'Pair work — connection words',
        'habilidades': 'Speaking, Writing',
    },
    {
        'turma': 'MASTER',
        'aula_num': '3',
        'date': '19/02/2026',
        'licao_conteudo': 'Lesson 3: Past tense review',
        'atividade_extra': 'Group presentation',
        'habilidades': 'Grammar, Speaking',
    },
]


def _student_preview_columns():
    columns = []
    for section in STUDENT_TEMPLATE_SECTIONS:
        for field in section['fields']:
            columns.append({
                'field': field,
                'label': STUDENT_FIELD_LABELS.get(field, field),
                'section': section['title'],
            })
    return columns


def _lesson_preview_columns():
    return [
        {'field': field, 'label': LESSON_FIELD_LABELS.get(field, field)}
        for field in LESSON_FIELDS
    ]


def _load_template_rows(name):
    path = TEMPLATE_DIR / f'{name}_template.csv'
    if path.exists():
        return load_csv(path)
    if name == 'students':
        return [TEMPLATE_ROWS['students']]
    return LESSON_TEMPLATE_ROWS


def _build_template_csv(name):
    fields = STUDENT_FIELDS if name == 'students' else LESSON_FIELDS
    rows = _load_template_rows(name)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return '\ufeff' + buf.getvalue()


def _read_csv_text(uploaded_file):
    try:
        return uploaded_file.read().decode('utf-8-sig'), None
    except UnicodeDecodeError:
        return None, 'Arquivo deve estar em UTF-8.'


def _validate_csv(key, text):
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return ['CSV sem cabecalho valido.']

    headers = [h.strip() for h in reader.fieldnames if h is not None]
    required = STUDENT_FIELDS if key == 'students' else LESSON_FIELDS
    missing = [f for f in required if f not in headers]
    if missing:
        return [f'Colunas obrigatorias ausentes: {", ".join(missing)}']

    rows = []
    for raw in reader:
        row = {}
        for k, v in raw.items():
            if k is None:
                continue
            row[k.strip()] = (v or '').strip()
        if any(row.values()):
            rows.append(row)

    if not rows:
        return ['CSV sem linhas de dados.']

    errors = []
    for idx, row in enumerate(rows, start=2):
        if key == 'students':
            if not row.get('turma'):
                errors.append(f'Linha {idx}: turma nao pode estar vazia.')
            if not row.get('student_name'):
                errors.append(f'Linha {idx}: student_name nao pode estar vazio.')

            for field in SCORE_FIELDS:
                val = row.get(field, '')
                if not val:
                    continue
                try:
                    num = int(float(val))
                except ValueError:
                    errors.append(f'Linha {idx}: {field} deve ser numero de 1 a 5.')
                    continue
                if num < 1 or num > 5:
                    errors.append(f'Linha {idx}: {field} deve estar entre 1 e 5.')

            faltas = row.get('faltas', '')
            if faltas:
                try:
                    if int(float(faltas)) < 0:
                        errors.append(f'Linha {idx}: faltas nao pode ser negativo.')
                except ValueError:
                    errors.append(f'Linha {idx}: faltas deve ser numero inteiro.')
        else:
            if not row.get('turma'):
                errors.append(f'Linha {idx}: turma nao pode estar vazia.')
            if not row.get('aula_num'):
                errors.append(f'Linha {idx}: aula_num nao pode estar vazio.')

        if len(errors) >= 10:
            errors.append('Muitos erros encontrados; corrija os primeiros e tente novamente.')
            break

    return errors


def _current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return {
        'id': user_id,
        'email': session.get('email', ''),
        'role': session.get('role', ''),
        'teacher_name': session.get('teacher_name', ''),
    }


def _login_session(user):
    session.clear()
    session['authenticated'] = True
    session['user_id'] = user['id']
    session['email'] = user['email']
    session['role'] = user['role']
    session['teacher_name'] = user.get('teacher_name') or ''


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _current_user():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    def decorator(f):
        @functools.wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            user = _current_user()
            if user['role'] not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def _scoped_students():
    all_students = _load_students()
    user = _current_user()
    if not user:
        return all_students, []
    visible = filter_students_for_user(all_students, user)
    return all_students, visible


def _scoped_lessons(all_students=None):
    all_lessons = _load_lessons()
    user = _current_user()
    if not user:
        return all_lessons, []
    if all_students is None:
        all_students = _load_students()
    visible = filter_lessons_for_user(all_lessons, all_students, user)
    return all_lessons, visible


def _merge_scoped_students(all_students, visible_students):
    """Replace visible rows in full list; used when teachers save edits."""
    if has_full_data_access(_current_user()['role']):
        return visible_students
    merged = list(all_students)
    visible_set = {id(r) for r in visible_students}
    for i, row in enumerate(merged):
        if id(row) in visible_set:
            for v in visible_students:
                if v is row or (
                    v.get('turma') == row.get('turma')
                    and v.get('student_name') == row.get('student_name')
                    and v.get('teacher') == row.get('teacher')
                ):
                    merged[i] = v
                    break
    return merged


@app.context_processor
def inject_auth():
    user = _current_user()
    return {
        'current_user': user,
        'role_labels': ROLE_LABELS,
        'can_manage_teachers': can_manage_teachers(user['role']) if user else False,
    }


def _load_students():
    if db_store:
        return db_store.load_students()
    path = DATA_DIR / 'students.csv'
    return load_csv(path) if path.exists() else []


def _load_lessons():
    if db_store:
        return db_store.load_lessons()
    path = DATA_DIR / 'lessons.csv'
    return load_csv(path) if path.exists() else []


def _save_students(students):
    if db_store:
        db_store.save_students(students)
        return
    with open(DATA_DIR / 'students.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=STUDENT_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(students)


def _save_lessons(lessons):
    if db_store:
        db_store.save_lessons(lessons)
        return
    with open(DATA_DIR / 'lessons.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=LESSON_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(lessons)


def _csv_rows_from_text(text):
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw in reader:
        row = {}
        for k, v in raw.items():
            if k is None:
                continue
            row[k.strip()] = (v or '').strip()
        if any(row.values()):
            rows.append(row)
    return rows


# ── Auth ─────────────────────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    """Railway healthcheck — no auth, always 200 when the app is up."""
    return 'ok', 200


@app.route('/health/db')
def health_db():
    """Database connectivity check (JSON). No auth — for Railway / ops."""
    status = _database_status()
    code = 200 if status.get('connected') or not status.get('configured') else 503
    return json.dumps(status, ensure_ascii=False), code, {'Content-Type': 'application/json'}


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        user = user_store.authenticate(email, password)
        if user:
            _login_session(user)
            return redirect(url_for('dashboard'))
        error = 'E-mail ou senha incorretos.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Dashboard ─────────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    all_students, students = _scoped_students()
    _, lessons = _scoped_lessons(all_students)
    reports = filter_reports_for_user(sorted(OUT_DIR.glob('*.html')), all_students, _current_user())
    turmas = group_by_turma(students) if students else {}
    individual = [f for f in reports if 'class_diagnostic' not in f.name]
    if db_store:
        data_ready = bool(students) and bool(lessons)
    else:
        lessons_path = DATA_DIR / 'lessons.csv'
        data_ready = (DATA_DIR / 'students.csv').exists() and lessons_path.exists()
    db_status = _database_status()
    return render_template('dashboard.html',
        student_count=len(students),
        turma_count=len(turmas),
        lesson_count=len(lessons),
        report_count=len(individual),
        turmas=list(turmas.keys()),
        data_ready=data_ready,
        db_status=db_status,
    )


# ── Students ──────────────────────────────────────────────────────────────────────────

@app.route('/students')
@login_required
def students():
    _, rows = _scoped_students()
    turmas = sorted(set(r['turma'] for r in rows))
    return render_template('students.html', students=rows, turmas=turmas)


@app.route('/students/<int:idx>/edit', methods=['GET', 'POST'])
@login_required
def student_edit(idx):
    all_rows, visible = _scoped_students()
    if idx < 0 or idx >= len(visible):
        abort(404)
    user = _current_user()
    if request.method == 'POST':
        for field in STUDENT_FIELDS:
            visible[idx][field] = request.form.get(field, '')
        if user['role'] == ROLE_TEACHER:
            visible[idx]['teacher'] = user.get('teacher_name') or visible[idx].get('teacher', '')
        if has_full_data_access(user['role']):
            _save_students(visible)
        else:
            global_idx = find_student_global_index(all_rows, visible, idx)
            if global_idx is None:
                abort(404)
            all_rows[global_idx] = visible[idx]
            _save_students(all_rows)
        return redirect(url_for('students'))
    return render_template('student_edit.html',
        student=visible[idx], idx=idx, score_fields=SCORE_FIELDS, is_new=False)


@app.route('/students/new', methods=['GET', 'POST'])
@login_required
def student_new():
    all_rows, visible = _scoped_students()
    user = _current_user()
    if request.method == 'POST':
        new_row = {f: request.form.get(f, '') for f in STUDENT_FIELDS}
        if user['role'] == ROLE_TEACHER:
            new_row['teacher'] = user.get('teacher_name') or new_row.get('teacher', '')
        all_rows.append(new_row)
        _save_students(all_rows)
        return redirect(url_for('students'))
    defaults = dict(visible[0]) if visible else dict(all_rows[0]) if all_rows else {}
    defaults['student_name'] = ''
    defaults.setdefault('faltas', '0')
    if user['role'] == ROLE_TEACHER:
        defaults['teacher'] = user.get('teacher_name', '')
    return render_template('student_edit.html',
        student=defaults, idx=None, score_fields=SCORE_FIELDS, is_new=True)


@app.route('/students/<int:idx>/delete', methods=['POST'])
@login_required
def student_delete(idx):
    all_rows, visible = _scoped_students()
    if 0 <= idx < len(visible):
        if has_full_data_access(_current_user()['role']):
            all_rows.remove(visible[idx])
        else:
            global_idx = find_student_global_index(all_rows, visible, idx)
            if global_idx is not None:
                all_rows.pop(global_idx)
        _save_students(all_rows)
    return redirect(url_for('students'))


# ── Upload ────────────────────────────────────────────────────────────────────────────

@app.route('/upload', methods=['GET', 'POST'])
@role_required(ROLE_SUPERADMIN, ROLE_ADMIN)
def upload():
    messages = []
    errors = []
    if request.method == 'POST':
        for key, label in [('students', 'Alunos'), ('lessons', 'Aulas')]:
            f = request.files.get(key)
            if f and f.filename:
                text, decode_error = _read_csv_text(f)
                if decode_error:
                    errors.append(f'Erro no CSV de {label}: {decode_error}')
                    continue

                validation_errors = _validate_csv(key, text)
                if validation_errors:
                    errors.append(f'Erro no CSV de {label}: {validation_errors[0]}')
                    continue

                try:
                    rows = _csv_rows_from_text(text)
                    if key == 'students':
                        _save_students(rows)
                    else:
                        _save_lessons(rows)
                    messages.append(f'{label} carregado: {f.filename}')
                except OSError as exc:
                    errors.append(f'Erro ao salvar {label}: {exc}')
    if db_store:
        students_exists = bool(_load_students())
        lessons_exists = bool(_load_lessons())
    else:
        students_exists = (DATA_DIR / 'students.csv').exists()
        lessons_exists = (DATA_DIR / 'lessons.csv').exists()
    return render_template('upload.html', messages=messages, errors=errors,
        students_exists=students_exists, lessons_exists=lessons_exists,
        student_template_rows=_load_template_rows('students'),
        lesson_template_rows=_load_template_rows('lessons'),
        student_field_labels=STUDENT_FIELD_LABELS,
        lesson_field_labels=LESSON_FIELD_LABELS,
        student_template_sections=STUDENT_TEMPLATE_SECTIONS,
        student_fields=STUDENT_FIELDS,
        lesson_fields=LESSON_FIELDS,
        student_preview_columns=_student_preview_columns(),
        lesson_preview_columns=_lesson_preview_columns(),
        score_fields=sorted(SCORE_FIELDS),
    )


@app.route('/upload/template/<name>')
@role_required(ROLE_SUPERADMIN, ROLE_ADMIN)
def download_template(name):
    if name not in ('students', 'lessons'):
        abort(404)

    buf = _build_template_csv(name)
    data = io.BytesIO(buf.encode('utf-8'))
    data.seek(0)
    return send_file(
        data,
        as_attachment=True,
        download_name=f'{name}_template.csv',
        mimetype='text/csv; charset=utf-8',
    )


@app.route('/upload/download/<name>')
@role_required(ROLE_SUPERADMIN, ROLE_ADMIN)
def download_csv(name):
    if name not in ('students', 'lessons'):
        abort(404)
    if db_store:
        rows = _load_students() if name == 'students' else _load_lessons()
        if not rows:
            abort(404)
        fields = STUDENT_FIELDS if name == 'students' else LESSON_FIELDS
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
        data = io.BytesIO(buf.getvalue().encode('utf-8'))
        data.seek(0)
        return send_file(data, as_attachment=True, download_name=f'{name}.csv', mimetype='text/csv')

    path = DATA_DIR / f'{name}.csv'
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=f'{name}.csv')


# ── Generate & Reports ────────────────────────────────────────────────────────────────

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    all_students, students = _scoped_students()
    _, lessons = _scoped_lessons(all_students)
    user = _current_user()

    if db_store:
        if not students or not lessons:
            return redirect(url_for('upload' if has_full_data_access(user['role']) else 'dashboard'))
        env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False)
        generate_individual_reports(students, lessons, env, OUT_DIR)
        generate_class_diagnostics(students, lessons, env, OUT_DIR)
        return redirect(url_for('reports'))

    if has_full_data_access(user['role']):
        students_file = DATA_DIR / 'students.csv'
        lessons_file = DATA_DIR / 'lessons.csv'
        students_text = students_file.read_text(encoding='utf-8')
        lessons_text = lessons_file.read_text(encoding='utf-8')
        students_errors = _validate_csv('students', students_text)
        lessons_errors = _validate_csv('lessons', lessons_text)
        if students_errors or lessons_errors:
            errors = []
            if students_errors:
                errors.append(f'CSV de Alunos invalido: {students_errors[0]}')
            if lessons_errors:
                errors.append(f'CSV de Aulas invalido: {lessons_errors[0]}')
            return render_template(
                'upload.html',
                messages=[],
                errors=errors,
                students_exists=students_file.exists(),
                lessons_exists=lessons_file.exists(),
            )

    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False)
    generate_individual_reports(students, lessons, env, OUT_DIR)
    generate_class_diagnostics(students, lessons, env, OUT_DIR)
    return redirect(url_for('reports'))


@app.route('/admin/teachers', methods=['GET', 'POST'])
@role_required(ROLE_SUPERADMIN, ROLE_ADMIN)
def manage_teachers():
    messages = []
    errors = []
    actor = _current_user()

    if request.method == 'POST':
        action = request.form.get('action', '')
        try:
            if action == 'create_teacher':
                user_store.create_teacher(
                    request.form.get('email', ''),
                    request.form.get('password', ''),
                    request.form.get('teacher_name', ''),
                )
                messages.append('Conta de professor criada.')
            elif action == 'create_admin' and actor['role'] == ROLE_SUPERADMIN:
                user_store.create_admin(
                    request.form.get('email', ''),
                    request.form.get('password', ''),
                    request.form.get('role', ROLE_ADMIN),
                )
                messages.append('Conta administrativa criada.')
            elif action == 'update':
                user_id = int(request.form.get('user_id', '0'))
                password = request.form.get('password', '').strip()
                user_store.update_user(
                    user_id,
                    email=request.form.get('email'),
                    password=password or None,
                    teacher_name=request.form.get('teacher_name'),
                    active=request.form.get('active') == '1',
                )
                messages.append('Usuário atualizado.')
            elif action == 'delete':
                user_id = int(request.form.get('user_id', '0'))
                user_store.delete_user(user_id, actor_id=actor['id'])
                messages.append('Usuário removido.')
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))

    users = [user_public_dict(u) for u in user_store.list_users()]
    teacher_names = sorted({
        normalize_teacher_name(s.get('teacher', ''))
        for s in _load_students()
        if s.get('teacher', '').strip()
    })
    return render_template(
        'teachers.html',
        users=users,
        teacher_names=teacher_names,
        messages=messages,
        errors=errors,
        roles_manageable=[ROLE_ADMIN, ROLE_TEACHER] if actor['role'] == ROLE_SUPERADMIN else [ROLE_TEACHER],
    )


@app.route('/reports')
@login_required
def reports():
    all_students, _ = _scoped_students()
    files = filter_reports_for_user(sorted(OUT_DIR.glob('*.html')), all_students, _current_user())
    individual = [f for f in files if 'class_diagnostic' not in f.name]
    diagnostics = [f for f in files if 'class_diagnostic' in f.name]
    return render_template('reports.html', individual=individual, diagnostics=diagnostics)


def _allowed_report_path(filename):
    path = OUT_DIR / Path(filename).name
    if not path.exists() or path.suffix != '.html':
        return None
    all_students, _ = _scoped_students()
    allowed = filter_reports_for_user([path], all_students, _current_user())
    return path if allowed else None


@app.route('/reports/preview/<path:filename>')
@login_required
def preview(filename):
    path = _allowed_report_path(filename)
    if not path:
        abort(404)
    return path.read_text(encoding='utf-8')


@app.route('/reports/download/<path:filename>')
@login_required
def download_report(filename):
    path = _allowed_report_path(filename)
    if not path:
        abort(404)
    return send_file(path, as_attachment=True)


@app.route('/reports/download-all')
@login_required
def download_all():
    all_students, _ = _scoped_students()
    files = filter_reports_for_user(sorted(OUT_DIR.glob('*.html')), all_students, _current_user())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, download_name='mister_wiz_reports.zip')


if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    port = int(os.environ.get('PORT', '5000'))
    app.run(debug=debug, host='0.0.0.0', port=port)
