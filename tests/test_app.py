import io
import json
from pathlib import Path

import app as web_app
from auth import UserStore


def _students_csv():
    return (
        "teacher,turma,turma_display,nivel,horario,student_name,participacao,comportamento,speaking,listening,foco,writing,reading,gramatica,trabalho_equipe,organizacao,pontualidade,respeito_regras,faltas,missed_aulas,aula_extra,feedback_participacao,feedback_foco,feedback_trabalho_equipe,recomendacoes,observacao\n"
        "Chuck,MASTER,Masters,Adults Book 4,Tue 19:00,Jane Doe,4,3,4,5,4,3,4,2,3,3,3,3,1,2,Reposicao,Good,Focus,Team,Practice speaking,\n"
    )


def _lessons_csv():
    return (
        "turma,aula_num,date,licao_conteudo,atividade_extra,habilidades\n"
        "MASTER,1,01/01,Lesson 1,,\n"
        "MASTER,2,03/01,Lesson 2,,\n"
    )


def _init_user_store(monkeypatch, data_dir):
    from auth import UserStore

    store = UserStore(db_store=None, json_path=data_dir / "users.json")
    store.initialize()
    store.ensure_bootstrap_superadmin("admin@test.local", "testpass")
    monkeypatch.setattr(web_app, "user_store", store)
    monkeypatch.setattr(web_app, "SUPERADMIN_EMAIL", "admin@test.local")
    monkeypatch.setattr(web_app, "SUPERADMIN_PASSWORD", "testpass")


def _login(client, email="admin@test.local", password="testpass"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def _seed_teacher_classes(data_dir, teacher_name, *entries):
    """entries: (turma, turma_display) or (turma, turma_display, day1, day2, time)."""
    from auth import normalize_teacher_name
    from form_ui import format_class_schedule
    from teacher_classes import load_registry, save_registry

    path = data_dir / "teacher_classes.json"
    data = load_registry(path)
    key = normalize_teacher_name(teacher_name)
    bucket = data.setdefault(key, [])
    for entry in entries:
        turma, display = entry[0], entry[1]
        weekdays = list(entry[2:4]) if len(entry) > 2 else []
        bucket.append({
            "turma": turma,
            "turma_display": display or turma,
            "class_weekdays": weekdays,
            "class_time": entry[4] if len(entry) > 4 else "19:00",
            "horario": format_class_schedule(weekdays, entry[4] if len(entry) > 4 else "19:00")
            if weekdays else "",
        })
    save_registry(path, data)
    return path


def _init_teacher_store(monkeypatch, data_dir, teacher_name="Chuck"):
    from auth import UserStore

    store = UserStore(db_store=None, json_path=data_dir / "users.json")
    store.initialize()
    store.ensure_bootstrap_superadmin("admin@test.local", "testpass")
    store.create_teacher("teacher@test.local", "teachpass", teacher_name)
    monkeypatch.setattr(web_app, "user_store", store)
    classes_path = _seed_teacher_classes(
        data_dir,
        teacher_name,
        ("MASTER", "Masters", "Terça-feira", "Quinta-feira", "19:00"),
    )
    monkeypatch.setattr(web_app, "TEACHER_CLASSES_PATH", classes_path)


def test_health_returns_ok():
    client = web_app.app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "ok"


def test_health_db_csv_mode():
    client = web_app.app.test_client()
    response = client.get("/health/db")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["configured"] is False
    assert payload["mode"] == "csv"


def test_health_auth_omits_account_emails(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, web_app.DATA_DIR)

    client = web_app.app.test_client()
    response = client.get("/health/auth")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["user_count"] == 1
    assert "accounts" not in payload
    assert "configured_email" not in payload
    assert "admin@test.local" not in response.get_data(as_text=True)


def test_login_success_sets_session(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, web_app.DATA_DIR)

    client = web_app.app.test_client()
    response = _login(client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_protected_route_requires_login(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()

    client = web_app.app.test_client()
    response = client.get("/")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_generate_reports_writes_html_files(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "output"
    data_dir.mkdir()
    out_dir.mkdir()
    (data_dir / "students.csv").write_text(_students_csv(), encoding="utf-8")
    (data_dir / "lessons.csv").write_text(_lessons_csv(), encoding="utf-8")

    _init_user_store(monkeypatch, data_dir)
    monkeypatch.setattr(web_app, "BASE", Path(web_app.__file__).parent)
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "TMPL_DIR", Path(web_app.__file__).parent / "templates")
    monkeypatch.setattr(web_app, "OUT_DIR", out_dir)

    client = web_app.app.test_client()
    _login(client)

    response = client.post("/generate", follow_redirects=False)

    assert response.status_code == 302
    assert "/reports" in response.headers["Location"]
    assert "month=" in response.headers["Location"]
    generated = sorted(p.name for p in out_dir.glob("*.html"))
    assert any(name.endswith("_report.html") for name in generated)
    assert any("class_diagnostic" in name for name in generated)


def test_reports_page_with_null_prior_snapshot(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "output"
    data_dir.mkdir()
    out_dir.mkdir()
    (data_dir / "students.csv").write_text(_students_csv(), encoding="utf-8")
    (data_dir / "lessons.csv").write_text(_lessons_csv(), encoding="utf-8")
    (out_dir / "MASTER_Jane_Doe_2026-03_report.html").write_text("<html>ok</html>", encoding="utf-8")
    (data_dir / "student_snapshots.json").write_text(
        json.dumps(
            [
                {
                    'report_month': '2026-03',
                    'turma': 'MASTER',
                    'student_id': '6a03573506b6a182',
                    'composite_score': 4,
                },
                {
                    'report_month': '2026-02',
                    'turma': 'MASTER',
                    'student_id': '6a03573506b6a182',
                    'composite_score': None,
                },
            ],
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )

    _init_user_store(monkeypatch, data_dir)
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", out_dir)
    monkeypatch.setattr(web_app, "SNAPSHOTS_PATH", data_dir / "student_snapshots.json")

    client = web_app.app.test_client()
    _login(client)
    response = client.get("/reports?month=2026-03")

    assert response.status_code == 200
    assert "Jane" in response.get_data(as_text=True)


def test_generate_missing_csv_shows_upload_error(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "output"
    data_dir.mkdir()
    out_dir.mkdir()

    _init_user_store(monkeypatch, data_dir)
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "TMPL_DIR", Path(web_app.__file__).parent / "templates")
    monkeypatch.setattr(web_app, "OUT_DIR", out_dir)

    client = web_app.app.test_client()
    _login(client)
    response = client.post("/generate")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "students.csv não encontrado" in html
    assert "csv-preview-table" in html


def test_generate_invalid_csv_reuses_full_upload_context(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "output"
    data_dir.mkdir()
    out_dir.mkdir()
    (data_dir / "students.csv").write_text("teacher,turma\nChuck,MASTER\n", encoding="utf-8")
    (data_dir / "lessons.csv").write_text(_lessons_csv(), encoding="utf-8")

    _init_user_store(monkeypatch, data_dir)
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "TMPL_DIR", Path(web_app.__file__).parent / "templates")
    monkeypatch.setattr(web_app, "OUT_DIR", out_dir)

    client = web_app.app.test_client()
    _login(client)
    response = client.post("/generate")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "CSV de Alunos invalido" in html
    assert "csv-preview-table" in html


def test_reports_preview_path_is_sanitized(monkeypatch, tmp_path):
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    (out_dir / "safe.html").write_text("<html>ok</html>", encoding="utf-8")

    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", out_dir)
    web_app.DATA_DIR.mkdir(exist_ok=True)
    _init_user_store(monkeypatch, web_app.DATA_DIR)

    client = web_app.app.test_client()
    _login(client)

    ok = client.get("/reports/preview/safe.html")
    blocked = client.get("/reports/preview/../secret.txt")

    assert ok.status_code == 200
    assert blocked.status_code == 404


def test_upload_invalid_students_csv_shows_error_and_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, web_app.DATA_DIR)

    client = web_app.app.test_client()
    _login(client)

    bad_students = io.BytesIO(b"teacher,turma\nChuck,MASTER\n")
    response = client.post(
        "/upload",
        data={"students": (bad_students, "students.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert b"Erro no CSV de Alunos" in response.data
    assert not (web_app.DATA_DIR / "students.csv").exists()


def test_upload_template_students_download(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, web_app.DATA_DIR)

    client = web_app.app.test_client()
    _login(client)

    response = client.get("/upload/template/students")

    assert response.status_code == 200
    assert "attachment;" in response.headers.get("Content-Disposition", "")
    assert "students_template.csv" in response.headers.get("Content-Disposition", "")
    assert response.data.startswith(b"\xef\xbb\xbf")
    assert b"teacher,turma,turma_display" in response.data
    assert b"Jane Doe" in response.data


def test_login_page_has_viewport(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")

    client = web_app.app.test_client()
    response = client.get("/login")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="viewport"' in html
    assert "width=device-width" in html
    assert 'name="email"' in html


def test_authenticated_shell_has_drawer_markup(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, web_app.DATA_DIR)

    client = web_app.app.test_client()
    _login(client)
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="viewport"' in html
    assert 'id="menu-toggle"' in html
    assert 'id="nav-backdrop"' in html
    assert 'class="students-cards-view"' not in html


def test_students_page_has_dual_view_markup(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "students.csv").write_text(_students_csv(), encoding="utf-8")

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, data_dir)

    client = web_app.app.test_client()
    _login(client)
    response = client.get("/students")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "students-table-view" in html
    assert "students-cards-view" in html
    assert "student-card-item" in html


def test_upload_page_shows_csv_template_preview(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, web_app.DATA_DIR)

    client = web_app.app.test_client()
    _login(client)
    response = client.get("/upload")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "csv-preview-table" in html
    assert "Identificação" in html
    assert "Nome do aluno" in html
    assert "Lesson 3: Past tense review" in html


def test_lessons_page_and_teacher_scope(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "students.csv").write_text(_students_csv(), encoding="utf-8")
    (data_dir / "lessons.csv").write_text(
        "turma,aula_num,date,licao_conteudo,atividade_extra,habilidades\n"
        "MASTER,1,01/01,L1,,\n"
        "OTHER,1,01/01,L9,,\n",
        encoding="utf-8",
    )

    store = UserStore(db_store=None, json_path=data_dir / "users.json")
    store.initialize()
    store.create_teacher("chuck@test.local", "pass123", "Chuck")

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    monkeypatch.setattr(web_app, "user_store", store)
    _init_user_store(monkeypatch, data_dir)

    client = web_app.app.test_client()
    client.post("/login", data={"email": "chuck@test.local", "password": "pass123"})
    response = client.get("/lessons")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "MASTER" in html
    assert "L9" not in html

    create = client.post(
        "/lessons/new",
        data={
            "turma": "MASTER",
            "aula_num": "99",
            "date": "01/05/2026",
            "licao_conteudo": "Test lesson",
            "atividade_extra": "",
            "habilidades": "",
        },
        follow_redirects=True,
    )
    assert create.status_code == 200
    assert "Test lesson" in create.get_data(as_text=True)

    blocked = client.post(
        "/lessons/new",
        data={
            "turma": "OTHER",
            "aula_num": "1",
            "date": "01/01",
            "licao_conteudo": "Hack",
            "atividade_extra": "",
            "habilidades": "",
        },
    )
    assert blocked.status_code == 403


def test_teacher_sees_only_own_students(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_text = (
        "teacher,turma,turma_display,nivel,horario,student_name,participacao,comportamento,speaking,listening,foco,writing,reading,gramatica,trabalho_equipe,organizacao,pontualidade,respeito_regras,faltas,missed_aulas,aula_extra,feedback_participacao,feedback_foco,feedback_trabalho_equipe,recomendacoes,observacao\n"
        "Chuck,MASTER,Masters,Book,Tue,Jane Doe,4,3,4,5,4,3,4,2,3,3,3,3,1,2,,,,,,\n"
        "Barbara,MASTER,Masters,Book,Tue,Bob Smith,4,3,4,5,4,3,4,2,3,3,3,3,1,2,,,,,,\n"
    )
    (data_dir / "students.csv").write_text(csv_text, encoding="utf-8")

    store = UserStore(db_store=None, json_path=data_dir / "users.json")
    store.initialize()
    store.create_teacher("chuck@test.local", "pass123", "Chuck")

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    monkeypatch.setattr(web_app, "user_store", store)

    client = web_app.app.test_client()
    client.post("/login", data={"email": "chuck@test.local", "password": "pass123"})
    response = client.get("/students")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Jane Doe" in html
    assert "Bob Smith" not in html


def test_teacher_cannot_create_student_in_other_turma(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "students.csv").write_text(_students_csv(), encoding="utf-8")

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_teacher_store(monkeypatch, data_dir, teacher_name="Chuck")

    client = web_app.app.test_client()
    _login(client, email="teacher@test.local", password="teachpass")
    response = client.post(
        "/students/new",
        data={
            "teacher": "Chuck",
            "turma": "OTHER",
            "student_name": "Mallory",
        },
    )

    assert response.status_code == 200
    assert "não permitida" in response.get_data(as_text=True) or "Dashboard" in response.get_data(as_text=True)
    assert "Mallory" not in (data_dir / "students.csv").read_text(encoding="utf-8")


def test_teacher_creates_turma_on_dashboard(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "students.csv").write_text(_students_csv(), encoding="utf-8")

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_teacher_store(monkeypatch, data_dir, teacher_name="Chuck")

    client = web_app.app.test_client()
    _login(client, email="teacher@test.local", password="teachpass")
    response = client.post(
        "/turmas/create",
        data={
            "turma_display": "Kids segunda",
            "class_weekday_1": "Terça-feira",
            "class_weekday_2": "Quinta-feira",
            "turma_time": "19:30",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    registry = (data_dir / "teacher_classes.json").read_text(encoding="utf-8")
    assert "KIDS_SEGUNDA" in registry
    assert "Kids segunda" in registry
    assert "Terça-feira" in registry
    assert "19:30" in registry


def test_students_page_shows_class_name_not_nivel(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv = (
        "teacher,turma,turma_display,nivel,horario,student_name,participacao,comportamento,"
        "speaking,listening,foco,writing,reading,gramatica,trabalho_equipe,organizacao,"
        "pontualidade,respeito_regras,faltas,missed_aulas,aula_extra,feedback_participacao,"
        "feedback_foco,feedback_trabalho_equipe,recomendacoes,observacao\n"
        "Chuck,TEENS_1,TEENS 1,TEENS 1,Tue 19:00,Kid,3,3,3,3,3,3,3,3,3,3,3,3,0,,,,,,,\n"
    )
    (data_dir / "students.csv").write_text(csv, encoding="utf-8")
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_teacher_store(monkeypatch, data_dir, teacher_name="Chuck")
    from teacher_classes import add_class, load_registry, save_registry

    data = load_registry(web_app.TEACHER_CLASSES_PATH)
    add_class(
        data,
        "Chuck",
        turma_display="Turma Teens noite",
        class_weekdays=["Terça-feira", "Quinta-feira"],
        class_time="19:00",
        turma="TEENS_1",
    )
    save_registry(web_app.TEACHER_CLASSES_PATH, data)

    client = web_app.app.test_client()
    _login(client, email="teacher@test.local", password="teachpass")
    html = client.get("/students").get_data(as_text=True)
    assert "Turma Teens noite" in html
    assert 'data-turma="TEENS_1">Turma Teens noite' in html


def test_teacher_adds_student_to_dashboard_turma(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "students.csv").write_text(_students_csv(), encoding="utf-8")

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_teacher_store(monkeypatch, data_dir, teacher_name="Chuck")
    client = web_app.app.test_client()
    _login(client, email="teacher@test.local", password="teachpass")
    client.post(
        "/turmas/create",
        data={
            "turma_display": "Kids 2 class",
            "class_weekday_1": "Segunda-feira",
            "class_weekday_2": "Quarta-feira",
            "turma_time": "10:00",
        },
    )

    response = client.post(
        "/students/new",
        data={
            "teacher": "Chuck",
            "class_choice": "KIDS_2_CLASS",
            "nivel": "KIDS 2",
            "student_name": "New Class Kid",
            "participacao": "3",
            "comportamento": "3",
            "speaking": "3",
            "listening": "3",
            "foco": "3",
            "writing": "3",
            "reading": "3",
            "gramatica": "3",
            "faltas": "0",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    csv_text = (data_dir / "students.csv").read_text(encoding="utf-8")
    assert "New Class Kid" in csv_text
    assert "KIDS_2_CLASS" in csv_text


def test_teacher_new_student_form_lists_dashboard_turmas(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "students.csv").write_text(_students_csv(), encoding="utf-8")

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_teacher_store(monkeypatch, data_dir, teacher_name="Chuck")

    client = web_app.app.test_client()
    _login(client, email="teacher@test.local", password="teachpass")
    html = client.get("/students/new").get_data(as_text=True)

    assert "Masters" in html
    assert "MASTER" in html
    assert "criar classe" not in html.lower()
    assert "KIDS 1" in html


def test_student_new_requires_turma(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "students.csv").write_text(_students_csv(), encoding="utf-8")

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, data_dir)

    client = web_app.app.test_client()
    _login(client)
    response = client.post(
        "/students/new",
        data={"student_name": "No Turma Kid", "teacher": "Chuck", "turma": ""},
    )

    assert response.status_code == 200
    assert "Informe o nome do aluno e a turma" in response.get_data(as_text=True)


def test_student_new_creates_row(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "students.csv").write_text(_students_csv(), encoding="utf-8")

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, data_dir)

    client = web_app.app.test_client()
    _login(client)
    response = client.post(
        "/students/new",
        data={
            "teacher": "Chuck",
            "turma": "KIDS",
            "student_name": "New Kid",
            "participacao": "3",
            "comportamento": "3",
            "speaking": "3",
            "listening": "3",
            "foco": "3",
            "writing": "3",
            "reading": "3",
            "gramatica": "3",
            "faltas": "0",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/students")
    assert "New Kid" in (data_dir / "students.csv").read_text(encoding="utf-8")


def test_upload_template_lessons_download(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, web_app.DATA_DIR)

    client = web_app.app.test_client()
    _login(client)

    response = client.get("/upload/template/lessons")

    assert response.status_code == 200
    assert "lessons_template.csv" in response.headers.get("Content-Disposition", "")
    assert response.data.startswith(b"\xef\xbb\xbf")
    assert b"turma,aula_num,date,licao_conteudo" in response.data
    assert b"MASTER,2," in response.data


def test_admin_delete_students_csv(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "students.csv").write_text(_students_csv(), encoding="utf-8")

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, data_dir)

    client = web_app.app.test_client()
    _login(client)
    response = client.post("/upload/delete/students", follow_redirects=True)

    assert response.status_code == 200
    assert not (data_dir / "students.csv").exists()
    assert b"alert-success" in response.data
    assert b"arquivo CSV removido" in response.data


def test_teacher_delete_only_own_students(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    mixed = (
        "teacher,turma,turma_display,nivel,horario,student_name,participacao,comportamento,speaking,listening,foco,writing,reading,gramatica,trabalho_equipe,organizacao,pontualidade,respeito_regras,faltas,missed_aulas,aula_extra,feedback_participacao,feedback_foco,feedback_trabalho_equipe,recomendacoes,observacao\n"
        "Chuck,MASTER,Masters,Adults Book 4,Tue 19:00,Jane Doe,4,3,4,5,4,3,4,2,3,3,3,3,1,2,Reposicao,Good,Focus,Team,Practice speaking,\n"
        "Barbara,SPARK,Spark,Teens,Tue 18:00,Bob Smith,3,3,3,3,3,3,3,3,3,3,3,3,0,0,,,,,,\n"
    )
    (data_dir / "students.csv").write_text(mixed, encoding="utf-8")

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_teacher_store(monkeypatch, data_dir, teacher_name="Chuck")

    client = web_app.app.test_client()
    _login(client, email="teacher@test.local", password="teachpass")
    response = client.post("/upload/delete/students", follow_redirects=True)

    assert response.status_code == 200
    assert b"1 registro(s) do seu perfil" in response.data
    remaining = (data_dir / "students.csv").read_text(encoding="utf-8")
    assert "Jane Doe" not in remaining
    assert "Bob Smith" in remaining


def test_teacher_upload_rejects_other_teacher_rows(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_teacher_store(monkeypatch, data_dir)

    bad_csv = _students_csv().replace("Chuck,", "Ana,", 1)

    client = web_app.app.test_client()
    _login(client, email="teacher@test.local", password="teachpass")
    response = client.post(
        "/upload",
        data={"students": (io.BytesIO(bad_csv.encode()), "students.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"teacher deve ser" in response.data
    assert not (data_dir / "students.csv").exists()


def test_extra_sessions_import_and_list(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_user_store(monkeypatch, data_dir)

    csv_body = (
        ",Nome do aluno ou responsável,Data ,Horário,Assuntos trabalhados,Observação,"
        "Turno,Contatado,Marcado,Realizado,Professor\n"
        ",Import Kid (MASTER),01/05,09:00,Reforço - test,,Manhã,ok,ok,ok,Chuck\n"
    )

    client = web_app.app.test_client()
    _login(client)
    response = client.post(
        "/extra-sessions/import",
        data={"file": (io.BytesIO(csv_body.encode("utf-8")), "atendimentos.csv"), "mode": "merge"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"adicionado" in response.data
    assert b"Import Kid" in response.data


def test_teacher_extra_sessions_scoped(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_teacher_store(monkeypatch, data_dir)

    web_app._save_extra_sessions([
        {"teacher": "Chuck", "student_name": "A", "turma": "T1", "date": "1", "horario": "",
         "turno": "", "session_type": "Reforço", "assuntos": "", "observacao": "",
         "contatado": "", "marcado": "", "realizado": ""},
        {"teacher": "Ana", "student_name": "B", "turma": "T2", "date": "2", "horario": "",
         "turno": "", "session_type": "Reforço", "assuntos": "", "observacao": "",
         "contatado": "", "marcado": "", "realizado": ""},
    ])

    client = web_app.app.test_client()
    _login(client, email="teacher@test.local", password="teachpass")
    response = client.get("/extra-sessions")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert ">A</strong>" in html or "student_name\">A" in html
    assert ">B</strong>" not in html


def test_download_atendimentos_template(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_teacher_store(monkeypatch, data_dir)

    client = web_app.app.test_client()
    _login(client, email="teacher@test.local", password="teachpass")
    response = client.get("/extra-sessions/template")
    assert response.status_code == 200
    assert "attachment" in response.headers.get("Content-Disposition", "")
    body = response.get_data(as_text=True)
    assert "Nome do aluno ou responsável" in body
    assert "Chuck" in body


def test_teacher_upload_merges_without_wiping_other_teachers(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "students.csv").write_text(
        _students_csv().replace("Jane Doe", "Bob Smith").replace("Chuck,", "Ana,", 1),
        encoding="utf-8",
    )

    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()
    _init_teacher_store(monkeypatch, data_dir)

    client = web_app.app.test_client()
    _login(client, email="teacher@test.local", password="teachpass")
    response = client.post(
        "/upload",
        data={"students": (io.BytesIO(_students_csv().encode()), "students.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Alunos carregado" in response.data
    text = (data_dir / "students.csv").read_text(encoding="utf-8")
    assert "Jane Doe" in text
    assert "Bob Smith" in text
