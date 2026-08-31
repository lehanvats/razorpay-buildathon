"""SQLAlchemy declarative base.

Kept in its own module so Alembic's env.py can import `Base.metadata`
without importing the FastAPI app (which would pull in network clients at
migration time).
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Explicit constraint naming. Without it Postgres invents index and constraint
# names, Alembic autogenerate produces churn on every run, and a downgrade
# cannot drop a constraint it has no stable name for.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
