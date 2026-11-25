"""Database engine and session handling.

The engine is created from DATABASE_URL, so the same code runs against
PostgreSQL in production and SQLite in automated tests. Models must stay
PostgreSQL-compatible (no database-specific column types).
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

settings = get_settings()


def _normalize_database_url(url: str) -> str:
    """Pin the PostgreSQL driver to psycopg2.

    SQLAlchemy 2.1 changed the default driver for bare ``postgresql://``
    URLs from psycopg2 to ``psycopg`` (v3), which is NOT installed here
    (requirements pin psycopg2-binary). A bare URL therefore crashed at
    import on Vercel with ``ModuleNotFoundError: No module named
    'psycopg'`` — while local tests passed, because they use
    ``postgresql+psycopg2://`` explicitly. Rewriting the scheme here
    makes every deployment use the tested driver, whatever URL the
    hosting dashboard hands us (Neon gives a bare ``postgresql://``).
    SQLite URLs pass through untouched.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


database_url = _normalize_database_url(settings.database_url)

# SQLite needs this flag for use across FastAPI's threads; PostgreSQL ignores it.
_connect_args = (
    {"check_same_thread": False}
    if database_url.startswith("sqlite")
    else {}
)

_engine_kwargs = {}
if database_url.startswith("sqlite"):
    # StaticPool keeps one shared connection. Required for ":memory:"
    # databases (Phase 2 tests): with the default pool each new connection
    # would see a different, empty in-memory database.
    _engine_kwargs["poolclass"] = StaticPool
else:
    _engine_kwargs["pool_pre_ping"] = True  # drop dead connections (PostgreSQL)

engine = create_engine(
    database_url,
    connect_args=_connect_args,
    **_engine_kwargs,
)

if database_url.startswith("sqlite"):
    # SQLite (unlike PostgreSQL) does NOT enforce foreign keys unless
    # asked, per connection. Phase 3 relies on FK behaviour (RESTRICT on
    # deliveries, SET NULL on preferred supplier, CASCADE deletes), so
    # turn it on — this makes SQLite tests behave like PostgreSQL here.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
