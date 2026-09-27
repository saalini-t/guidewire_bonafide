from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """One transaction per `with` block. Commits on clean exit, rolls back
    and re-raises on error. Never wrap an AI/network call inside this.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency (Day 2). Route handlers commit explicitly per
    request via session_scope-style usage inside the route, not here.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
