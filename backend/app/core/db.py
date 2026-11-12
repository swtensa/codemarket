"""Подключение к PostgreSQL (SQLAlchemy 2.0, синхронный стиль)."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Сессия на запрос. Изменения фиксирует роутер (db.commit()), при ошибке всё откатывается."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
