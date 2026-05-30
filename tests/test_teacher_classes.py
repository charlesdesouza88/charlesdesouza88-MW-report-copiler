from form_ui import format_class_schedule, turma_code_from_display
from teacher_classes import (
    add_class,
    count_students_in_turma,
    list_for_teacher,
    load_registry,
    remove_class,
    save_registry,
    sync_teacher_classes_from_students,
    update_class,
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
        class_time_start='19:00',
        class_time_end='20:00',
    )
    assert err is None
    assert row['turma'] == 'TEENS_NIGHT'
    assert row['class_weekdays'] == ['Terça-feira', 'Quinta-feira']
    assert row['horario'] == 'Terça-feira e Quinta-feira 19:00 - 20:00'
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
        class_time_start='10:00',
        class_time_end='11:00',
    )
    assert err is not None


def test_add_class_rejects_missing_time():
    data = {}
    _, err = add_class(
        data,
        'Chuck',
        turma_display='No time',
        class_weekdays=['Segunda-feira', 'Quarta-feira'],
        class_time_start='',
        class_time_end='',
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


def test_update_class_changes_schedule():
    data = {}
    add_class(
        data,
        'Chuck',
        turma_display='Old name',
        class_weekdays=['Segunda-feira', 'Quarta-feira'],
        class_time_start='09:00',
        class_time_end='10:00',
        turma='OLD',
    )
    row, err = update_class(
        data,
        'Chuck',
        'OLD',
        turma_display='New name',
        class_weekdays=['Terça-feira', 'Quinta-feira'],
        class_time_start='19:00',
        class_time_end='20:00',
    )
    assert err is None
    assert row['turma'] == 'OLD'
    assert row['turma_display'] == 'New name'
    assert 'Terça-feira e Quinta-feira 19:00 - 20:00' == row['horario']
    listed = list_for_teacher(data, 'Chuck')[0]
    assert listed['turma_display'] == 'New name'


def test_remove_class_without_students():
    data = {}
    add_class(
        data,
        'Chuck',
        turma_display='Empty class',
        class_weekdays=['Segunda-feira', 'Quarta-feira'],
        class_time_start='09:00',
        class_time_end='10:00',
    )
    ok, err = remove_class(data, 'Chuck', 'EMPTY_CLASS', students=[])
    assert err is None
    assert ok is True
    assert list_for_teacher(data, 'Chuck') == []


def test_remove_class_blocked_when_students_linked():
    data = {}
    add_class(
        data,
        'Chuck',
        turma_display='Busy class',
        class_weekdays=['Terça-feira', 'Quinta-feira'],
        class_time_start='19:00',
        class_time_end='20:00',
        turma='BUSY',
    )
    students = [{'teacher': 'Chuck', 'turma': 'BUSY', 'student_name': 'Kid'}]
    assert count_students_in_turma(students, 'Chuck', 'BUSY') == 1
    ok, err = remove_class(data, 'Chuck', 'BUSY', students=students)
    assert ok is False
    assert 'aluno' in err
    assert len(list_for_teacher(data, 'Chuck')) == 1


def test_duplicate_turma_rejected():
    data = {}
    add_class(
        data,
        'Chuck',
        turma_display='Turma A',
        class_weekdays=['Segunda-feira', 'Quarta-feira'],
        class_time_start='09:00',
        class_time_end='10:00',
        turma='TURMA_A',
    )
    _, err = add_class(
        data,
        'Chuck',
        turma_display='Turma A2',
        class_weekdays=['Terça-feira', 'Quinta-feira'],
        class_time_start='10:00',
        class_time_end='11:00',
        turma='TURMA_A',
    )
    assert err is not None
