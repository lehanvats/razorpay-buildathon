"""Failure classification tests."""

import pytest

from app.core.taxonomy import _REASON_MAP, FailureClass, classify


@pytest.mark.parametrize(("error_reason", "expected"), sorted(_REASON_MAP.items()))
def test_known_reasons_map_to_expected_class(error_reason, expected):
    """Table-driven over _REASON_MAP — one assertion per Razorpay code."""
    assert classify({"error_reason": error_reason}) is expected


@pytest.mark.parametrize("entity", [{"error_reason": "some_new_reason_code"}, {}])
def test_unknown_reason_falls_back_to_soft_technical(entity):
    """Never to HARD_DECLINE.

    Misclassifying a recoverable failure as hard silently loses revenue and
    is invisible; the reverse costs one retry that the attempt budget
    already caps. The asymmetry is deliberate.
    """
    assert classify(entity) is FailureClass.SOFT_TECHNICAL


def test_classification_is_pure():
    """No DB, no clock, no network — same payload, same class."""
    entity = {"error_reason": "insufficient_funds"}
    assert classify(entity) is classify(dict(entity)) is FailureClass.SOFT_FUNDS
