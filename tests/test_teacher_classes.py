from form_ui import format_class_schedule, turma_code_from_display
from teacher_classes import (
    add_class,
    list_for_teacher,
    load_registry,
    save_registry,
    sync_teacher_classes_from_students,
)


def test_turma_code_from_display():
    assert turma_code_from_display('Turma terça') == 'TURMA_TERCA'
    assert turma_code_from_display('Kids 2 class') == 'KIDS_2_CLASS'


def test_add_class_two_weekdays(tmp_path):
    path = tmp_path / 'teacher_classes.json'
    data = {}
    row, err = add_class(
        data,
        'Chuck',
        turma_display='Teens night',
        class_weekdays=['Terça-feira', 'Quinta-feira'],
        class_time='19:00',
    )
    assert err is None
    assert row['turma'] == 'TEENS_NIGHT'
    assert row['class_weekdays'] == ['Terça-feira', 'Quinta-feira']
    assert row['horario'] == 'Terça-feira e Quinta-feira 19:00'
    save_registry(path, data)

    rows = list_for_teacher(load_registry(path), 'Chuck')
    assert len(rows) == 1
    assert rows[0]['class_weekdays'] == ['Terça-feira', 'Quinta-feira']


def test_add_class_rejects_same_weekday():
    data = {}
    _, err = add_class(
        data,
        'Chuck',
        turma_display='Dup',
        class_weekdays=['Segunda-feira', 'Segunda-feira'],
        class_time='10:00',
    )
    assert err is not None


def test_add_class_rejects_missing_time():
    data = {}
    _, err = add_class(
        data,
        'Chuck',
        turma_display='No time',
        class_weekdays=['Segunda-feira', 'Quarta-feira'],
        class_time='',
    )
    assert err is not None


def test_sync_imports_turmas_from_existing_students():
    data = {}
    students = [
        {
            'teacher': 'Chuck',
            'turma': 'LIVE_FLOW',
            'turma_display': 'Book 1',
            'nivel': 'Book 1',
            'horario': 'Mon 10:00',
        },
        {
            'teacher': 'Chuck',
            'turma': 'MASTER',
            'turma_display': 'Masters',
            'nivel': 'Adults Book 4',
            'horario': 'Tue 19:00',
        },
        {'teacher': 'Ana', 'turma': 'OTHER', 'turma_display': 'X', 'nivel': '', 'horario': ''},
    ]
    added = sync_teacher_classes_from_students(data, 'Chuck', students)
    assert added == 2
    rows = list_for_teacher(data, 'Chuck')
    codes = {r['turma'] for r in rows}
    assert codes == {'LIVE_FLOW', 'MASTER'}
    master = next(r for r in rows if r['turma'] == 'MASTER')
    assert master['turma_display'] == 'Masters'
    live = next(r for r in rows if r['turma'] == 'LIVE_FLOW')
    assert live['turma_display'] == 'LIVE FLOW'
    assert live['horario'] == 'Mon 10:00'
    assert sync_teacher_classes_from_students(data, 'Chuck', students) == 0


def test_duplicate_turma_rejected():
    data = {}
    add_class(
        data,
        'Chuck',
        turma_display='Turma A',
        class_weekdays=['Segunda-feira', 'Quarta-feira'],
        class_time='09:00',
        turma='TURMA_A',
    )
    _, err = add_class(
        data,
        'Chuck',
        turma_display='Turma A2',
        class_weekdays=['Terça-feira', 'Quinta-feira'],
        class_time='10:00',
        turma='TURMA_A',
    )
    assert err is not None
