from pathlib import Path

from extra_sessions import (
    ATENDIMENTOS_CSV_HEADERS,
    build_atendimentos_template_csv,
    display_status,
    internal_row_to_csv_row,
    is_status_ok,
    normalize_status,
    parse_import_csv,
    parse_session_type,
    parse_turma_from_student_name,
    row_from_form,
)


SAMPLE_CSV = """\
,Nome do aluno ou responsável,Data ,Horário,Assuntos trabalhados,Observação,Turno,Contatado,Marcado,Realizado,Professor
,Jane Test (Comet - A),13/05,09:30,Reforço - vocabulary,FALTOU,Manhã,ok,ok,NÃO,Chuck
,Bob Test (Star - B),04/05,10:00,Reforço - Reposição ate a lição 12,Feito lição 4,Manhã,ok,ok,ok,Chuck
"""


def test_parse_session_type():
    assert parse_session_type('Reforço - ') == 'Reforço'
    assert parse_session_type('Reforço - Reposição ate a lição 12') == 'Reposição'
    assert parse_session_type('Nivelamento oral') == 'Nivelamento'


def test_parse_turma_from_student_name():
    assert parse_turma_from_student_name('Jane (Comet - A)') == 'Comet - A'
    assert parse_turma_from_student_name('Jane (Comet - A) (2)') == 'Comet - A'


def test_parse_import_csv_sample():
    rows, errors = parse_import_csv(SAMPLE_CSV)
    assert not errors
    assert len(rows) == 2
    assert rows[0]['student_name'] == 'Jane Test (Comet - A)'
    assert rows[0]['turma'] == 'Comet - A'
    assert rows[0]['realizado'] == 'NÃO'
    assert rows[0]['contatado'] == 'OK'
    assert rows[1]['marcado'] == 'OK'
    assert rows[0]['teacher'] == 'Chuck'
    assert rows[1]['session_type'] == 'Reposição'


def test_row_from_form():
    row = row_from_form({
        'student_name': 'Ana (MASTER)',
        'teacher': 'Chuck',
        'date': '01/06',
        'horario': '14:00',
        'turno': 'Tarde',
        'session_type': 'Reforço',
        'assuntos': 'Reforço - speaking',
        'observacao': 'ok',
        'contatado': 'ok',
        'marcado': 'ok',
        'realizado': 'OK',
        'turma': '',
    })
    assert row['turma'] == 'MASTER'
    assert row['contatado'] == 'OK'


def test_normalize_status_ok_capitalized():
    assert normalize_status('ok') == 'OK'
    assert normalize_status('OK') == 'OK'
    assert is_status_ok('ok')
    assert display_status('ok') == 'OK'


def test_build_atendimentos_template_csv(tmp_path):
    template_dir = Path(__file__).resolve().parents[1] / 'data' / 'templates'
    text = build_atendimentos_template_csv(template_dir)
    assert text.startswith('\ufeff')
    assert 'Nome do aluno ou responsável' in text
    assert 'Contatado' in text
    assert 'OK' in text
    rows, errors = parse_import_csv(text.lstrip('\ufeff'))
    assert not errors
    assert len(rows) >= 2


def test_build_atendimentos_template_csv_teacher_name(tmp_path):
    text = build_atendimentos_template_csv(tmp_path, teacher_name='Maria')
    assert 'Maria' in text
    rows, _ = parse_import_csv(text.lstrip('\ufeff'))
    assert all(r['teacher'] == 'Maria' for r in rows)


def test_internal_row_to_csv_row():
    row = internal_row_to_csv_row({
        'student_name': 'Ana',
        'turma': 'MASTER',
        'date': '01/06/2026',
        'horario': '10:00',
        'session_type': 'Reforço',
        'assuntos': 'speaking',
        'observacao': 'note',
        'turno': 'Manhã',
        'contatado': 'ok',
        'marcado': '',
        'realizado': 'NÃO',
        'teacher': 'Chuck',
    })
    assert row['Nome do aluno ou responsável'] == 'Ana (MASTER)'
    assert row['Contatado'] == 'OK'
    assert row['Realizado'] == 'NÃO'
    assert set(row.keys()) == set(ATENDIMENTOS_CSV_HEADERS)
