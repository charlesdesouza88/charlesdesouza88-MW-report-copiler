#!/usr/bin/env python3
"""Mister Wiz Report Compiler — Web Dashboard"""

import csv
import functools
import io
import os
import zipfile
from pathlib import Path

from flask import (Flask, abort, redirect, render_template, request,
                   send_file, session, url_for)
from jinja2 import Environment, FileSystemLoader

from compiler import (generate_class_diagnostics, generate_individual_reports,
                      group_by_turma, load_csv)

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

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
DB_ENABLED = bool(DATABASE_URL)
db_store = None
if DB_ENABLED:
    
    db_store = DatabaseStore(DATABASE_URL)
db_store.initialize()

'/tmp/mw/data'
    default_data_dir = str(BASE / 'data')
    default_out_dir = str(BASE / 'output')

TMPL_DIR = BASE / 'templates'
DATA_DIR = _ensure_writable_dir(
    os.environ.get('DATA_DIR', default_data_dir), '/tmp/mw/data')
OUT_DIR = _ensure_writable_dir(
    os.environ.get('OUT_DIR', default_out_dir), '/tmp/mw/output')

app = Flask(__name__, template_folder='web_templates')
app.secret_key = os.environ.get('SECRET_KEY', 'mw-dev-change-in-prod')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')

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

TEMPLATE_ROWS = {
    'students': {
        'teacher': 'Chuck',
        'turma': 'MASTER',
        'turma_display': 'Masters',
        'nivel': 'Adults Book 4',
        'horario': 'Terca e quinta, 19:00 - 20:00',
        'student_name': 'Jane Doe',
        'participacao': '4',
        'comportamento': '3',
        'speaking': '4',
        'listening': '5',
        'foco': '4',
        'writing': '3',
        'reading': '4',
        'gramatica': '3',
        'trabalho_equipe': '4',
        'organizacao': '3',
        'pontualidade': '4',
        'respeito_regras': '4',
        'faltas': '1',
        'missed_aulas': '2,5',
        'aula_extra': 'Reforco',
        'feedback_participacao': 'Participa bem em aula.',
        'feedback_foco': 'Melhorar foco nas atividades longas.',
        'feedback_trabalho_equipe': 'Boa colaboracao com colegas.',
        'recomendacoes': 'Praticar speaking em casa 2x por semana.',
        'observacao': 'Exemplo de preenchimento',
    },
    'lessons': {
        'turma': 'MASTER',
        'aula_num': '1',
        'date': '03/09',
        'licao_conteudo': 'Lesson 1: Introductions',
        'atividade_extra': 'Role-play em duplas',
        'habilidades': 'Speaking, Listening',
    },
}


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


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


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

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('dashboard'))
        error = 'Senha incorreta. Tente novamente.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Dashboard ─────────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    students = _load_students()
    lessons = _load_lessons()
    reports = sorted(OUT_DIR.glob('*.html'))
    turmas = group_by_turma(students) if students else {}
    individual = [f for f in reports if 'class_diagnostic' not in f.name]
    if db_store:
        data_ready = bool(students) and bool(lessons)
    else:
        lessons_path = DATA_DIR / 'lessons.csv'
        data_ready = (DATA_DIR / 'students.csv').exists() and lessons_path.exists()
    return render_template('dashboard.html',
        student_count=len(students),
        turma_count=len(turmas),
        lesson_count=len(lessons),
        report_count=len(individual),
        turmas=list(turmas.keys()),
        data_ready=data_ready,
    )


# ── Students ──────────────────────────────────────────────────────────────────────────

@app.route('/students')
@login_required
def students():
    rows = _load_students()
    turmas = sorted(set(r['turma'] for r in rows))
    return render_template('students.html', students=rows, turmas=turmas)


@app.route('/students/<int:idx>/edit', methods=['GET', 'POST'])
@login_required
def student_edit(idx):
    rows = _load_students()
    if idx < 0 or idx >= len(rows):
        abort(404)
    if request.method == 'POST':
        for field in STUDENT_FIELDS:
            rows[idx][field] = request.form.get(field, '')
        _save_students(rows)
        return redirect(url_for('students'))
    return render_template('student_edit.html',
        student=rows[idx], idx=idx, score_fields=SCORE_FIELDS, is_new=False)


@app.route('/students/new', methods=['GET', 'POST'])
@login_required
def student_new():
    rows = _load_students()
    if request.method == 'POST':
        rows.append({f: request.form.get(f, '') for f in STUDENT_FIELDS})
        _save_students(rows)
        return redirect(url_for('students'))
    defaults = dict(rows[0]) if rows else {}
    defaults['student_name'] = ''
    defaults.setdefault('faltas', '0')
    return render_template('student_edit.html',
        student=defaults, idx=None, score_fields=SCORE_FIELDS, is_new=True)


@app.route('/students/<int:idx>/delete', methods=['POST'])
@login_required
def student_delete(idx):
    rows = _load_students()
    if 0 <= idx < len(rows):
        rows.pop(idx)
        _save_students(rows)
    return redirect(url_for('students'))


# ── Upload ────────────────────────────────────────────────────────────────────────────

@app.route('/upload', methods=['GET', 'POST'])
@login_required
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
        lessons_exists OS=rr_road_lessons())
    else:
        students_exists = (DATA_DIR / 'students.csv').exists()
        lessons_exists = (DATA_DIR / 'lessons.csv').exists()
    return render_template('upload.html', messages=messages, errors=errors,
        students_exists=students_exists, lessons_exists=lessons_exists)


@app.route('/upload/template/<name>')
@login_required
def download_template(name):
    if name == 'students':
        fields = STUDENT_FIELDS
    elif name == 'lessons':
        fields = LESSON_FIELDS
    else:
        abort(404)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerow(TEMPLATE_ROWS[name])

    data = io.BytesIO(buf.getvalue().encode('utf-8'))
    data.seek(0)
    return send_file(
        data,
        as_attachment=True,
        download_name=f'{name}_template.csv',
        mimetype='text/csv',
    )


@app.route('/upload/download/<name>')
@login_required
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
    if db_store:
        students = _load_students()
        lessons = _load_lessons()
        if not students or not lessons:
            return redirect(url_for('upload'))

        env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False)
        generate_individual_reports(students, lessons, env, OUT_DIR)
        generate_class_diagnostics(students, lessons, env, OUT_DIR)
        return redirect(url_for('reports'))

    students_file = DATA_DIR / 'students.csv'
    lessons_file = DATA_DIR / 'lessons.csv'
    if not students_file.exists() or not lessons_file.exists():
        return redirect(url_for('upload'))

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

    students = load_csv(students_file)
    lessons = load_csv(lessons_file)
    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=False)
    generate_individual_reports(students, lessons, env, OUT_DIR)
    generate_class_diagnostics(students, lessons, env, OUT_DIR)
    return redirect(url_for('reports'))


@app.route('/reports')
@login_required
def reports():
    files = sorted(OUT_DIR.glob('*.html'))
    individual = [f for f in files if 'class_diagnostic' not in f.name]
    diagnostics = [f for f in files if 'class_diagnostic' in f.name]
    return render_template('reports.html', individual=individual, diagnostics=diagnostics)


@app.route('/reports/preview/<path:filename>')
@login_required
def preview(filename):
    path = OUT_DIR / Path(filename).name
    if not path.exists() or path.suffix != '.html':
        abort(404)
    return path.read_text(encoding='utf-8')


@app.route('/reports/download/<path:filename>')
@login_required
def download_report(filename):
    path = OUT_DIR / Path(filename).name
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True)


@app.route('/reports/download-all')
@login_required
def download_all():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(OUT_DIR.glob('*.html')):
            zf.write(f, f.name)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, download_name='mister_wiz_reports.zip')


if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    port = int(os.environ.get('PORT', '5000'))
    app.run(debug=debug, host='0.0.0.0', port=port)
