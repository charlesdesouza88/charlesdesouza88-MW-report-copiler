from form_ui import (
    date_from_form,
    iso_date_to_storage,
    storage_date_to_iso,
    storage_time_to_input,
    time_from_form,
    time_input_to_storage,
)


def test_storage_date_roundtrip():
    iso_short = storage_date_to_iso('13/05')
    assert iso_short.endswith('-05-13')
    assert len(iso_short) == 10

    iso = storage_date_to_iso('10/02/2026')
    assert iso == '2026-02-10'
    assert iso_date_to_storage(iso) == '10/02/2026'


def test_date_from_form_calendar():
    assert date_from_form({'date_picker': '2026-05-13'}) == '13/05/2026'
    assert date_from_form({'date_picker': ''}) == ''


def test_time_picker_roundtrip():
    assert storage_time_to_input('09:30') == '09:30'
    assert time_from_form({'horario': '09:30'}) == '09:30'
    assert time_input_to_storage('14:15') == '14:15'
