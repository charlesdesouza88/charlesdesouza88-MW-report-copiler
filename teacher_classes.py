"""Per-teacher class (turma) registry — created on the dashboard before adding students."""

import json
import logging
from collections import Counter
from pathlib import Path

from auth import normalize_teacher_name
from form_ui import format_class_schedule, is_valid_nivel, normalize_weekdays, turma_code_from_display

logger = logging.getLogger(__name__)


def _empty_registry():
    return {}


def load_registry(path):
    if not path or not Path(path).exists():
        return _empty_registry()
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else _empty_registry()
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning('Could not read teacher classes %s: %s', path, exc)
        return _empty_registry()


def save_registry(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def _weekdays_from_row(row):
    """Support class_weekdays list and legacy single class_weekday / class_date."""
    stored = row.get('class_weekdays')
    if isinstance(stored, list) and stored:
        return normalize_weekdays(stored)
    legacy = (row.get('class_weekday') or row.get('class_date') or '').strip()
    return normalize_weekdays([legacy] if legacy else [])


def _schedule_fields(row):
    weekdays = _weekdays_from_row(row)
    class_time = (row.get('class_time') or '').strip()
    horario = (row.get('horario') or '').strip()
    if not horario and (weekdays or class_time):
        horario = format_class_schedule(weekdays, class_time)
    return weekdays, class_time, horario


def list_for_teacher(data, teacher_name):
    key = normalize_teacher_name(teacher_name)
    if not key:
        return []
    rows = data.get(key) or data.get(key.casefold()) or []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        turma = (row.get('turma') or '').strip()
        if turma:
            weekdays, class_time, horario = _schedule_fields(row)
            out.append({
                'turma': turma,
                'turma_display': (row.get('turma_display') or turma).strip(),
                'class_weekdays': weekdays,
                'class_time': class_time,
                'horario': horario,
                'needs_schedule': len(weekdays) < 2 or not class_time,
            })
    return sorted(out, key=lambda r: (r['turma_display'].casefold(), r['turma']))


def turma_codes_for_teacher(data, teacher_name):
    return {r['turma'] for r in list_for_teacher(data, teacher_name)}


def find_class(data, teacher_name, turma):
    code = (turma or '').strip()
    for row in list_for_teacher(data, teacher_name):
        if row['turma'] == code:
            return row
    return None


def add_class(
    data,
    teacher_name,
    *,
    turma_display,
    class_weekdays=None,
    class_time='',
    horario='',
    turma='',
):
    """
    Register a new turma for a teacher. Returns (row, None) or (None, error_message).
    Livro/nível is chosen per student. Turma id is generated from the display name.
    """
    key = normalize_teacher_name(teacher_name)
    if not key:
        return None, 'Professor não identificado.'

    display = (turma_display or '').strip()
    if not display:
        return None, 'Informe o nome da turma.'

    weekdays = normalize_weekdays(class_weekdays or [])
    if len(weekdays) < 2:
        return None, 'Selecione dois dias da semana diferentes (a turma tem aula 2x por semana).'

    class_time = (class_time or '').strip()
    if not class_time:
        return None, 'Informe o horário da turma.'

    code = (turma or '').strip() or turma_code_from_display(display)
    if not code:
        return None, 'Não foi possível gerar o identificador da turma.'

    horario = (horario or '').strip() or format_class_schedule(weekdays, class_time)

    bucket = data.setdefault(key, [])
    if not isinstance(bucket, list):
        bucket = []
        data[key] = bucket

    for row in bucket:
        if not isinstance(row, dict):
            continue
        if (row.get('turma') or '').strip() == code:
            return None, f'A turma "{display}" já está cadastrada.'

    new_row = {
        'turma': code,
        'turma_display': display,
        'class_weekdays': weekdays,
        'class_time': class_time,
        'horario': horario,
    }
    bucket.append(new_row)
    return new_row, None


def class_display_from_student_rows(student_rows, turma_code):
    """Best-effort class name from existing student CSV rows (not livro/nível)."""
    names = []
    for row in student_rows:
        display = (row.get('turma_display') or '').strip()
        nivel = (row.get('nivel') or '').strip()
        if display and display != nivel and not is_valid_nivel(display):
            names.append(display)
    if names:
        return Counter(names).most_common(1)[0][0]
    return turma_code.replace('_', ' ')


def sync_teacher_classes_from_students(data, teacher_name, students):
    """
    Import turmas that already exist on student rows but not in teacher_classes.json.
    Safe to run on every request (no-op when already synced).
    """
    key = normalize_teacher_name(teacher_name)
    if not key:
        return 0

    existing = turma_codes_for_teacher(data, teacher_name)
    teacher_key = normalize_teacher_name(teacher_name).casefold()
    by_turma = {}
    for row in students:
        if normalize_teacher_name(row.get('teacher', '')).casefold() != teacher_key:
            continue
        code = (row.get('turma') or '').strip()
        if code:
            by_turma.setdefault(code, []).append(row)

    bucket = data.setdefault(key, [])
    if not isinstance(bucket, list):
        bucket = []
        data[key] = bucket

    added = 0
    for code, rows in sorted(by_turma.items()):
        if code in existing:
            continue
        horario = ''
        for row in rows:
            candidate = (row.get('horario') or '').strip()
            if candidate:
                horario = candidate
                break
        bucket.append({
            'turma': code,
            'turma_display': class_display_from_student_rows(rows, code),
            'class_weekdays': [],
            'class_time': '',
            'horario': horario,
            'legacy_import': True,
        })
        existing.add(code)
        added += 1
        logger.info('Legacy turma imported for %s: %s', key, code)

    return added
