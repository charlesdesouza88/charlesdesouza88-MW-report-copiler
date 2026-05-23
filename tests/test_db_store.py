from db_store import DatabaseStore


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
