import io
from pathlib import Path

import app as web_app


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


def _login(client):
    return client.post("/login", data={"password": "testpass"}, follow_redirects=False)


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
    monkeypatch.setattr(web_app, "ADMIN_PASSWORD", "testpass")
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()

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

    monkeypatch.setattr(web_app, "ADMIN_PASSWORD", "testpass")
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

    monkeypatch.setattr(web_app, "ADMIN_PASSWORD", "testpass")
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", out_dir)
    web_app.DATA_DIR.mkdir(exist_ok=True)

    client = web_app.app.test_client()
    _login(client)

    ok = client.get("/reports/preview/safe.html")
    blocked = client.get("/reports/preview/../secret.txt")

    assert ok.status_code == 200
    assert blocked.status_code == 404


def test_upload_invalid_students_csv_shows_error_and_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "ADMIN_PASSWORD", "testpass")
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()

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
    monkeypatch.setattr(web_app, "ADMIN_PASSWORD", "testpass")
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()

    client = web_app.app.test_client()
    _login(client)

    response = client.get("/upload/template/students")

    assert response.status_code == 200
    assert "attachment;" in response.headers.get("Content-Disposition", "")
    assert "students_template.csv" in response.headers.get("Content-Disposition", "")
    assert b"teacher,turma,turma_display" in response.data


def test_login_page_has_viewport(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")

    client = web_app.app.test_client()
    response = client.get("/login")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="viewport"' in html
    assert "width=device-width" in html


def test_authenticated_shell_has_drawer_markup(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "ADMIN_PASSWORD", "testpass")
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()

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

    monkeypatch.setattr(web_app, "ADMIN_PASSWORD", "testpass")
    monkeypatch.setattr(web_app, "DATA_DIR", data_dir)
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.OUT_DIR.mkdir()

    client = web_app.app.test_client()
    _login(client)
    response = client.get("/students")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "students-table-view" in html
    assert "students-cards-view" in html
    assert "student-card-item" in html


def test_upload_template_lessons_download(monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "ADMIN_PASSWORD", "testpass")
    monkeypatch.setattr(web_app, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(web_app, "OUT_DIR", tmp_path / "output")
    web_app.DATA_DIR.mkdir()
    web_app.OUT_DIR.mkdir()

    client = web_app.app.test_client()
    _login(client)

    response = client.get("/upload/template/lessons")

    assert response.status_code == 200
    assert "lessons_template.csv" in response.headers.get("Content-Disposition", "")
    assert b"turma,aula_num,date,licao_conteudo" in response.data
