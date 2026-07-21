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
    _upgrade_existing_schema()
    Base.metadata.create_all(_engine)
    # The MVP deliberately has no migration dependency.  Keep additions to
    # the report-release state compatible with already-created SQLite files.
    additive_columns = {
        "evaluations": {
            "published_at": "DATETIME",
            "published_by_teacher_id": "INTEGER",
            "prompt_profile": "VARCHAR",
            "prompt_instructions": "VARCHAR",
        },
        "group_evaluations": {
            "published_at": "DATETIME",
            "published_by_teacher_id": "INTEGER",
            "prompt_version": "VARCHAR",
            "prompt_profile": "VARCHAR",
            "prompt_instructions": "VARCHAR",
        },
        "assignments": {
            "evaluation_profile": "VARCHAR",
            "evaluation_instructions": "VARCHAR",
        },
        "course_enrollments": {
            "enrollment_code": "VARCHAR",
        },
    }
    with _engine.begin() as conn:
        inspector = inspect(_engine)
        for table, additions in additive_columns.items():
            columns = {column["name"] for column in inspector.get_columns(table)}
            for name, sql_type in additions.items():
                if name not in columns:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def _upgrade_existing_schema():
    """Apply small idempotent upgrades needed by existing SQLite databases."""
    if _engine is None or _engine.dialect.name != "sqlite":
        return
    inspector = inspect(_engine)
    if "students" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("students")}
    if "web_session_version" in columns:
        return
    with _engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE students "
                "ADD COLUMN web_session_version INTEGER NOT NULL DEFAULT 1"
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
