"""Engine, session factory, and the FastAPI dependency.

Neon Postgres pools connections server-side; from a short-lived request this
wants a modest pool with pre-ping enabled, since Neon may close idle
connections between bursts.
"""

from collections.abc import Iterator
from typing import Any

# TODO(step-01): create_engine(settings.database_url, pool_pre_ping=True)
engine: Any = None

# TODO(step-01): sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
SessionLocal: Any = None


def get_db() -> Iterator[Any]:
    """FastAPI dependency yielding a session per request.

    The caller owns the transaction: routes commit explicitly. Audit writes
    must land in the same transaction as the state change they describe, so
    that a rolled-back action cannot leave a phantom audit event claiming it
    happened.
    """
    raise NotImplementedError("step-01: database session")
