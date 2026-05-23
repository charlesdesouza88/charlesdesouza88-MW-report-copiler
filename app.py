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

app = Flask(__name__, template_folder='web_templates')
app.secret_key = os.environ.get('SECRET_KEY', 'mw-dev-change-in-prod')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')

BASE = Path(__file__).parent
DATA_DIR = BASE / 'data'
TMPL_DIR = BASE / 'templates'
OUT_DIR = BASE / 'output'
OUT_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

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


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def _load_students():
    path = DATA_DIR / 'students.csv'
    return load_csv(path) if path.exists() else []


def _save_students(students):
    with open(DATA_DIR / 'students.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=STUDENT_FIELDS)
        writer.writeheader()
        writer.writerows(students)


# ── Auth ──────────────────────────────────────────────────────────────────────

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


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    students = _load_students()
    lessons_path = DATA_DIR / 'lessons.csv'
    lessons = load_csv(lessons_path) if lessons_path.exists() else []
    reports = sorted(OUT_DIR.glob('*.html'))
    turmas = group_by_turma(students) if students else {}
    individual = [f for f in reports if 'class_diagnostic' not in f.name]
    return render_template('dashboard.html',
        student_count=len(students),
        turma_count=len(turmas),
        lesson_count=len(lessons),
        report_count=len(individual),
        turmas=list(turmas.keys()),
        data_ready=(DATA_DIR / 'students.csv').exists() and lessons_path.exists(),
    )


# ── Students ──────────────────────────────────────────────────────────────────

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


# ── Upload ────────────────────────────────────────────────────────────────────

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    messages = []
    if request.method == 'POST':
        for key, label in [('students', 'Alunos'), ('lessons', 'Aulas')]:
            f = request.files.get(key)
            if f and f.filename:
                f.save(DATA_DIR / f'{key}.csv')
                messages.append(f'{label} carregado: {f.filename}')
    students_exists = (DATA_DIR / 'students.csv').exists()
    lessons_exists = (DATA_DIR / 'lessons.csv').exists()
    return render_template('upload.html', messages=messages,
        students_exists=students_exists, lessons_exists=lessons_exists)


@app.route('/upload/download/<name>')
@login_required
def download_csv(name):
    if name not in ('students', 'lessons'):
        abort(404)
    path = DATA_DIR / f'{name}.csv'
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=f'{name}.csv')


# ── Generate & Reports ────────────────────────────────────────────────────────

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    students = load_csv(DATA_DIR / 'students.csv')
    lessons = load_csv(DATA_DIR / 'lessons.csv')
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
    app.run(debug=True, port=5000)
