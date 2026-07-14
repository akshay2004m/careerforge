"""
SQLAlchemy engine / session setup.

- SQLite (dev): enables foreign_keys PRAGMA, WAL for concurrent reads
- Postgres/MySQL (prod): pool_pre_ping + sized pool for scale-out
"""

from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

# backend/ directory (stable regardless of process CWD)
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _resolve_database_url(url: str) -> str:
    """Pin relative SQLite paths to backend/ so all servers share one DB."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url.startswith("sqlite"):
        return url
    # sqlite:///./file.db or sqlite:///file.db (3 slashes = relative)
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    rest = url[len(prefix) :]
    if rest.startswith("/") or (len(rest) > 2 and rest[1] == ":"):
        return url  # absolute posix or windows path
    path = (_BACKEND_DIR / rest.lstrip("./")).resolve()
    return f"sqlite:///{path.as_posix()}"


def _make_engine():
    url = _resolve_database_url(settings.DATABASE_URL)
    if url.startswith("sqlite"):
        eng = create_engine(
            url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )

        @event.listens_for(eng, "connect")
        def _sqlite_on_connect(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            # Enforce FK constraints (off by default in SQLite)
            cursor.execute("PRAGMA foreign_keys=ON")
            # Better concurrent read performance in single-node dev/prod lite
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        return eng

    # Postgres / MySQL production-oriented defaults
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=1800,
    )


engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
