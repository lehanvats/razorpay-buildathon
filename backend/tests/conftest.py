"""Shared pytest fixtures.

Note the split: policy and taxonomy tests need no fixtures at all — they are
pure functions over plain data. Only the webhook and metrics tests touch a
database. Keep it that way; the moment the gate needs a fixture, it has
stopped being pure.
"""

import pytest


@pytest.fixture
def db_session():
    """Transactional session against a throwaway database, rolled back after
    each test."""
    raise NotImplementedError("step-01: test database fixture")


@pytest.fixture
def snapshot_factory():
    """Build a CaseSnapshot with sensible defaults, overridable per test.

    Defaults to the boring case: SOFT_TECHNICAL, treatment arm, Rs 1,499,
    no attempts used, no prior contact, fixed `now`. Each test overrides only
    the field it is about, so the test reads as the rule it checks.
    """
    raise NotImplementedError("step-05: snapshot factory")


@pytest.fixture
def proposal_factory():
    """Build a valid Proposal with defaults; override per test."""
    raise NotImplementedError("step-05: proposal factory")
