"""SQLAlchemy declarative Base.

Every model in app/models/ inherits from this one Base, so Alembic or
create_all can discover all tables from a single place.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
