import io
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


def _init_teacher_store(monkeypatch, data_dir, teacher_name="Chuck"):
    from auth import UserStore

    store = UserStore(db_store=None, json_path=data_dir / "users.json")
    store.initialize()
    store.ensure_bootstrap_superadmin("admin@test.local", "testpass")
    store.create_teacher("teacher@test.local", "teachpass", teacher_name)
    monkeypatch.setattr(web_app, "user_store", store)


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
    assert response.headers["Location"].endswith("/reports")
    generated = sorted(p.name for p in out_dir.glob("*.html"))
    assert "MASTER_Jane_Doe_report.html" in generated
    assert "MASTER_class_diagnostic.html" in generated


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
