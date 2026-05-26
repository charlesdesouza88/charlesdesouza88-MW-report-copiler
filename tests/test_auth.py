import io

import app as web_app
from auth import (
    ROLE_SUPERADMIN,
    ROLE_TEACHER,
    UserStore,
    filter_lessons_for_user,
    filter_reports_for_user,
    filter_students_for_user,
    teacher_turmas,
)


def _students():
    return [
        {'teacher': 'Chuck', 'turma': 'MASTER', 'student_name': 'Jane'},
        {'teacher': 'Ana', 'turma': 'KIDS', 'student_name': 'Bob'},
    ]


def _lessons():
    return [
        {'turma': 'MASTER', 'aula_num': '1'},
        {'turma': 'KIDS', 'aula_num': '1'},
    ]


def test_filter_students_teacher_scope():
    user = {'role': ROLE_TEACHER, 'teacher_name': 'Chuck'}
    visible = filter_students_for_user(_students(), user)
    assert len(visible) == 1
    assert visible[0]['turma'] == 'MASTER'


def test_filter_students_excludes_other_teachers_in_same_turma():
    students = [
        {'teacher': 'Chuck', 'turma': 'MASTER', 'student_name': 'Jane'},
        {'teacher': 'Barbara', 'turma': 'MASTER', 'student_name': 'Bob'},
    ]
    user = {'role': ROLE_TEACHER, 'teacher_name': 'Chuck'}
    visible = filter_students_for_user(students, user)
    assert len(visible) == 1
    assert visible[0]['student_name'] == 'Jane'


def test_filter_lessons_teacher_scope():
    user = {'role': ROLE_TEACHER, 'teacher_name': 'Chuck'}
    visible = filter_lessons_for_user(_lessons(), _students(), user)
    assert len(visible) == 1
    assert visible[0]['turma'] == 'MASTER'


def test_filter_reports_teacher_scope(tmp_path):
    user = {'role': ROLE_TEACHER, 'teacher_name': 'Chuck'}
    students = _students()
    master = tmp_path / 'MASTER_Jane_report.html'
    kids = tmp_path / 'KIDS_Bob_report.html'
    master.write_text('x', encoding='utf-8')
    kids.write_text('y', encoding='utf-8')
    allowed = filter_reports_for_user([master, kids], students, user)
    assert [p.name for p in allowed] == ['MASTER_Jane_report.html']


def test_filter_reports_excludes_same_turma_other_teacher(tmp_path):
    user = {'role': ROLE_TEACHER, 'teacher_name': 'Chuck'}
    students = [
        {'teacher': 'Chuck', 'turma': 'MASTER', 'student_name': 'Jane'},
        {'teacher': 'Barbara', 'turma': 'MASTER', 'student_name': 'Bob'},
    ]
    jane = tmp_path / 'MASTER_Jane_report.html'
    bob = tmp_path / 'MASTER_Bob_report.html'
    jane.write_text('x', encoding='utf-8')
    bob.write_text('y', encoding='utf-8')
    allowed = filter_reports_for_user([jane, bob], students, user)
    assert [p.name for p in allowed] == ['MASTER_Jane_report.html']


def test_user_store_create_teacher(tmp_path):
    store = UserStore(json_path=tmp_path / 'users.json')
    store.initialize()
    store.ensure_bootstrap_superadmin('boss@test.local', 'secret1')
    store.create_teacher('chuck@test.local', 'secret2', 'Chuck')
    user = store.authenticate('chuck@test.local', 'secret2')
    assert user is not None
    assert user['role'] == ROLE_TEACHER
    assert user['teacher_name'] == 'Chuck'


def test_teacher_can_upload_scoped_csv(monkeypatch, tmp_path):
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    out_dir = tmp_path / 'output'
    out_dir.mkdir()

    store = UserStore(json_path=data_dir / 'users.json')
    store.initialize()
    store.create_teacher('t@test.local', 'pass123', 'Chuck')

    monkeypatch.setattr(web_app, 'DATA_DIR', data_dir)
    monkeypatch.setattr(web_app, 'OUT_DIR', out_dir)
    monkeypatch.setattr(web_app, 'user_store', store)
    monkeypatch.setattr(web_app, 'SUPERADMIN_EMAIL', '')
    monkeypatch.setattr(web_app, 'SUPERADMIN_PASSWORD', '')

    students_csv = (
        'teacher,turma,turma_display,nivel,horario,student_name,participacao,comportamento,'
        'speaking,listening,foco,writing,reading,gramatica,trabalho_equipe,organizacao,'
        'pontualidade,respeito_regras,faltas,missed_aulas,aula_extra,feedback_participacao,'
        'feedback_foco,feedback_trabalho_equipe,recomendacoes,observacao\n'
        'Chuck,MASTER,Masters,,,Jane Doe,,,,,,,,,,,,,,,,,,,,\n'
    )

    client = web_app.app.test_client()
    client.post('/login', data={'email': 't@test.local', 'password': 'pass123'})
    assert client.get('/upload').status_code == 200
    assert client.get('/upload/template/students').status_code == 200
    response = client.post(
        '/upload',
        data={'students': (io.BytesIO(students_csv.encode()), 'students.csv')},
        content_type='multipart/form-data',
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b'Alunos carregado' in response.data
    saved = (data_dir / 'students.csv').read_text(encoding='utf-8')
    assert 'Jane Doe' in saved
    assert 'teacher,turma' in saved


def test_teacher_turmas():
    assert teacher_turmas(_students(), 'Chuck') == {'MASTER'}


def test_apply_env_superadmin_creates_when_missing(tmp_path):
    store = UserStore(json_path=tmp_path / 'users.json')
    store.initialize()
    store.apply_env_superadmin('boss@test.local', 'secret1')
    assert store.authenticate('boss@test.local', 'secret1') is not None


def test_apply_env_superadmin_migrates_sole_superadmin_email(tmp_path):
    store = UserStore(json_path=tmp_path / 'users.json')
    store.initialize()
    store.ensure_bootstrap_superadmin('old@test.local', 'old-pass')
    store.apply_env_superadmin('new@test.local', 'new-pass')
    assert store.authenticate('new@test.local', 'new-pass') is not None
    assert store.get_by_email('old@test.local') is None


def test_apply_env_superadmin_upgrades_existing_email(tmp_path):
    store = UserStore(json_path=tmp_path / 'users.json')
    store.initialize()
    store.create_teacher('boss@test.local', 'teacher-pass', 'Chuck')
    store.apply_env_superadmin('boss@test.local', 'admin-pass')
    user = store.authenticate('boss@test.local', 'admin-pass')
    assert user is not None
    assert store.authenticate('boss@test.local', 'admin-pass')['role'] == ROLE_SUPERADMIN


def test_sync_superadmin_password(tmp_path):
    store = UserStore(json_path=tmp_path / 'users.json')
    store.initialize()
    store.ensure_bootstrap_superadmin('boss@test.local', 'old-pass')
    assert store.authenticate('boss@test.local', 'old-pass')
    store.sync_superadmin_password('boss@test.local', 'new-pass')
    assert store.authenticate('boss@test.local', 'new-pass') is not None
    assert store.authenticate('boss@test.local', 'old-pass') is None
