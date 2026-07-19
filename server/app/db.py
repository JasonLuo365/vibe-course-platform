from sqlalchemy import create_engine
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

