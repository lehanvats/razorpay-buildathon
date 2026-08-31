"""Settings normalisation.

Pure — no database. Guards the URL rewrite that lets a Neon connection string
be pasted from the dashboard verbatim.
"""

import pytest

from app.config import Settings, _with_psycopg_driver


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # Neon and most managed providers hand out the bare scheme. SQLAlchemy
        # reads it as "use psycopg2", which this project does not install.
        ("postgresql://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgres://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        # Already-qualified URLs are left exactly as they are.
        ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgresql+asyncpg://u:p@h/d", "postgresql+asyncpg://u:p@h/d"),
    ],
)
def test_driver_normalisation(given: str, expected: str) -> None:
    assert _with_psycopg_driver(given) == expected


def test_tls_query_params_survive_normalisation() -> None:
    """A rewrite that dropped these would silently downgrade a hosted
    connection to plaintext, and nothing else in the suite would notice.
    Rewriting the scheme prefix by slicing preserves them; rebuilding the URL
    through `make_url` is the edit that would not.
    """
    url = (
        "postgresql://u:p@ep-x-pooler.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    out = _with_psycopg_driver(url)

    assert out.startswith("postgresql+psycopg://")
    assert "sslmode=require" in out
    assert "channel_binding=require" in out


def test_migrations_prefer_the_direct_endpoint() -> None:
    """Alembic holds session state a transaction pooler does not preserve."""
    settings = Settings(
        database_url="postgresql://u:p@ep-x-pooler.aws.neon.tech/neondb",
        database_url_unpooled="postgresql://u:p@ep-x.aws.neon.tech/neondb",
        _env_file=None,
    )

    assert "-pooler" in settings.database_url
    assert "-pooler" not in settings.migration_database_url


def test_migrations_fall_back_to_the_only_url_when_unpooled_is_unset() -> None:
    """Correct for a plain Postgres with no pooler in front of it."""
    settings = Settings(
        database_url="postgresql://u:p@localhost/recoup",
        database_url_unpooled="",
        _env_file=None,
    )

    assert settings.migration_database_url == settings.database_url
