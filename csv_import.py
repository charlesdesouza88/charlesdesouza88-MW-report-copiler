"""Convert teacher spreadsheet exports into MW report compiler CSV rows."""

import csv
import io
import re
import unicodedata
from pathlib import Path

from extra_sessions import EXTRA_SESSION_FIELDS, parse_import_csv

STUDENT_FIELDS = [
    'teacher', 'turma', 'turma_display', 'nivel', 'horario', 'student_name',
    'participacao', 'comportamento', 'speaking', 'listening', 'foco',
    'writing', 'reading', 'gramatica', 'trabalho_equipe', 'organizacao',
    'pontualidade', 'respeito_regras', 'faltas', 'missed_aulas', 'aula_extra',
    'feedback_participacao', 'feedback_foco', 'feedback_trabalho_equipe',
    'recomendacoes', 'observacao',
]

LESSON_FIELDS = [
    'turma', 'aula_num', 'date', 'licao_conteudo', 'atividade_extra', 'habilidades',
]

STUDENT_HEADER_MAP = {
    'professor': 'teacher',
    'codigo turma': 'turma',
    'código turma': 'turma',
    'nome exibido': 'turma_display',
    'nivel': 'nivel',
    'nível / livro': 'nivel',
    'horario': 'horario',
    'horário': 'horario',
    'nome do aluno': 'student_name',
    'participacao': 'participacao',
    'participação': 'participacao',
    'comportamento': 'comportamento',
    'speaking': 'speaking',
    'fala': 'speaking',
    'listening': 'listening',
    'audição': 'listening',
    'audicao': 'listening',
    'foco': 'foco',
    'writing': 'writing',
    'escrita': 'writing',
    'reading': 'reading',
    'leitura': 'reading',
    'gramatica': 'gramatica',
    'gramática': 'gramatica',
    'trabalho em equipe': 'trabalho_equipe',
    'trabalho_equipe': 'trabalho_equipe',
    'organizacao': 'organizacao',
    'organização': 'organizacao',
    'pontualidade': 'pontualidade',
    'respeito as regras': 'respeito_regras',
    'respeito às regras': 'respeito_regras',
    'respeito_regras': 'respeito_regras',
    'faltas': 'faltas',
    'aulas perdidas': 'missed_aulas',
    'missed_aulas': 'missed_aulas',
    'aula extra': 'aula_extra',
    'aula_extra': 'aula_extra',
    'feedback participacao': 'feedback_participacao',
    'feedback — participação': 'feedback_participacao',
    'feedback participação': 'feedback_participacao',
    'feedback_participacao': 'feedback_participacao',
    'feedback foco': 'feedback_foco',
    'feedback — foco': 'feedback_foco',
    'feedback_foco': 'feedback_foco',
    'feedback equipe': 'feedback_trabalho_equipe',
    'feedback — equipe': 'feedback_trabalho_equipe',
    'feedback_trabalho_equipe': 'feedback_trabalho_equipe',
    'recomendacoes': 'recomendacoes',
    'recomendações': 'recomendacoes',
    'observacao': 'observacao',
    'observação': 'observacao',
}

LESSON_HEADER_MAP = {
    'turma': 'turma',
    'codigo turma': 'turma',
    'código turma': 'turma',
    'aula_num': 'aula_num',
    'nº da aula': 'aula_num',
    'no da aula': 'aula_num',
    'numero da aula': 'aula_num',
    'número da aula': 'aula_num',
    'date': 'date',
    'data': 'date',
    'licao_conteudo': 'licao_conteudo',
    'conteudo da licao': 'licao_conteudo',
    'conteúdo da lição': 'licao_conteudo',
    'lição + conteúdo': 'licao_conteudo',
    'licao + conteudo': 'licao_conteudo',
    'atividade_extra': 'atividade_extra',
    'atividade extra': 'atividade_extra',
    'habilidades': 'habilidades',
}


def _norm_header(value):
    text = unicodedata.normalize('NFKD', (value or '').strip())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold().replace('\ufeff', '')


def _norm_cell(value):
    return (value or '').strip()


def _map_row(raw, header_map, fields):
    mapped = {}
    for key, value in raw.items():
        if key is None:
            continue
        field = header_map.get(_norm_header(key))
        if field:
            mapped[field] = _norm_cell(value)
    if all(field in mapped for field in fields):
        return {field: mapped.get(field, '') for field in fields}
    return None


def parse_students_csv(text):
    """Accept compiler-format or Portuguese-header student spreadsheets."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ['CSV sem cabeçalho válido.']

    headers = [_norm_header(name) for name in reader.fieldnames if name]
    if headers == [_norm_header(field) for field in STUDENT_FIELDS]:
        rows = []
        for raw in reader:
            row = {field: _norm_cell(raw.get(field, '')) for field in STUDENT_FIELDS}
            if any(row.values()):
                rows.append(row)
        if not rows:
            return [], ['CSV sem linhas de dados.']
        return rows, []

    rows = []
    for raw in reader:
        if not any(_norm_cell(v) for v in raw.values() if v is not None):
            continue
        row = _map_row(raw, STUDENT_HEADER_MAP, STUDENT_FIELDS)
        if row:
            rows.append(row)

    if not rows:
        return [], ['Nenhuma linha de aluno reconhecida — use o template students.csv ou cabeçalhos em português.']
    return rows, []


def parse_lessons_csv(text):
    """Accept compiler-format lesson CSV rows."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ['CSV sem cabeçalho válido.']

    headers = [_norm_header(name) for name in reader.fieldnames if name]
    if headers == [_norm_header(field) for field in LESSON_FIELDS]:
        rows = []
        for raw in reader:
            row = {field: _norm_cell(raw.get(field, '')) for field in LESSON_FIELDS}
            if row.get('turma') and row.get('aula_num'):
                rows.append(row)
        if not rows:
            return [], ['CSV sem linhas de dados.']
        return rows, []

    rows = []
    for raw in reader:
        if not any(_norm_cell(v) for v in raw.values() if v is not None):
            continue
        row = _map_row(raw, LESSON_HEADER_MAP, LESSON_FIELDS)
        if row and row.get('turma') and row.get('aula_num'):
            rows.append(row)

    if not rows:
        return [], ['Nenhuma linha de aula reconhecida — use lessons.csv ou um plano de aula exportado.']
    return rows, []


def parse_turma_from_plan_header(header):
    """Extract turma code from headers like 'SPARK - KIDS 1 (Segunda e quarta, 8:00-9:30)'."""
    text = _norm_cell(header)
    match = re.match(r'^([A-Za-z0-9]+)\s*-\s*', text)
    if match:
        return match.group(1).upper()
    return text.upper()


def parse_lesson_plan_csv(text):
    """Parse teacher lesson-plan exports with a title row + DATA/LIÇÃO header row."""
    rows_raw = list(csv.reader(io.StringIO(text)))
    header_idx = None
    turma = ''

    for idx, row in enumerate(rows_raw):
        if len(row) > 2 and _norm_header(row[2]) == 'data':
            header_idx = idx
            if idx >= 1 and len(rows_raw[idx - 1]) > 1:
                turma = parse_turma_from_plan_header(rows_raw[idx - 1][1])
            break

    if header_idx is None:
        return [], ['Plano de aula não reconhecido — falta a linha de cabeçalho com DATA e LIÇÃO + CONTEÚDO.']
    if not turma:
        return [], ['Não foi possível identificar a turma no título do plano de aula.']

    rows = []
    for row in rows_raw[header_idx + 1:]:
        if len(row) < 3:
            continue
        aula_num = _norm_cell(row[1] if len(row) > 1 else '')
        date = _norm_cell(row[2] if len(row) > 2 else '')
        if not aula_num or not date:
            continue
        rows.append({
            'turma': turma,
            'aula_num': aula_num,
            'date': date,
            'licao_conteudo': _norm_cell(row[3] if len(row) > 3 else ''),
            'atividade_extra': _norm_cell(row[4] if len(row) > 4 else ''),
            'habilidades': _norm_cell(row[5] if len(row) > 5 else ''),
        })

    if not rows:
        return [], ['Nenhuma aula encontrada no plano de aula.']
    return rows, []


def parse_atendimentos_csv(text):
    """Convert the reference atendimentos spreadsheet into extra-session rows."""
    return parse_import_csv(text)


def merge_lessons(existing_rows, new_rows, turma=None):
    """Replace lessons for one turma, or append when turma is omitted."""
    if turma:
        kept = [row for row in existing_rows if row.get('turma', '').strip().upper() != turma.upper()]
        return kept + new_rows
    return existing_rows + new_rows


def write_csv(path, fieldnames, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def write_students_csv(path, rows):
    write_csv(path, STUDENT_FIELDS, rows)


def write_lessons_csv(path, rows):
    write_csv(path, LESSON_FIELDS, rows)


def write_extra_sessions_csv(path, rows):
    write_csv(path, EXTRA_SESSION_FIELDS, rows)


# ── Teacher report folder (monthly grade sheets + lesson plans) ─────────────

MONTH_SORT_KEYS = {
    'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'março': 3, 'abril': 4,
    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8, 'setembro': 9,
    'outubro': 10, 'novembro': 11, 'dezembro': 12,
}

STUDENT_REPORT_HEADER_MAP = {
    'alunos': 'student_name',
    'participacao': 'participacao',
    'participação': 'participacao',
    'foco': 'foco',
    'comportamento': 'comportamento',
    'speaking': 'speaking',
    'listening': 'listening',
    'writing': 'writing',
    'reading': 'reading',
    'aula extra': 'aula_extra',
    'materias': 'materias',
    'materiais': 'materias',
    'atrasos': 'atrasos',
    'faltas': 'faltas',
    'observacao': 'observacao',
    'observação': 'observacao',
}


def _teacher_display_name(folder_name):
    return (folder_name or '').strip().title()


def month_sort_key_from_filename(filename):
    stem = _norm_header(Path(filename).stem)
    for month, order in MONTH_SORT_KEYS.items():
        if month in stem:
            return order
    return 0


def turma_from_filename(filename, teacher_name=None):
    """Extract turma code from names like 'Bárbara - Março - Rise.csv'."""
    stem = Path(filename).stem
    parts = [part.strip() for part in re.split(r'\s*-\s*', stem) if part.strip()]
    teacher_key = _norm_header(teacher_name or '')
    skip = set(MONTH_SORT_KEYS.keys())
    if teacher_key:
        skip.add(teacher_key)
        skip.add(_norm_header(_teacher_display_name(teacher_name or '')))
    candidates = [
        part for part in parts
        if _norm_header(part) not in skip and _norm_header(part) not in ('plano de aula', 'planejamento de aula')
    ]
    if not candidates:
        return ''
    return candidates[-1].upper()


def turma_from_class_header(header):
    text = _norm_cell(header)
    match = re.search(r'-\s*([A-Za-z0-9]+)', text)
    if match:
        return match.group(1).upper()
    return parse_turma_from_plan_header(text)


def horario_from_header(header):
    match = re.search(r'\(([^)]+)\)', header or '')
    return match.group(1).strip() if match else ''


def nivel_from_class_header(header):
    text = _norm_cell(header)
    match = re.match(r'^[A-Za-z0-9]+\s*-\s*(.+?)(?:\s*\(|$)', text)
    if not match:
        return ''
    value = match.group(1).strip()
    level_hint = _norm_header(value)
    if any(token in level_hint for token in ('kids', 'teens', 'adults', 'book', 'nivel', 'nível')):
        return value.title()
    if re.search(r'\d', value):
        return value.title()
    return ''


def lesson_plan_metadata(text):
    """Return turma/nivel/horario parsed from a lesson-plan title row."""
    rows_raw = list(csv.reader(io.StringIO(text)))
    for idx, row in enumerate(rows_raw):
        if len(row) > 2 and _norm_header(row[2]) == 'data' and idx >= 1 and len(rows_raw[idx - 1]) > 1:
            title = rows_raw[idx - 1][1]
            turma = parse_turma_from_plan_header(title)
            if turma and turma not in {'SEGUNDAS', 'TERCAS', 'TERÇAS'}:
                return {
                    'turma': turma,
                    'nivel': nivel_from_class_header(title),
                    'horario': horario_from_header(title),
                }
    return {}


def parse_faltas(value):
    text = _norm_cell(value).casefold()
    if not text:
        return '0'
    match = re.search(r'\d+', text)
    return match.group(0) if match else '0'


def _compose_observacao(raw):
    parts = []
    for label, key in (
        ('Materiais', 'materias'),
        ('Atrasos', 'atrasos'),
    ):
        value = _norm_cell(raw.get(key, ''))
        if value:
            parts.append(f'{label}: {value}')
    note = _norm_cell(raw.get('observacao', ''))
    if note:
        parts.append(note)
    return ' '.join(parts)


def _reader_skip_blank_rows(text):
    lines = text.splitlines()
    while lines:
        reader = csv.reader(io.StringIO('\n'.join(lines)))
        rows = list(reader)
        if rows and any(any(_norm_cell(cell) for cell in row) for row in rows[:3]):
            return rows
        lines = lines[1:]
    return list(csv.reader(io.StringIO(text)))


def parse_teacher_student_report_csv(text, teacher_name, source_filename):
    """Parse monthly teacher grade sheets (Alunos, Participação, Foco, ...)."""
    rows_raw = _reader_skip_blank_rows(text)
    header_idx = None
    for idx, row in enumerate(rows_raw):
        if len(row) > 1 and _norm_header(row[1]) == 'alunos':
            header_idx = idx
            break

    if header_idx is None:
        return [], [f'{source_filename}: cabeçalho "Alunos" não encontrado.']

    title = rows_raw[header_idx - 1][1] if header_idx >= 1 and len(rows_raw[header_idx - 1]) > 1 else ''
    turma = turma_from_filename(source_filename, teacher_name) or turma_from_class_header(title)
    if not turma:
        return [], [f'{source_filename}: não foi possível identificar a turma.']

    header_row = rows_raw[header_idx]
    col_map = {}
    for idx, label in enumerate(header_row):
        field = STUDENT_REPORT_HEADER_MAP.get(_norm_header(label))
        if field:
            col_map[field] = idx

    if 'student_name' not in col_map:
        return [], [f'{source_filename}: coluna Alunos não encontrada.']

    title_turma = turma_from_class_header(title)
    use_title_meta = title_turma == turma
    meta = {
        'turma': turma,
        'nivel': nivel_from_class_header(title) if use_title_meta else '',
        'horario': horario_from_header(title) if use_title_meta else '',
    }
    teacher = _teacher_display_name(teacher_name)
    parsed = []

    for row in rows_raw[header_idx + 1:]:
        if not any(_norm_cell(cell) for cell in row):
            continue
        name_idx = col_map['student_name']
        student_name = _norm_cell(row[name_idx] if len(row) > name_idx else '')
        if not student_name:
            continue
        if student_name.casefold().startswith('nº de alunos'):
            break
        if student_name.casefold().startswith('prazo:'):
            break

        raw = {}
        for field, idx in col_map.items():
            raw[field] = _norm_cell(row[idx] if len(row) > idx else '')

        if not any(raw.get(field) for field in ('participacao', 'foco', 'speaking', 'listening', 'writing', 'reading')):
            continue

        comportamento = raw.get('comportamento') or raw.get('participacao') or '3'
        parsed.append({
            'teacher': teacher,
            'turma': turma,
            'turma_display': turma.title(),
            'nivel': meta['nivel'],
            'horario': meta['horario'],
            'student_name': student_name,
            'participacao': raw.get('participacao', ''),
            'comportamento': comportamento,
            'speaking': raw.get('speaking', ''),
            'listening': raw.get('listening', ''),
            'foco': raw.get('foco', ''),
            'writing': raw.get('writing', ''),
            'reading': raw.get('reading', ''),
            'gramatica': '',
            'trabalho_equipe': comportamento,
            'organizacao': comportamento,
            'pontualidade': comportamento,
            'respeito_regras': comportamento,
            'faltas': parse_faltas(raw.get('faltas', '')),
            'missed_aulas': '',
            'aula_extra': raw.get('aula_extra', ''),
            'feedback_participacao': '',
            'feedback_foco': '',
            'feedback_trabalho_equipe': '',
            'recomendacoes': '',
            'observacao': _compose_observacao(raw),
            '_month_sort': month_sort_key_from_filename(source_filename),
            '_source': source_filename,
        })

    if not parsed:
        return [], [f'{source_filename}: nenhum aluno com notas encontrado.']
    return parsed, []


def classify_teacher_csv(path):
    name = path.name.casefold()
    if 'attendance' in name:
        return 'skip'
    if 'plano de aula' in name or 'planejamento de aula' in name:
        return 'lessons'
    return 'students'


def _apply_lesson_metadata(student_rows, turma_meta):
    for row in student_rows:
        meta = turma_meta.get(row['turma'], {})
        if not row.get('nivel'):
            row['nivel'] = meta.get('nivel', '')
        if not row.get('horario'):
            row['horario'] = meta.get('horario', '')


def _dedupe_student_rows(rows):
    best = {}
    for row in rows:
        key = (row['teacher'].casefold(), row['turma'].upper(), row['student_name'].casefold())
        month_sort = row.get('_month_sort', 0)
        current = best.get(key)
        if current is None or month_sort >= current.get('_month_sort', 0):
            best[key] = row
    return list(best.values())


def convert_teacher_folder(teacher_dir):
    teacher_dir = Path(teacher_dir)
    teacher_name = teacher_dir.name
    student_rows = []
    lesson_rows = []
    turma_meta = {}
    warnings = []

    lesson_files = []
    student_files = []

    for path in sorted(teacher_dir.glob('*.csv')):
        kind = classify_teacher_csv(path)
        if kind == 'lessons':
            lesson_files.append(path)
        elif kind == 'students':
            student_files.append(path)

    for path in lesson_files:
        if 'geral' in path.name.casefold():
            continue
        text = path.read_text(encoding='utf-8-sig')
        meta = lesson_plan_metadata(text)
        if meta.get('turma'):
            turma_meta[meta['turma']] = meta
        rows, errors = parse_lesson_plan_csv(text)
        if errors:
            warnings.extend(errors)
            continue
        lesson_rows = merge_lessons(lesson_rows, rows, turma=rows[0]['turma'])

    for path in student_files:
        rows, errors = parse_teacher_student_report_csv(
            path.read_text(encoding='utf-8-sig'),
            teacher_name,
            path.name,
        )
        if errors:
            warnings.extend(errors)
            continue
        student_rows.extend(rows)

    _apply_lesson_metadata(student_rows, turma_meta)
    student_rows = _dedupe_student_rows(student_rows)
    for row in student_rows:
        row.pop('_month_sort', None)
        row.pop('_source', None)

    return student_rows, lesson_rows, warnings


def convert_teacher_reports_root(root_dir):
    root_dir = Path(root_dir)
    all_students = []
    all_lessons = []
    warnings = []

    for teacher_dir in sorted(path for path in root_dir.iterdir() if path.is_dir()):
        students, lessons, notes = convert_teacher_folder(teacher_dir)
        all_students.extend(students)
        for turma in {row['turma'] for row in lessons}:
            turma_rows = [row for row in lessons if row['turma'] == turma]
            all_lessons = merge_lessons(all_lessons, turma_rows, turma=turma)
        warnings.extend(notes)

    return all_students, all_lessons, warnings
