from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
SessionLocal = sessionmaker(expire_on_commit=False)


def init_engine(url: str):
    global _engine
    _engine = create_engine(url, connect_args={"check_same_thread": False})
    SessionLocal.configure(bind=_engine)
    return _engine


def create_all():
    from . import models  # noqa: F401  确保模型已注册
    Base.metadata.create_all(_engine)
    additive_columns = {
        "evaluations": {"published_at": "DATETIME", "published_by_teacher_id": "INTEGER"},
        "group_evaluations": {"published_at": "DATETIME", "published_by_teacher_id": "INTEGER"},
    }
    with _engine.begin() as conn:
        inspector = inspect(_engine)
        for table, additions in additive_columns.items():
            columns = {column["name"] for column in inspector.get_columns(table)}
            for name, sql_type in additions.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

