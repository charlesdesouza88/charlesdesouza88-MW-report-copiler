from db_store import DatabaseStore, prepare_database_url


def test_prepare_database_url_adds_ssl_for_postgres():
    url = prepare_database_url("postgres://user:pass@containers.railway.app:5432/railway")
    assert url.startswith("postgresql+psycopg2://")
    assert "sslmode=require" in url


def test_prepare_database_url_leaves_sqlite_untouched():
    url = "sqlite:////tmp/test.db"
    assert prepare_database_url(url) == url


def test_database_store_round_trip(tmp_path):
    db_path = tmp_path / "app.db"
    store = DatabaseStore(f"sqlite:///{db_path}")
    store.initialize()

    students = [
        {"student_name": "Jane Doe", "turma": "MASTER", "speaking": "4"},
        {"student_name": "John Doe", "turma": "MASTER", "speaking": "3"},
    ]
    lessons = [
        {"turma": "MASTER", "aula_num": "1", "date": "01/01", "licao_conteudo": "L1"}
    ]

    store.save_students(students)
    store.save_lessons(lessons)

    assert store.load_students() == students
    assert store.load_lessons() == lessons

    store.check_connection()
