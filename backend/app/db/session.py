"""Engine, session factory, and the FastAPI dependency.

Neon Postgres pools connections server-side; from a short-lived request this
wants a modest pool with pre-ping enabled, since Neon may close idle
connections between bursts.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    future=True,
)
"""`pool_pre_ping` costs one round-trip per checkout and buys immunity to
Neon dropping idle connections — the alternative is an intermittent
OperationalError on the first request after a quiet period."""

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)
"""`expire_on_commit=False` so a route can still read an object's attributes
after commit without a second SELECT."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session per request.

    The caller owns the transaction: routes commit explicitly. Audit writes
    must land in the same transaction as the state change they describe, so
    that a rolled-back action cannot leave a phantom audit event claiming it
    happened.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
