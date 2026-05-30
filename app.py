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

from compiler import (build_student_ctx, create_report_environment,
                      generate_class_diagnostics, generate_individual_reports,
                      group_by_turma, load_csv)

from auth import (ROLE_ADMIN, ROLE_LABELS, ROLE_SUPERADMIN, ROLE_TEACHER,
                  UserStore, can_manage_teachers, filter_extra_sessions_for_user,
                  filter_lessons_for_user, filter_reports_for_user,
                  filter_students_for_user, find_extra_session_global_index,
                  find_lesson_global_index, find_student_global_index,
                  has_full_data_access, normalize_teacher_name, teacher_turmas,
                  user_public_dict)
from csv_import import parse_upload_csv
from extra_sessions import (EXTRA_SESSION_FIELD_LABELS, EXTRA_SESSION_FIELDS,
                            build_atendimentos_template_csv,
                            SESSION_TYPE_CHOICES, coerce_session_status_fields,
                            display_status, is_status_ok, parse_import_csv,
                            row_from_form)
from form_ui import date_from_form, storage_date_to_iso, storage_time_to_input
from report_periods import (available_report_months, compute_month_trend,
                            default_report_month, filter_report_files_by_month,
                            individual_report_filename, load_snapshots,
                            month_label, report_month_from_filename,
                            student_composite_score, upsert_month_snapshots)

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
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE / '.env')
        return
    except ImportError:
        pass
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
            'extra_session_rows': len(db_store.load_extra_sessions()),
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
SNAPSHOTS_PATH = DATA_DIR / 'student_snapshots.json'

app = Flask(__name__, template_folder='web_templates')
SECRET_KEY = os.environ.get('SECRET_KEY')
PRODUCTION_ENV = (
    os.environ.get('FLASK_ENV') == 'production'
    or os.environ.get('RAILWAY_ENVIRONMENT')
    or os.environ.get('RAILWAY_SERVICE_ID')
)
if PRODUCTION_ENV and not SECRET_KEY:
    raise RuntimeError('SECRET_KEY must be set in production.')
app.secret_key = SECRET_KEY or 'mw-dev-change-in-prod'
app.config.update(
    MAX_CONTENT_LENGTH=int(os.environ.get('MAX_UPLOAD_MB', '5')) * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=bool(PRODUCTION_ENV),
)

app.jinja_env.globals.update(
    storage_date_to_iso=storage_date_to_iso,
    storage_time_to_input=storage_time_to_input,
    is_status_ok=is_status_ok,
    display_status=display_status,
    month_label=month_label,
    report_month_from_filename=report_month_from_filename,
)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
SUPERADMIN_EMAIL = os.environ.get('SUPERADMIN_EMAIL', 'admin@misterwiz.local').strip()
SUPERADMIN_PASSWORD = os.environ.get('SUPERADMIN_PASSWORD', ADMIN_PASSWORD).strip()
SUPERADMIN_SYNC_PASSWORD = os.environ.get('SUPERADMIN_SYNC_PASSWORD', '').lower() in (
    '1', 'true', 'yes',
)


def _bootstrap_auth_accounts():
    """Keep PostgreSQL/JSON users aligned with SUPERADMIN_EMAIL + SUPERADMIN_PASSWORD."""
    user_store.apply_env_superadmin(SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)
    if SUPERADMIN_SYNC_PASSWORD:
        user_store.sync_superadmin_password(SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)


user_store = UserStore(
    db_store=db_store,
    json_path=DATA_DIR / 'users.json',
)
try:
    user_store.initialize()
    _bootstrap_auth_accounts()
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


def _teacher_scope_errors(user):
    if has_full_data_access(user['role']):
        return None
    if user['role'] != ROLE_TEACHER:
        return ['Conta sem permissão para enviar CSV.']
    if not normalize_teacher_name(user.get('teacher_name', '')):
        return ['Seu perfil não tem nome de professor vinculado. Peça ao admin em Usuários.']
    return None


def _validate_teacher_student_rows(rows, user):
    teacher_key = normalize_teacher_name(user.get('teacher_name', '')).casefold()
    expected = user.get('teacher_name', '')
    errors = []
    for idx, row in enumerate(rows, start=2):
        row_teacher = normalize_teacher_name(row.get('teacher', '')).casefold()
        if row_teacher != teacher_key:
            errors.append(
                f'Linha {idx}: coluna teacher deve ser "{expected}" (apenas seus alunos).',
            )
        if len(errors) >= 10:
            errors.append('Muitos erros encontrados; corrija os primeiros e tente novamente.')
            break
    return errors


def _validate_teacher_lesson_rows(rows, user, students):
    turmas = teacher_turmas(students, user.get('teacher_name', ''))
    if not turmas:
        return [
            'Nenhuma turma vinculada ao seu perfil. Envie o CSV de alunos antes das aulas.',
        ]
    errors = []
    for idx, row in enumerate(rows, start=2):
        turma = row.get('turma', '').strip()
        if turma not in turmas:
            errors.append(
                f'Linha {idx}: turma "{turma}" não é sua '
                f'(permitidas: {", ".join(sorted(turmas))}).',
            )
        if len(errors) >= 10:
            errors.append('Muitos erros encontrados; corrija os primeiros e tente novamente.')
            break
    return errors


def _merge_teacher_students(new_rows, user):
    teacher_key = normalize_teacher_name(user.get('teacher_name', '')).casefold()
    kept = [
        row for row in _load_students()
        if normalize_teacher_name(row.get('teacher', '')).casefold() != teacher_key
    ]
    return kept + new_rows


def _merge_teacher_lessons(new_rows, user, students):
    turmas = teacher_turmas(students, user.get('teacher_name', ''))
    kept = [
        row for row in _load_lessons()
        if row.get('turma', '').strip() not in turmas
    ]
    return kept + new_rows


def _save_upload_dataset(key, rows, user, students_context=None):
    if has_full_data_access(user['role']):
        if key == 'students':
            _save_students(rows)
        else:
            _save_lessons(rows)
        return

    if key == 'students':
        _save_students(_merge_teacher_students(rows, user))
        return

    students = students_context if students_context is not None else _load_students()
    _save_lessons(_merge_teacher_lessons(rows, user, students))


def _teacher_template_rows(name, user):
    if name == 'students':
        row = dict(TEMPLATE_ROWS['students'])
        row['teacher'] = user.get('teacher_name') or row.get('teacher', '')
        return [row]
    all_students = _load_students()
    turmas = teacher_turmas(all_students, user.get('teacher_name', ''))
    if turmas:
        return [r for r in LESSON_TEMPLATE_ROWS if r.get('turma', '').strip() in turmas]
    return [dict(LESSON_TEMPLATE_ROWS[0])]


def _current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    try:
        user = user_store.get_by_id(user_id)
    except Exception as exc:
        logger.warning('Could not refresh session user %s: %s', user_id, exc)
        session.clear()
        return None
    if not user or not user.get('active', True):
        session.clear()
        return None
    public = user_public_dict(user)
    session['email'] = public['email']
    session['role'] = public['role']
    session['teacher_name'] = public.get('teacher_name') or ''
    return public


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
    all_lessons = _sort_lessons(_load_lessons())
    user = _current_user()
    if not user:
        return all_lessons, []
    if all_students is None:
        all_students = _load_students()
    visible = filter_lessons_for_user(all_lessons, all_students, user)
    return all_lessons, visible


def _allowed_turmas(all_students, user):
    if has_full_data_access(user['role']):
        return sorted({s.get('turma', '').strip() for s in all_students if s.get('turma', '').strip()})
    return sorted(teacher_turmas(all_students, user.get('teacher_name', '')))


def _teacher_may_use_turma(turma, all_students, user):
    if has_full_data_access(user['role']):
        return True
    return turma.strip() in teacher_turmas(all_students, user.get('teacher_name', ''))


def _teacher_may_use_student_turma(turma, all_students, user):
    if has_full_data_access(user['role']):
        return True
    existing_turmas = teacher_turmas(all_students, user.get('teacher_name', ''))
    if not existing_turmas:
        return True
    return turma.strip() in existing_turmas


def _lesson_from_form():
    row = {field: (request.form.get(field) or '').strip() for field in LESSON_FIELDS}
    row['date'] = date_from_form(request.form)
    return row


def _sort_lessons(rows):
    def sort_key(row):
        turma = row.get('turma', '')
        num = row.get('aula_num', '')
        try:
            num_val = int(float(num))
        except (TypeError, ValueError):
            num_val = 9999
        return (turma, num_val, num)

    return sorted(rows, key=sort_key)


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
        'can_upload_csv': bool(user),
        'can_upload_all_csv': has_full_data_access(user['role']) if user else False,
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


def _load_extra_sessions():
    if db_store:
        rows = db_store.load_extra_sessions()
    else:
        path = DATA_DIR / 'extra_sessions.csv'
        rows = load_csv(path) if path.exists() else []
    return [coerce_session_status_fields(dict(row)) for row in rows]


def _save_extra_sessions(rows):
    if db_store:
        db_store.save_extra_sessions(rows)
        return
    with open(DATA_DIR / 'extra_sessions.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=EXTRA_SESSION_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def _scoped_extra_sessions():
    all_rows = _load_extra_sessions()
    user = _current_user()
    if not user:
        return all_rows, []
    visible = filter_extra_sessions_for_user(all_rows, user)
    return all_rows, visible


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


def _rows_to_csv_text(key, rows):
    fields = STUDENT_FIELDS if key == 'students' else LESSON_FIELDS
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _queue_upload_notice(message=None, error=None):
    if message:
        messages = list(session.get('upload_messages', []))
        messages.append(message)
        session['upload_messages'] = messages
    if error:
        errors = list(session.get('upload_errors', []))
        errors.append(error)
        session['upload_errors'] = errors


def _pull_upload_notices():
    messages = session.pop('upload_messages', [])
    errors = session.pop('upload_errors', [])
    return messages, errors


def _upload_page_context(user, messages=None, errors=None):
    messages = list(messages or [])
    errors = list(errors or [])
    all_students = _load_students()
    all_lessons = _load_lessons()
    if has_full_data_access(user['role']):
        students_exists = bool(all_students) if db_store else (DATA_DIR / 'students.csv').exists()
        lessons_exists = bool(all_lessons) if db_store else (DATA_DIR / 'lessons.csv').exists()
    else:
        students_exists = bool(filter_students_for_user(all_students, user))
        lessons_exists = bool(filter_lessons_for_user(all_lessons, all_students, user))
    return {
        'messages': messages,
        'errors': errors,
        'can_delete_all_csv': has_full_data_access(user['role']),
        'is_teacher_upload': not has_full_data_access(user['role']),
        'students_exists': students_exists,
        'lessons_exists': lessons_exists,
        'student_template_rows': _load_template_rows('students'),
        'lesson_template_rows': _load_template_rows('lessons'),
        'student_field_labels': STUDENT_FIELD_LABELS,
        'lesson_field_labels': LESSON_FIELD_LABELS,
        'student_template_sections': STUDENT_TEMPLATE_SECTIONS,
        'student_fields': STUDENT_FIELDS,
        'lesson_fields': LESSON_FIELDS,
        'student_preview_columns': _student_preview_columns(),
        'lesson_preview_columns': _lesson_preview_columns(),
        'score_fields': sorted(SCORE_FIELDS),
    }


def _delete_csv_dataset(name, user):
    """Remove uploaded CSV data. Admins clear all; teachers only their rows."""
    if name not in ('students', 'lessons'):
        abort(404)

    if has_full_data_access(user['role']):
        if db_store:
            if name == 'students':
                before = len(_load_students())
                _save_students([])
            else:
                before = len(_load_lessons())
                _save_lessons([])
        else:
            path = DATA_DIR / f'{name}.csv'
            before = len(load_csv(path)) if path.exists() else 0
            if path.exists():
                path.unlink()
        return before, True

    teacher_key = normalize_teacher_name(user.get('teacher_name', '')).casefold()
    if not teacher_key:
        return 0, False

    if name == 'students':
        all_rows = _load_students()
        kept = [
            row for row in all_rows
            if normalize_teacher_name(row.get('teacher', '')).casefold() != teacher_key
        ]
        removed = len(all_rows) - len(kept)
        _save_students(kept)
        return removed, False

    all_students = _load_students()
    turmas = teacher_turmas(all_students, user.get('teacher_name', ''))
    all_lessons = _load_lessons()
    kept = [
        row for row in all_lessons
        if row.get('turma', '').strip() not in turmas
    ]
    removed = len(all_lessons) - len(kept)
    _save_lessons(kept)
    return removed, False


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


@app.route('/health/auth')
def health_auth():
    """Auth diagnostics (JSON). Public payload intentionally excludes PII."""
    status = user_store.auth_status(SUPERADMIN_EMAIL)
    public_status = {
        'user_count': status['user_count'],
        'superadmin_count': status['superadmin_count'],
        'bootstrap_email_configured': status['bootstrap_email_configured'],
        'bootstrap_email_registered': status['bootstrap_email_registered'],
        'password_configured': bool(SUPERADMIN_PASSWORD),
        'storage': 'postgresql' if db_store else 'json',
    }
    return json.dumps(public_status, ensure_ascii=False), 200, {'Content-Type': 'application/json'}


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    user_count = len(user_store.list_users())
    bootstrap_email = SUPERADMIN_EMAIL or 'admin@misterwiz.local'

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        user = user_store.authenticate(email, password)
        if user:
            _login_session(user)
            return redirect(url_for('dashboard'))
        if user_count == 0:
            error = (
                'Nenhuma conta foi criada no servidor. Defina SUPERADMIN_EMAIL e '
                'SUPERADMIN_PASSWORD nas variáveis de ambiente (Railway) e reinicie o app.'
            )
        elif not SUPERADMIN_PASSWORD and user_store.get_by_email(email) is None:
            error = (
                f'E-mail ou senha incorretos. Primeiro acesso do administrador: use '
                f'{bootstrap_email} e a senha definida em SUPERADMIN_PASSWORD.'
            )
        else:
            known = user_store.get_by_email(email)
            if known and not known.get('active', True):
                error = 'Esta conta está desativada. Peça a um administrador para reativá-la.'
            elif known:
                error = 'Senha incorreta para este e-mail.'
            else:
                error = (
                    f'E-mail não cadastrado. Administrador: use {bootstrap_email}. '
                    f'Professores: use o e-mail criado em Usuários.'
                )
    return render_template(
        'login.html',
        error=error,
        bootstrap_email=bootstrap_email,
        accounts_configured=user_count > 0,
    )


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
    generate_error = session.pop('generate_error', None)
    return render_template('dashboard.html',
        student_count=len(students),
        turma_count=len(turmas),
        lesson_count=len(lessons),
        report_count=len(individual),
        turmas=list(turmas.keys()),
        data_ready=data_ready,
        db_status=db_status,
        available_months=available_report_months(lessons),
        default_month=default_report_month(lessons),
        generate_error=generate_error,
    )


# ── Students ──────────────────────────────────────────────────────────────────────────

@app.route('/students')
@login_required
def students():
    _, rows = _scoped_students()
    turmas = sorted({r.get('turma', '').strip() for r in rows if r.get('turma', '').strip()})
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
        if not visible[idx].get('turma') or not visible[idx].get('student_name'):
            abort(400)
        if not _teacher_may_use_student_turma(visible[idx]['turma'], all_rows, user):
            abort(403)
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
        if not new_row.get('turma') or not new_row.get('student_name'):
            abort(400)
        if not _teacher_may_use_student_turma(new_row['turma'], all_rows, user):
            abort(403)
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


# ── Lessons (class details) ───────────────────────────────────────────────────────────

@app.route('/lessons')
@login_required
def lessons():
    all_students, _ = _scoped_students()
    _, rows = _scoped_lessons(all_students)
    turmas = sorted({r.get('turma', '').strip() for r in rows if r.get('turma', '').strip()})
    return render_template(
        'lessons.html',
        lessons=rows,
        turmas=turmas,
        lesson_field_labels=LESSON_FIELD_LABELS,
    )


@app.route('/lessons/<int:idx>/edit', methods=['GET', 'POST'])
@login_required
def lesson_edit(idx):
    all_students, _ = _scoped_students()
    all_rows, visible = _scoped_lessons(all_students)
    user = _current_user()
    allowed_turmas = _allowed_turmas(all_students, user)

    if idx < 0 or idx >= len(visible):
        abort(404)

    if request.method == 'POST':
        updated = _lesson_from_form()
        if not updated.get('turma') or not updated.get('aula_num'):
            abort(400)
        if not _teacher_may_use_turma(updated['turma'], all_students, user):
            abort(403)
        global_idx = find_lesson_global_index(all_rows, visible, idx)
        if global_idx is None:
            abort(404)
        all_rows[global_idx] = updated
        _save_lessons(_sort_lessons(all_rows))
        return redirect(url_for('lessons'))

    return render_template(
        'lesson_edit.html',
        lesson=visible[idx],
        idx=idx,
        is_new=False,
        allowed_turmas=allowed_turmas,
        lesson_field_labels=LESSON_FIELD_LABELS,
    )


@app.route('/lessons/new', methods=['GET', 'POST'])
@login_required
def lesson_new():
    all_students, _ = _scoped_students()
    all_rows, visible = _scoped_lessons(all_students)
    user = _current_user()
    allowed_turmas = _allowed_turmas(all_students, user)

    if request.method == 'POST':
        new_row = _lesson_from_form()
        if not new_row.get('turma') or not new_row.get('aula_num'):
            abort(400)
        if not _teacher_may_use_turma(new_row['turma'], all_students, user):
            abort(403)
        all_rows.append(new_row)
        _save_lessons(_sort_lessons(all_rows))
        return redirect(url_for('lessons'))

    defaults = dict(visible[-1]) if visible else {}
    for field in LESSON_FIELDS:
        defaults.setdefault(field, '')
    if allowed_turmas:
        defaults['turma'] = allowed_turmas[0]
    return render_template(
        'lesson_edit.html',
        lesson=defaults,
        idx=None,
        is_new=True,
        allowed_turmas=allowed_turmas,
        lesson_field_labels=LESSON_FIELD_LABELS,
    )


# ── Extra sessions (reforço / reposição / nivelamento) ───────────────────────────────

@app.route('/extra-sessions')
@login_required
def extra_sessions():
    _, rows = _scoped_extra_sessions()
    teachers = sorted({r.get('teacher', '').strip() for r in rows if r.get('teacher', '').strip()})
    types = sorted({r.get('session_type', '').strip() for r in rows if r.get('session_type', '').strip()})
    message = session.pop('extra_session_flash_message', None)
    error = session.pop('extra_session_flash_error', None)
    return render_template(
        'extra_sessions.html',
        sessions=rows,
        teachers=teachers,
        session_types=types or list(SESSION_TYPE_CHOICES),
        field_labels=EXTRA_SESSION_FIELD_LABELS,
        message=message,
        error=error,
    )


@app.route('/extra-sessions/new', methods=['GET', 'POST'])
@login_required
def extra_session_new():
    all_rows, visible = _scoped_extra_sessions()
    user = _current_user()
    if request.method == 'POST':
        new_row = row_from_form(request.form)
        if user['role'] == ROLE_TEACHER:
            new_row['teacher'] = user.get('teacher_name') or new_row.get('teacher', '')
        if not new_row.get('student_name'):
            abort(400)
        all_rows.append(new_row)
        _save_extra_sessions(all_rows)
        return redirect(url_for('extra_sessions'))

    defaults = {f: '' for f in EXTRA_SESSION_FIELDS}
    defaults['session_type'] = 'Reforço'
    if user['role'] == ROLE_TEACHER:
        defaults['teacher'] = user.get('teacher_name', '')
    return render_template(
        'extra_session_edit.html',
        session=defaults,
        idx=None,
        is_new=True,
        field_labels=EXTRA_SESSION_FIELD_LABELS,
        session_type_choices=SESSION_TYPE_CHOICES,
        teacher_names=_teacher_names_from_students(),
    )


@app.route('/extra-sessions/<int:idx>/edit', methods=['GET', 'POST'])
@login_required
def extra_session_edit(idx):
    all_rows, visible = _scoped_extra_sessions()
    user = _current_user()
    if idx < 0 or idx >= len(visible):
        abort(404)

    if request.method == 'POST':
        updated = row_from_form(request.form)
        if user['role'] == ROLE_TEACHER:
            updated['teacher'] = user.get('teacher_name') or updated.get('teacher', '')
        if not updated.get('student_name'):
            abort(400)
        global_idx = find_extra_session_global_index(all_rows, visible, idx)
        if global_idx is None:
            abort(404)
        all_rows[global_idx] = updated
        _save_extra_sessions(all_rows)
        return redirect(url_for('extra_sessions'))

    return render_template(
        'extra_session_edit.html',
        session=visible[idx],
        idx=idx,
        is_new=False,
        field_labels=EXTRA_SESSION_FIELD_LABELS,
        session_type_choices=SESSION_TYPE_CHOICES,
        teacher_names=_teacher_names_from_students(),
    )


@app.route('/extra-sessions/<int:idx>/delete', methods=['POST'])
@login_required
def extra_session_delete(idx):
    all_rows, visible = _scoped_extra_sessions()
    if 0 <= idx < len(visible):
        global_idx = find_extra_session_global_index(all_rows, visible, idx)
        if global_idx is not None:
            all_rows.pop(global_idx)
            _save_extra_sessions(all_rows)
    return redirect(url_for('extra_sessions'))


@app.route('/extra-sessions/import', methods=['POST'])
@role_required(ROLE_SUPERADMIN, ROLE_ADMIN)
def extra_sessions_import():
    f = request.files.get('file')
    if not f or not f.filename:
        return redirect(url_for('extra_sessions'))

    text, decode_error = _read_csv_text(f)
    if decode_error:
        session['extra_session_flash_error'] = decode_error
        return redirect(url_for('extra_sessions'))

    rows, errors = parse_import_csv(text)
    if errors:
        session['extra_session_flash_error'] = errors[0]
        return redirect(url_for('extra_sessions'))

    mode = request.form.get('mode', 'merge')
    if mode == 'replace':
        _save_extra_sessions(rows)
        session['extra_session_flash_message'] = f'{len(rows)} atendimento(s) importado(s) (substituiu tudo).'
    else:
        existing = _load_extra_sessions()
        existing.extend(rows)
        _save_extra_sessions(existing)
        session['extra_session_flash_message'] = f'{len(rows)} atendimento(s) adicionado(s).'
    return redirect(url_for('extra_sessions'))


@app.route('/extra-sessions/template')
@login_required
def download_atendimentos_template():
    user = _current_user()
    teacher_name = None
    if not has_full_data_access(user['role']):
        teacher_name = normalize_teacher_name(user.get('teacher_name', ''))
    csv_text = build_atendimentos_template_csv(
        TEMPLATE_DIR,
        teacher_name=teacher_name or None,
    )
    data = io.BytesIO(csv_text.encode('utf-8'))
    data.seek(0)
    return send_file(
        data,
        as_attachment=True,
        download_name='atendimentos_template.csv',
        mimetype='text/csv; charset=utf-8',
    )


def _teacher_names_from_students():
    names = {
        normalize_teacher_name(s.get('teacher', ''))
        for s in _load_students()
        if s.get('teacher', '').strip()
    }
    return sorted(n for n in names if n)


@app.route('/lessons/<int:idx>/delete', methods=['POST'])
@login_required
def lesson_delete(idx):
    all_students, _ = _scoped_students()
    all_rows, visible = _scoped_lessons(all_students)
    if 0 <= idx < len(visible):
        global_idx = find_lesson_global_index(all_rows, visible, idx)
        if global_idx is not None:
            all_rows.pop(global_idx)
            _save_lessons(all_rows)
    return redirect(url_for('lessons'))


# ── Upload ────────────────────────────────────────────────────────────────────────────

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    user = _current_user()
    messages, errors = _pull_upload_notices()
    if request.method == 'POST':
        scope_errors = _teacher_scope_errors(user)
        if scope_errors:
            errors.extend(scope_errors)
        else:
            students_after_upload = _load_students()
            for key, label in [('students', 'Alunos'), ('lessons', 'Aulas')]:
                f = request.files.get(key)
                if not (f and f.filename):
                    continue

                text, decode_error = _read_csv_text(f)
                if decode_error:
                    errors.append(f'Erro no CSV de {label}: {decode_error}')
                    continue

                rows, convert_note, parse_errors = parse_upload_csv(
                    key,
                    text,
                    user=user,
                    source_filename=f.filename,
                )
                if parse_errors:
                    errors.append(f'Erro no CSV de {label}: {parse_errors[0]}')
                    continue

                validation_errors = _validate_csv(key, _rows_to_csv_text(key, rows))
                if validation_errors:
                    errors.append(f'Erro no CSV de {label}: {validation_errors[0]}')
                    continue

                if not has_full_data_access(user['role']):
                    if key == 'students':
                        validation_errors = _validate_teacher_student_rows(rows, user)
                    else:
                        validation_errors = _validate_teacher_lesson_rows(
                            rows, user, students_after_upload,
                        )
                    if validation_errors:
                        errors.append(f'Erro no CSV de {label}: {validation_errors[0]}')
                        continue

                try:
                    _save_upload_dataset(key, rows, user, students_after_upload)
                    if key == 'students':
                        students_after_upload = _load_students()
                    success = f'{label} carregado: {f.filename}'
                    if convert_note:
                        success = f'{success} ({convert_note})'
                    messages.append(success)
                except OSError as exc:
                    errors.append(f'Erro ao salvar {label}: {exc}')
    return render_template('upload.html', **_upload_page_context(user, messages, errors))


@app.route('/upload/delete/<name>', methods=['POST'])
@login_required
def delete_csv(name):
    user = _current_user()
    removed, full_delete = _delete_csv_dataset(name, user)
    label = 'Alunos' if name == 'students' else 'Aulas'
    if removed == 0:
        _queue_upload_notice(error=f'Nenhum dado de {label.lower()} para remover.')
    elif full_delete:
        _queue_upload_notice(message=f'{label}: arquivo CSV removido ({removed} registro(s)).')
    else:
        _queue_upload_notice(
            message=f'{label}: {removed} registro(s) do seu perfil removido(s).')
    return redirect(url_for('upload'))


@app.route('/upload/template/<name>')
@login_required
def download_template(name):
    if name not in ('students', 'lessons'):
        abort(404)

    user = _current_user()
    if has_full_data_access(user['role']):
        buf = _build_template_csv(name)
    else:
        scope_errors = _teacher_scope_errors(user)
        if scope_errors:
            abort(403)
        fields = STUDENT_FIELDS if name == 'students' else LESSON_FIELDS
        rows = _teacher_template_rows(name, user)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
        buf = '\ufeff' + buf.getvalue()
    data = io.BytesIO(buf.encode('utf-8'))
    data.seek(0)
    return send_file(
        data,
        as_attachment=True,
        download_name=f'{name}_template.csv',
        mimetype='text/csv; charset=utf-8',
    )


@app.route('/upload/download/<name>')
@login_required
def download_csv(name):
    if name not in ('students', 'lessons'):
        abort(404)
    user = _current_user()
    if db_store:
        all_students = _load_students()
        if name == 'students':
            rows = (
                _load_students()
                if has_full_data_access(user['role'])
                else filter_students_for_user(all_students, user)
            )
        else:
            all_lessons = _load_lessons()
            rows = (
                all_lessons
                if has_full_data_access(user['role'])
                else filter_lessons_for_user(all_lessons, all_students, user)
            )
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
    if has_full_data_access(user['role']):
        return send_file(path, as_attachment=True, download_name=f'{name}.csv')

    all_students = load_csv(DATA_DIR / 'students.csv') if (DATA_DIR / 'students.csv').exists() else []
    all_lessons = load_csv(path) if name == 'lessons' else []
    if name == 'students':
        rows = filter_students_for_user(all_students, user)
    else:
        rows = filter_lessons_for_user(all_lessons, all_students, user)
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


# ── Generate & Reports ────────────────────────────────────────────────────────────────

def _report_month_from_request(lessons):
    raw = (request.form.get('report_month') or request.args.get('month') or '').strip()
    if raw and raw in available_report_months(lessons):
        return raw
    return default_report_month(lessons)


def _validate_generation_inputs(students, lessons):
    """Return a user-facing error message, or None when generation can proceed."""
    if not students:
        return 'Nenhum aluno encontrado para o seu perfil. Cadastre alunos antes de gerar relatórios.'
    if not lessons:
        return (
            'Nenhuma aula encontrada para as turmas selecionadas. '
            'Cadastre o CSV de aulas (ou confira se as turmas dos alunos batem com as aulas).'
        )
    missing = []
    for idx, student in enumerate(students, start=1):
        if not (student.get('turma') or '').strip():
            missing.append(f'linha {idx}: turma em branco')
        if not (student.get('student_name') or '').strip():
            missing.append(f'linha {idx}: nome do aluno em branco')
        if len(missing) >= 3:
            break
    if missing:
        return 'Dados de alunos incompletos: ' + '; '.join(missing) + '.'
    return None


def _run_report_generation(students, lessons, report_month):
    snapshots = load_snapshots(SNAPSHOTS_PATH)
    env = create_report_environment(TMPL_DIR)
    generate_individual_reports(
        students, lessons, env, OUT_DIR,
        report_month=report_month, snapshots=snapshots,
    )
    generate_class_diagnostics(
        students, lessons, env, OUT_DIR,
        report_month=report_month, snapshots=snapshots,
    )
    try:
        upsert_month_snapshots(
            SNAPSHOTS_PATH, report_month, students, lessons, build_student_ctx,
        )
    except OSError as exc:
        logger.warning('Could not save monthly snapshots to %s: %s', SNAPSHOTS_PATH, exc)


def _trend_for_report_file(path, month, students, lessons, snapshots):
    if not month:
        return None
    for student in students:
        turma = student.get('turma', '').strip()
        name = student.get('student_name', '').strip()
        if not turma or not name:
            continue
        if individual_report_filename(turma, name, month) != path.name:
            if individual_report_filename(turma, name) != path.name:
                continue
        ctx = build_student_ctx(student, lessons, report_month=month)
        composite = student_composite_score(ctx)
        return compute_month_trend(composite, month, snapshots, turma, name)
    return None


@app.route('/generate', methods=['POST'])
@login_required
def generate():
    all_students, students = _scoped_students()
    _, lessons = _scoped_lessons(all_students)
    user = _current_user()
    report_month = _report_month_from_request(lessons)

    if has_full_data_access(user['role']) and not db_store:
        students_file = DATA_DIR / 'students.csv'
        lessons_file = DATA_DIR / 'lessons.csv'
        missing = []
        if not students_file.exists():
            missing.append('students.csv não encontrado.')
        if not lessons_file.exists():
            missing.append('lessons.csv não encontrado.')
        if missing:
            return render_template(
                'upload.html',
                **_upload_page_context(user, errors=missing),
            )
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
                **_upload_page_context(user, errors=errors),
            )

    input_error = _validate_generation_inputs(students, lessons)
    if input_error:
        session['generate_error'] = input_error
        return redirect(url_for('dashboard'))

    try:
        _run_report_generation(students, lessons, report_month)
    except Exception as exc:
        logger.exception('Report generation failed for month %s: %s', report_month, exc)
        session['generate_error'] = (
            'Não foi possível gerar os relatórios. Verifique os dados de alunos e aulas '
            'e tente novamente. Se o problema continuar, contate o suporte.'
        )
        return redirect(url_for('dashboard'))

    return redirect(url_for('reports', month=report_month))


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
    all_students, students = _scoped_students()
    _, lessons = _scoped_lessons(all_students)
    selected_month = (request.args.get('month') or '').strip()
    available_months = available_report_months(lessons)
    if selected_month and selected_month not in available_months:
        selected_month = ''

    files = filter_reports_for_user(sorted(OUT_DIR.glob('*.html')), all_students, _current_user())
    files = filter_report_files_by_month(files, selected_month)
    individual = [f for f in files if 'class_diagnostic' not in f.name]
    diagnostics = [f for f in files if 'class_diagnostic' in f.name]

    snapshots = load_snapshots(SNAPSHOTS_PATH)
    report_trends = {}
    report_months = {}
    for path in individual:
        month = report_month_from_filename(path.name) or selected_month
        report_months[path.name] = month
        trend = _trend_for_report_file(path, month, students, lessons, snapshots)
        if trend:
            report_trends[path.name] = trend

    try:
        return render_template(
            'reports.html',
            individual=individual,
            report_trends=report_trends,
            report_months=report_months,
            diagnostics=diagnostics,
            available_months=available_months,
            selected_month=selected_month,
            default_month=default_report_month(lessons),
        )
    except Exception as exc:
        logger.exception('Reports page failed: %s', exc)
        session['generate_error'] = (
            'Não foi possível abrir a lista de relatórios. Tente gerar novamente.'
        )
        return redirect(url_for('dashboard'))


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
    _, lessons = _scoped_lessons(all_students)
    selected_month = (request.args.get('month') or '').strip()
    available_months = available_report_months(lessons)
    if selected_month and selected_month not in available_months:
        selected_month = ''
    files = filter_reports_for_user(sorted(OUT_DIR.glob('*.html')), all_students, _current_user())
    files = filter_report_files_by_month(files, selected_month)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, download_name='mister_wiz_reports.zip')


def _pick_port(preferred):
    """Use preferred port, or the next free one (macOS AirPlay often blocks 5000)."""
    import socket

    for candidate in range(preferred, preferred + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('0.0.0.0', candidate))
            except OSError:
                continue
            return candidate
    return preferred


if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    preferred = int(os.environ.get('PORT', '5000'))
    port = _pick_port(preferred)
    if port != preferred:
        logger.warning('Port %s is in use; starting on http://127.0.0.1:%s', preferred, port)
    else:
        logger.info('Starting on http://127.0.0.1:%s', port)
    app.run(debug=debug, host='0.0.0.0', port=port)
