"""Safe report filename helpers."""

import re
from pathlib import Path


_SAFE_PART_RE = re.compile(r'[^A-Za-z0-9._-]+')


def safe_report_filename_part(value, fallback):
    """Normalize user-controlled report filename parts to path-safe ASCII."""
    cleaned = _SAFE_PART_RE.sub('_', str(value or '').strip().replace(' ', '_'))
    cleaned = cleaned.strip('._')
    return cleaned or fallback


def student_report_filename(turma, student_name, report_month=None):
    safe_turma = safe_report_filename_part(turma, 'turma')
    safe_name = safe_report_filename_part(student_name, 'student')
    if report_month:
        return f'{safe_turma}_{safe_name}_{report_month}_report.html'
    return f'{safe_turma}_{safe_name}_report.html'


def class_diagnostic_filename(turma, report_month=None):
    safe_turma = safe_report_filename_part(turma, 'turma')
    if report_month:
        return f'{safe_turma}_{report_month}_class_diagnostic.html'
    return f'{safe_turma}_class_diagnostic.html'


def safe_child_path(directory, filename):
    """Return a resolved child path or raise if the filename escapes directory."""
    root = Path(directory).resolve()
    target = (root / Path(filename).name).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f'Unsafe report path: {filename}') from exc
    return target
