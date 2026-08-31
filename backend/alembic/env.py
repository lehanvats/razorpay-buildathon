"""Alembic migration environment.

Imports `Base.metadata` from app.db.base rather than from app.main, so
running a migration does not construct the FastAPI app or its network
clients. Reads the database URL from app.config.settings — never from
alembic.ini — so no connection string is ever committed.
"""

# TODO(step-01): standard alembic env wiring
#   from app.config import settings
#   from app.db.base import Base
#   import app.db.models  # noqa: F401  -- registers models on the metadata
#   target_metadata = Base.metadata
#   config.set_main_option("sqlalchemy.url", settings.database_url)
