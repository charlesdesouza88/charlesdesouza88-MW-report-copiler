from form_ui import (
    NIVEL_CHOICES,
    format_class_schedule,
    is_valid_nivel,
    is_valid_weekday,
    parse_time_range_from_horario,
    turma_code_from_nivel,
)


def test_nivel_choices():
    assert 'KIDS 1' in NIVEL_CHOICES
    assert 'TEENS 5' in NIVEL_CHOICES
    assert len(NIVEL_CHOICES) == 9


def test_turma_code_from_nivel():
    assert turma_code_from_nivel('KIDS 1') == 'KIDS_1'
    assert turma_code_from_nivel('TEENS 3') == 'TEENS_3'


def test_is_valid_nivel():
    assert is_valid_nivel('KIDS 2')
    assert not is_valid_nivel('Adults Book 4')


def test_is_valid_weekday():
    assert is_valid_weekday('Terça-feira')
    assert not is_valid_weekday('Feriado')


def test_format_class_schedule():
    assert format_class_schedule(
        ['Terça-feira', 'Quinta-feira'], '19:00', '20:00',
    ) == 'Terça-feira e Quinta-feira 19:00 - 20:00'
    assert format_class_schedule([], '19:00', '20:00') == '19:00 - 20:00'


def test_parse_time_range_from_horario():
    assert parse_time_range_from_horario('Terça e quinta, 19:00 - 20:00') == (
        '19:00', '20:00',
    )
    assert parse_time_range_from_horario('Tue 19:00') == ('', '')
