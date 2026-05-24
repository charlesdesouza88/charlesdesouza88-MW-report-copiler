import json
import logging
from contextlib import contextmanager
from urllib.parse import urlparse

from sqlalchemy import Integer, Text, create_engine, select, text

logger = logging.getLogger(__name__)


def prepare_database_url(database_url: str) -> str:
    """Normalize Railway/Heroku Postgres URLs for SQLAlchemy + psycopg2."""
    url = database_url.strip()
    if not url:
        return url

    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://") :]
    elif url.startswith("postgresql://") and "+psycopg2" not in url.split("://", 1)[0]:
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]

    # Railway and most cloud Postgres require SSL; skip for local sqlite tests.
    if url.startswith("postgresql") and "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"

    return url
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
        prepared = prepare_database_url(database_url)
        parsed = urlparse(prepared.replace("postgresql+psycopg2://", "postgresql://", 1))
        logger.info(
            "Connecting to database host=%s port=%s db=%s",
            parsed.hostname,
            parsed.port or 5432,
            (parsed.path or "").lstrip("/") or "(default)",
        )
        engine_kwargs = {"pool_pre_ping": True}
        if prepared.startswith("postgresql"):
            engine_kwargs["connect_args"] = {"sslmode": "require"}
        self.engine = create_engine(prepared, **engine_kwargs)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def initialize(self):
        Base.metadata.create_all(self.engine)

    def check_connection(self):
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))

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
