import json
from contextlib import contextmanager

from sqlalchemy import Integer, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class StudentRow(Base):
    __tablename__ = "student_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    row_order: Mapped[int] = mapped_column(Integer, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)


class LessonRow(Base):
    __tablename__ = "lesson_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    row_order: Mapped[int] = mapped_column(Integer, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)


class DatabaseStore:
    def __init__(self, database_url: str):
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://") :]
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def initialize(self):
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self):
        session = Session(self.engine)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def load_students(self):
        return self._load_rows(StudentRow)

    def load_lessons(self):
        return self._load_rows(LessonRow)

    def save_students(self, rows):
        self._replace_rows(StudentRow, rows)

    def save_lessons(self, rows):
        self._replace_rows(LessonRow, rows)

    def _load_rows(self, model):
        with self.session() as session:
            q = select(model).order_by(model.row_order.asc(), model.id.asc())
            records = session.execute(q).scalars().all()
            return [json.loads(r.data_json) for r in records]

    def _replace_rows(self, model, rows):
        with self.session() as session:
            session.query(model).delete()
            payloads = [
                model(row_order=i, data_json=json.dumps(row, ensure_ascii=False))
                for i, row in enumerate(rows)
            ]
            session.add_all(payloads)
