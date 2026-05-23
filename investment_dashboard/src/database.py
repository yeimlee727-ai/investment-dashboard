from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.resolved_database_url, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    from src import models  # noqa: F401

    settings.base_dir.joinpath("db").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_sqlite_migrations()


def _apply_lightweight_sqlite_migrations() -> None:
    if not settings.resolved_database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    migrations: list[str] = []
    if "virtual_orders" in table_names:
        columns = {column["name"] for column in inspector.get_columns("virtual_orders")}
        if "market" not in columns:
            migrations.append("ALTER TABLE virtual_orders ADD COLUMN market VARCHAR(20) DEFAULT 'KR'")
    if "virtual_positions" in table_names:
        columns = {column["name"] for column in inspector.get_columns("virtual_positions")}
        if "market" not in columns:
            migrations.append("ALTER TABLE virtual_positions ADD COLUMN market VARCHAR(20) DEFAULT 'KR'")
    if migrations:
        with engine.begin() as connection:
            for statement in migrations:
                connection.execute(text(statement))


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
