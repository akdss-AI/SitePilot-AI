from app.core.config import Settings
from app.db.session import _normalize_database_url


def test_settings_defaults_are_safe():
    s = Settings()
    assert s.app_name == "SitePilot AI"
    assert s.groq_configured is False  # no key set in test env


def test_groq_configured_detects_a_key():
    s = Settings(groq_api_key="test-key-not-real")
    assert s.groq_configured is True


def test_bare_postgres_url_pins_psycopg2_driver():
    # Regression test for the Vercel 500 (2026-11-25): SQLAlchemy 2.1
    # maps a bare postgresql:// URL to the psycopg (v3) driver, which
    # is not installed. The deployed app must always use psycopg2.
    assert (
        _normalize_database_url("postgresql://u:p@host:5432/db")
        == "postgresql+psycopg2://u:p@host:5432/db"
    )
    assert (
        _normalize_database_url("postgres://u:p@host:5432/db")
        == "postgresql+psycopg2://u:p@host:5432/db"
    )
    # Already explicit, and SQLite, pass through untouched.
    assert (
        _normalize_database_url("postgresql+psycopg2://u:p@host:5432/db")
        == "postgresql+psycopg2://u:p@host:5432/db"
    )
    assert _normalize_database_url("sqlite:///./x.db") == "sqlite:///./x.db"


def test_normalized_url_resolves_to_psycopg2_dialect():
    # End-to-end proof: with the latest SQLAlchemy installed, a bare
    # URL fails at create_engine, the normalized one builds a
    # psycopg2 engine. No connection is opened. Note: dialect.name is
    # "postgresql" for every Postgres driver; the driver is what
    # distinguishes psycopg2 from psycopg.
    from sqlalchemy import create_engine

    engine = create_engine(
        _normalize_database_url("postgresql://u:p@host:5432/db")
    )
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg2"
