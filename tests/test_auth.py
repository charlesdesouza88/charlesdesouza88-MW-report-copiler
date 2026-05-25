import app as web_app
from auth import (
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


def test_user_store_create_teacher(tmp_path):
    store = UserStore(json_path=tmp_path / 'users.json')
    store.initialize()
    store.ensure_bootstrap_superadmin('boss@test.local', 'secret1')
    store.create_teacher('chuck@test.local', 'secret2', 'Chuck')
    user = store.authenticate('chuck@test.local', 'secret2')
    assert user is not None
    assert user['role'] == ROLE_TEACHER
    assert user['teacher_name'] == 'Chuck'


def test_teacher_cannot_access_upload(monkeypatch, tmp_path):
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

    client = web_app.app.test_client()
    client.post('/login', data={'email': 't@test.local', 'password': 'pass123'})
    response = client.get('/upload')
    assert response.status_code == 403


def test_teacher_turmas():
    assert teacher_turmas(_students(), 'Chuck') == {'MASTER'}
