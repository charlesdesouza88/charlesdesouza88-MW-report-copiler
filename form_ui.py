"""Shared date/time picker helpers (calendar + clock inputs ↔ DD/MM storage)."""

import re
import unicodedata
from datetime import datetime

_ISO_DATE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')
_STORAGE_DATE = re.compile(r'^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$')
_TIME = re.compile(r'^(\d{1,2}):(\d{2})')


def storage_date_to_iso(value):
    """Convert stored DD/MM or DD/MM/YYYY to YYYY-MM-DD for <input type=\"date\">."""
    raw = (value or '').strip().replace('.', '/')
    if not raw:
        return ''

    match = _STORAGE_DATE.match(raw)
    if not match:
        return ''

    day, month, year = match.group(1), match.group(2), match.group(3) or ''
    if year and len(year) == 2:
        year = f'20{year}'
    if not year:
        year = str(datetime.now().year)

    return f'{int(year):04d}-{int(month):02d}-{int(day):02d}'


def iso_date_to_storage(iso_value):
    """Convert YYYY-MM-DD from calendar input to DD/MM/YYYY for CSV storage."""
    raw = (iso_value or '').strip()
    if not raw:
        return ''

    match = _ISO_DATE.match(raw)
    if not match:
        return raw

    year, month, day = match.group(1), match.group(2), match.group(3)
    return f'{int(day):02d}/{int(month):02d}/{year}'


def storage_time_to_input(value):
    """Convert stored time text to HH:MM for <input type=\"time\">."""
    raw = (value or '').strip()
    if not raw:
        return ''

    match = _TIME.search(raw)
    if not match:
        return ''

    return f'{int(match.group(1)):02d}:{match.group(2)}'


def time_input_to_storage(input_value):
    """Normalize clock input to HH:MM."""
    raw = (input_value or '').strip()
    if not raw:
        return ''

    match = _TIME.match(raw)
    if not match:
        return raw

    return f'{int(match.group(1)):02d}:{match.group(2)}'


def date_from_form(form, picker_field='date_picker'):
    """Read calendar field and return storage date string (DD/MM/YYYY)."""
    picker = (form.get(picker_field) or '').strip()
    if picker:
        return iso_date_to_storage(picker)

    if picker_field == 'date_picker':
        legacy = (form.get('date') or '').strip()
        if legacy and _ISO_DATE.match(legacy):
            return iso_date_to_storage(legacy)

    return ''


WEEKDAY_CHOICES = (
    'Segunda-feira',
    'Terça-feira',
    'Quarta-feira',
    'Quinta-feira',
    'Sexta-feira',
    'Sábado',
    'Domingo',
)


def is_valid_weekday(weekday):
    return (weekday or '').strip() in WEEKDAY_CHOICES


def normalize_weekdays(weekdays):
    """Return up to two valid, distinct weekdays in form order."""
    if isinstance(weekdays, str):
        weekdays = [weekdays] if weekdays else []
    out = []
    for raw in weekdays:
        day = (raw or '').strip()
        if not day or not is_valid_weekday(day):
            continue
        if day not in out:
            out.append(day)
    return out[:2]


def format_weekdays_label(weekdays):
    days = normalize_weekdays(weekdays)
    if not days:
        return ''
    if len(days) == 1:
        return days[0]
    return f'{days[0]} e {days[1]}'


def format_class_schedule(weekdays=None, class_time=''):
    """Human-readable schedule line for turma registry (two weekdays + clock time)."""
    if weekdays is None:
        weekdays = []
    day_part = format_weekdays_label(weekdays)
    time_part = (class_time or '').strip()
    if day_part and time_part:
        return f'{day_part} {time_part}'
    return day_part or time_part


def turma_code_from_display(name):
    """Stable turma id from the teacher's class name (e.g. Turma terça → TURMA_TERCA)."""
    raw = (name or '').strip()
    if not raw:
        return ''
    normalized = unicodedata.normalize('NFD', raw)
    ascii_name = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    code = re.sub(r'[^A-Za-z0-9]+', '_', ascii_name).strip('_').upper()
    return code[:48] or 'TURMA'


def time_from_form(form, field='horario'):
    return time_input_to_storage(form.get(field) or '')


NIVEL_CHOICES = (
    'KIDS 1',
    'KIDS 2',
    'KIDS 3',
    'KIDS 4',
    'TEENS 1',
    'TEENS 2',
    'TEENS 3',
    'TEENS 4',
    'TEENS 5',
)


def is_valid_nivel(nivel):
    return (nivel or '').strip() in NIVEL_CHOICES


def turma_code_from_nivel(nivel):
    """Stable turma id for a standard level (e.g. KIDS 1 → KIDS_1)."""
    return (nivel or '').strip().replace(' ', '_')
