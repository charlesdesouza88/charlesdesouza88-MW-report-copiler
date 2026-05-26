"""Shared date/time picker helpers (calendar + clock inputs ↔ DD/MM storage)."""

import re
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


def date_from_form(form):
    """Read calendar field and return storage date string."""
    picker = (form.get('date_picker') or '').strip()
    if picker:
        return iso_date_to_storage(picker)

    legacy = (form.get('date') or '').strip()
    if legacy and _ISO_DATE.match(legacy):
        return iso_date_to_storage(legacy)

    return legacy


def time_from_form(form, field='horario'):
    return time_input_to_storage(form.get(field) or '')
