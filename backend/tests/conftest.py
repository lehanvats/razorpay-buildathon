"""Shared pytest fixtures.

Note the split: policy and taxonomy tests need no fixtures at all — they are
pure functions over plain data. Only the webhook and metrics tests touch a
database. Keep it that way; the moment the gate needs a fixture, it has
stopped being pure.

Environment is pinned here, before any `app.*` import, because
`app.config.settings` is instantiated at import time. Tests therefore never
depend on whatever is in the developer's `.env`.
"""

import os
from collections.abc import Iterator

import pytest

TEST_WEBHOOK_SECRET = "test_webhook_secret"

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://recoup:recoup@localhost:55432/recoup_test"

# Must happen before `app.config` is imported anywhere. Real env vars take
# precedence over the .env file in pydantic-settings, so this wins.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
# Also pin the unpooled URL, not just the pooled one: Settings.migration_database_url
# prefers DATABASE_URL_UNPOOLED when it's set, and .env carries a real (Neon)
# value there once a dev has moved onto the pooled endpoint (see BUILD-PLAN.md).
# Left unset, alembic migrations during tests would silently target Neon while
# every actual query — through app.db.session.engine, built from DATABASE_URL —
# still hits the local throwaway Postgres, leaving it permanently one migration
# behind. Empty string falls back to DATABASE_URL, same as in production.
os.environ["DATABASE_URL_UNPOOLED"] = ""
os.environ["RAZORPAY_WEBHOOK_SECRET"] = TEST_WEBHOOK_SECRET

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402


def _ensure_test_database() -> None:
    """Create the test database if it does not exist.

    Connects to the `postgres` maintenance database, since you cannot CREATE
    DATABASE from inside the database being created. AUTOCOMMIT because
    Postgres refuses CREATE DATABASE inside a transaction block.
    """
    url = make_url(os.environ["DATABASE_URL"])
    admin_url = url.set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": url.database},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    """Bring the test database to head.

    Runs the real Alembic migrations rather than `Base.metadata.create_all`,
    so a migration that does not match the models fails the suite instead of
    failing the first deploy.
    """
    from alembic.config import Config

    from alembic import command

    _ensure_test_database()
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@pytest.fixture
def db_session(_migrated_database: None) -> Iterator[Session]:
    """Transactional session against a throwaway database, rolled back after
    each test.

    The session joins an outer transaction via SAVEPOINT, so code under test
    can call `commit()` for real — the webhook route does — and the outer
    rollback still leaves the database untouched between tests.
    """
    from app.db.session import engine

    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        autoflush=False,
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[object]:
    """TestClient wired to the per-test transactional session.

    Overriding `get_db` rather than pointing the app at a second connection
    matters: the test asserts on rows the request wrote, and two connections
    would not see each other's uncommitted work.
    """
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def snapshot_factory():
    """Build a CaseSnapshot with sensible defaults, overridable per test.

    Defaults to the boring case: SOFT_TECHNICAL, treatment arm, Rs 1,499,
    no attempts used, no prior contact, fixed `now`. Each test overrides only
    the field it is about, so the test reads as the rule it checks.
    """
    from datetime import UTC, datetime

    from app.core.holdout import Arm
    from app.core.taxonomy import FailureClass
    from app.policy.snapshot import CaseSnapshot

    def _build(**overrides) -> CaseSnapshot:
        defaults = dict(
            case_id="case_test",
            amount_paise=149_900,
            method="card",
            failure_class=FailureClass.SOFT_TECHNICAL,
            arm=Arm.TREATMENT,
            attempts_used=0,
            is_mandate=False,
            pre_debit_notice_sent_at=None,
            messages_sent=0,
            last_contact_at=None,
            discount_already_offered=False,
            now=datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        )
        defaults.update(overrides)
        return CaseSnapshot(**defaults)

    return _build


@pytest.fixture
def proposal_factory():
    """Build a valid Proposal with defaults; override per test."""
    from app.schemas.proposal import ActionKind, Proposal

    def _build(**overrides) -> Proposal:
        defaults = dict(
            action=ActionKind.SCHEDULE_RETRY,
            confidence=0.9,
            reasoning="Test proposal.",
        )
        defaults.update(overrides)
        return Proposal(**defaults)

    return _build
