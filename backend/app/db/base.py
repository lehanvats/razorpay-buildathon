"""SQLAlchemy declarative base.

Kept in its own module so Alembic's env.py can import `Base.metadata`
without importing the FastAPI app (which would pull in network clients at
migration time).
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    # TODO(step-01): shared columns/mixins if wanted (created_at, uuid pk)
