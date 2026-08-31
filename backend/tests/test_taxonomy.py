"""Failure classification tests."""

import pytest

pytestmark = pytest.mark.skip(reason="step-02 not implemented")


def test_known_reasons_map_to_expected_class():
    """Table-driven over _REASON_MAP — one assertion per Razorpay code."""


def test_unknown_reason_falls_back_to_soft_technical():
    """Never to HARD_DECLINE.

    Misclassifying a recoverable failure as hard silently loses revenue and
    is invisible; the reverse costs one retry that the attempt budget
    already caps. The asymmetry is deliberate.
    """


def test_classification_is_pure():
    """No DB, no clock, no network — same payload, same class."""
