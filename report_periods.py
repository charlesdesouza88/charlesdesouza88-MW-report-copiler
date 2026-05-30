"""Reporting periods (months), snapshots, and month-over-month trends."""

import json
import re
from datetime import datetime
from pathlib import Path

from form_ui import storage_date_to_iso

_MONTH_KEY = re.compile(r'^\d{4}-\d{2}$')
_REPORT_MONTH_IN_NAME = re.compile(r'_(\d{4}-\d{2})_report\.html$')
_CLASS_MONTH_IN_NAME = re.compile(r'_(\d{4}-\d{2})_class_diagnostic\.html$')


def parse_lesson_month(date_str):
    """Return YYYY-MM for a lesson date in DD/MM or DD/MM/YYYY storage format."""
    iso = storage_date_to_iso(date_str)
    if not iso or len(iso) < 7:
        return None
    return iso[:7]


def available_report_months(lessons):
    months = set()
    for lesson in lessons:
        month = parse_lesson_month(lesson.get('date', ''))
        if month:
            months.add(month)
    return sorted(months)


def default_report_month(lessons):
    months = available_report_months(lessons)
    if months:
        return months[-1]
    return datetime.now().strftime('%Y-%m')


def previous_calendar_month(month_key):
    if not _MONTH_KEY.match(month_key or ''):
        return None
    year, month = int(month_key[:4]), int(month_key[5:7])
    if month == 1:
        return f'{year - 1:04d}-12'
    return f'{year:04d}-{month - 1:02d}'


def lesson_in_month(lesson, month_key):
    return parse_lesson_month(lesson.get('date', '')) == month_key


def filter_lessons_by_month(lessons, month_key):
    if not month_key:
        return lessons
    return [lesson for lesson in lessons if lesson_in_month(lesson, month_key)]


def report_month_from_filename(filename):
    name = Path(filename).name
    match = _REPORT_MONTH_IN_NAME.search(name)
    if match:
        return match.group(1)
    match = _CLASS_MONTH_IN_NAME.search(name)
    if match:
        return match.group(1)
    return None


def month_label(month_key):
    if not month_key or not _MONTH_KEY.match(month_key):
        return month_key or ''
    year, month = month_key[:4], int(month_key[5:7])
    names = (
        '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
        'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
    )
    if 1 <= month <= 12:
        return f'{names[month]} {year}'
    return month_key


def student_composite_score(ctx):
    return round(
        (ctx['dev_overall'] + ctx['part_overall'] + ctx['comp_overall'] + ctx['pres_score']) / 4
    )


def _as_int_score(value, default=0):
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compute_month_trend(current_score, report_month, snapshots, turma, student_name):
    """Compare composite score to the previous calendar month's snapshot."""
    prev_month = previous_calendar_month(report_month)
    if not prev_month:
        return _trend('first', None, current_score)

    key = _snapshot_key(turma, student_name, prev_month)
    prior = snapshots.get(key)
    if not prior:
        return _trend('first', None, current_score)

    raw_prior = prior.get('composite_score')
    if raw_prior is None:
        return _trend('first', None, current_score)
    prior_score = _as_int_score(raw_prior, 0)
    delta = _as_int_score(current_score) - prior_score
    if delta > 0:
        return _trend('improved', delta, current_score, prior_score)
    if delta < 0:
        return _trend('declined', delta, current_score, prior_score)
    return _trend('stable', 0, current_score, prior_score)


def _trend(direction, delta, current_score, prior_score=None):
    labels = {
        'improved': 'Melhorou',
        'declined': 'Piorou',
        'stable': 'Estável',
        'first': 'Primeiro período',
    }
    symbols = {
        'improved': '▲',
        'declined': '▼',
        'stable': '→',
        'first': '—',
    }
    return dict(
        direction=direction,
        delta=delta,
        label=labels[direction],
        symbol=symbols[direction],
        current_score=current_score,
        prior_score=prior_score,
    )


def _snapshot_key(turma, student_name, month_key):
    return f'{turma}|{student_name}|{month_key}'


def load_snapshots(path):
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, list):
        return {}
    out = {}
    for row in raw:
        if not isinstance(row, dict):
            continue
        month = (row.get('report_month') or '').strip()
        turma = (row.get('turma') or '').strip()
        name = (row.get('student_name') or '').strip()
        if not month or not turma or not name:
            continue
        out[_snapshot_key(turma, name, month)] = row
    return out


def save_snapshots(path, snapshot_rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot_rows, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def upsert_month_snapshots(path, report_month, students, lessons, build_ctx):
    """Persist composite scores for each student for this reporting month."""
    store = load_snapshots(path)
    for student in students:
        turma = student.get('turma', '').strip()
        name = student.get('student_name', '').strip()
        if not turma or not name:
            continue
        ctx = build_ctx(student, lessons, report_month=report_month)
        composite = student_composite_score(ctx)
        store[_snapshot_key(turma, name, report_month)] = {
            'report_month': report_month,
            'turma': turma,
            'student_name': name,
            'composite_score': composite,
            'dev_overall': ctx['dev_overall'],
            'part_overall': ctx['part_overall'],
            'comp_overall': ctx['comp_overall'],
            'pres_score': ctx['pres_score'],
        }
    save_snapshots(path, list(store.values()))


def individual_report_filename(turma, student_name, report_month=None):
    from report_names import student_report_filename

    return student_report_filename(turma, student_name, report_month)


def class_diagnostic_filename(turma, report_month=None):
    from report_names import class_diagnostic_filename as class_diagnostic_name

    return class_diagnostic_name(turma, report_month)


def filter_report_files_by_month(files, month_key):
    if not month_key:
        return list(files)
    filtered = []
    for path in files:
        file_month = report_month_from_filename(path.name)
        if file_month == month_key:
            filtered.append(path)
    return filtered
