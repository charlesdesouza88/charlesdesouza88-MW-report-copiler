"""Parse and normalize reforço / reposição / extra-class scheduling rows."""

import csv
import io
import re
from pathlib import Path

from form_ui import date_from_form, time_from_form

EXTRA_SESSION_FIELDS = [
    'teacher', 'student_name', 'turma', 'date', 'horario', 'turno',
    'session_type', 'assuntos', 'observacao', 'contatado', 'marcado', 'realizado',
]

EXTRA_SESSION_FIELD_LABELS = {
    'teacher': 'Professor',
    'student_name': 'Nome do aluno',
    'turma': 'Turma',
    'date': 'Data',
    'horario': 'Horário',
    'turno': 'Turno',
    'session_type': 'Tipo',
    'assuntos': 'Assuntos trabalhados',
    'observacao': 'Observação',
    'contatado': 'Contatado',
    'marcado': 'Marcado',
    'realizado': 'Realizado',
}

SESSION_TYPE_CHOICES = ('Reforço', 'Reposição', 'Nivelamento', 'Aula extra')

# Portuguese headers for CSV download / import (reference spreadsheet)
ATENDIMENTOS_CSV_HEADERS = [
    'Nome do aluno ou responsável',
    'Data',
    'Horário',
    'Assuntos trabalhados',
    'Observação',
    'Turno',
    'Contatado',
    'Marcado',
    'Realizado',
    'Professor',
]

# Portuguese headers from the reference spreadsheet
IMPORT_HEADER_MAP = {
    'nome do aluno ou responsável': 'student_name',
    'nome do aluno ou responsavel': 'student_name',
    'data': 'date',
    'horário': 'horario',
    'horario': 'horario',
    'assuntos trabalhados': 'assuntos',
    'observação': 'observacao',
    'observacao': 'observacao',
    'turno': 'turno',
    'contatado': 'contatado',
    'marcado': 'marcado',
    'realizado': 'realizado',
    'professor': 'teacher',
}


def _norm_header(value):
    return (value or '').strip().lower().replace('\ufeff', '')


def parse_session_type(assuntos):
    text = (assuntos or '').casefold()
    if 'nivelamento' in text or 'nivelamentos' in text:
        return 'Nivelamento'
    if 'reposição' in text or 'reposicao' in text or 'repos' in text:
        return 'Reposição'
    if 'aula extra' in text:
        return 'Aula extra'
    return 'Reforço'


def parse_turma_from_student_name(student_name):
    """Extract turma hint from names like 'Ana (Comet - A)'."""
    name = (student_name or '').strip()
    match = re.search(r'\(([^)]+)\)\s*(?:\(\d+\))?$', name)
    if match:
        return match.group(1).strip()
    match = re.search(r'\(([^)]+)\)', name)
    if match:
        return match.group(1).strip()
    return ''


def clean_student_display_name(student_name):
    """Remove trailing (2) session markers but keep turma in parentheses."""
    name = (student_name or '').strip()
    name = re.sub(r'\s*\(\d+\)\s*$', '', name)
    return name.strip()


STATUS_OK = 'OK'
STATUS_NO = 'NÃO'

DEFAULT_ATENDIMENTOS_TEMPLATE_ROWS = [
    {
        'Nome do aluno ou responsável': 'Jane Doe (MASTER)',
        'Data': '10/02/2026',
        'Horário': '09:30',
        'Assuntos trabalhados': 'Reforço - revisão de vocabulário da última aula',
        'Observação': 'Substitua pelos dados reais do aluno.',
        'Turno': 'Manhã',
        'Contatado': STATUS_OK,
        'Marcado': STATUS_OK,
        'Realizado': '',
        'Professor': 'Chuck',
    },
    {
        'Nome do aluno ou responsável': 'John Smith (Comet - A)',
        'Data': '12/02/2026',
        'Horário': '14:00',
        'Assuntos trabalhados': 'Reposição - aula perdida (listening e speaking)',
        'Observação': '',
        'Turno': 'Tarde',
        'Contatado': STATUS_OK,
        'Marcado': STATUS_OK,
        'Realizado': STATUS_NO,
        'Professor': 'Amanda',
    },
]


def is_status_ok(value):
    return (value or '').strip().casefold() == 'ok'


def display_status(value):
    """User-facing label for status fields."""
    raw = (value or '').strip()
    if is_status_ok(raw):
        return STATUS_OK
    return raw


def normalize_status(value):
    raw = (value or '').strip()
    if not raw:
        return ''
    low = raw.casefold()
    if low in ('ok', 'sim', 's', 'yes', 'y'):
        return STATUS_OK
    if low in ('não', 'nao', 'n', 'no', 'faltou', 'cancelado'):
        return STATUS_NO
    return raw


def coerce_session_status_fields(row):
    """Normalize legacy lowercase ok in stored rows."""
    for field in ('contatado', 'marcado', 'realizado'):
        if field in row and is_status_ok(row.get(field)):
            row[field] = STATUS_OK
    return row


def student_name_for_csv(row):
    """Format name for spreadsheet import (turma in parentheses when helpful)."""
    name = (row.get('student_name') or '').strip()
    turma = (row.get('turma') or '').strip()
    if turma and f'({turma})' not in name:
        return f'{name} ({turma})' if name else turma
    return name


def internal_row_to_csv_row(row):
    """Map internal storage fields to Portuguese CSV columns."""
    out = {header: '' for header in ATENDIMENTOS_CSV_HEADERS}
    out['Nome do aluno ou responsável'] = student_name_for_csv(row)
    out['Data'] = (row.get('date') or '').strip()
    out['Horário'] = (row.get('horario') or '').strip()
    assuntos = (row.get('assuntos') or '').strip()
    session_type = (row.get('session_type') or '').strip()
    if session_type and session_type.casefold() not in assuntos.casefold():
        assuntos = f'{session_type} - {assuntos}' if assuntos else session_type
    out['Assuntos trabalhados'] = assuntos
    out['Observação'] = (row.get('observacao') or '').strip()
    out['Turno'] = (row.get('turno') or '').strip()
    out['Contatado'] = display_status(row.get('contatado', ''))
    out['Marcado'] = display_status(row.get('marcado', ''))
    out['Realizado'] = display_status(row.get('realizado', ''))
    out['Professor'] = (row.get('teacher') or '').strip()
    return out


def load_atendimentos_template_rows(template_dir):
    path = Path(template_dir) / 'atendimentos_template.csv'
    if path.exists():
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = [dict(r) for r in reader if any((v or '').strip() for v in r.values())]
            if rows:
                return rows
    return [dict(r) for r in DEFAULT_ATENDIMENTOS_TEMPLATE_ROWS]


def build_atendimentos_template_csv(template_dir, teacher_name=None):
    """UTF-8 CSV with BOM for Excel; optional professor column prefill."""
    rows = load_atendimentos_template_rows(template_dir)
    if teacher_name:
        for row in rows:
            row['Professor'] = teacher_name
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=ATENDIMENTOS_CSV_HEADERS, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return '\ufeff' + buf.getvalue()


def row_from_form(form):
    assuntos = form.get('assuntos', '').strip()
    session_type = form.get('session_type', '').strip() or parse_session_type(assuntos)
    student_name = clean_student_display_name(form.get('student_name', ''))
    turma = form.get('turma', '').strip() or parse_turma_from_student_name(student_name)
    return {
        'teacher': form.get('teacher', '').strip(),
        'student_name': student_name,
        'turma': turma,
        'date': date_from_form(form),
        'horario': time_from_form(form),
        'turno': form.get('turno', '').strip(),
        'session_type': session_type,
        'assuntos': assuntos,
        'observacao': form.get('observacao', '').strip(),
        'contatado': normalize_status(form.get('contatado', '')),
        'marcado': normalize_status(form.get('marcado', '')),
        'realizado': normalize_status(form.get('realizado', '')),
    }


def _map_import_row(raw):
    mapped = {}
    for key, value in raw.items():
        if key is None:
            continue
        field = IMPORT_HEADER_MAP.get(_norm_header(key))
        if field:
            mapped[field] = (value or '').strip()
    if not mapped.get('student_name'):
        return None
    assuntos = mapped.get('assuntos', '')
    mapped['session_type'] = parse_session_type(assuntos)
    mapped['student_name'] = clean_student_display_name(mapped['student_name'])
    mapped['turma'] = parse_turma_from_student_name(mapped['student_name'])
    for flag in ('contatado', 'marcado', 'realizado'):
        mapped[flag] = normalize_status(mapped.get(flag, ''))
    for field in EXTRA_SESSION_FIELDS:
        mapped.setdefault(field, '')
    return coerce_session_status_fields(mapped)


def parse_import_csv(text):
    """Read spreadsheet export; returns list of row dicts."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ['CSV sem cabeçalho válido.']

    rows = []
    for raw in reader:
        if not any((v or '').strip() for v in raw.values() if v is not None):
            continue
        row = _map_import_row(raw)
        if row:
            rows.append(row)

    if not rows:
        return [], ['Nenhuma linha de atendimento encontrada no arquivo.']
    return rows, []


def load_reference_csv(path):
    """Load rows from the user's reference file path (for one-off import)."""
    return Path(path).read_text(encoding='utf-8-sig')
