"""Metrics tests — gross vs incremental."""

import pytest

pytestmark = pytest.mark.skip(reason="step-08 not implemented")


def test_incremental_is_zero_when_arms_perform_identically():
    """If treatment matches control, we caused nothing. Say so."""


def test_incremental_can_be_negative():
    """If the agent underperforms doing nothing, the dashboard shows a
    negative number. Do not clamp to zero — a floor would quietly
    reintroduce exactly the dishonesty the holdout exists to prevent.
    """


def test_gross_exceeds_incremental_when_control_self_recovers():
    """The headline asymmetry: ~21% of failures recover unaided, so gross
    always flatters. Both numbers must be shown."""


def test_funnel_excludes_hard_declines_from_eligible():
    """Unrecoverable by design — counting them in the denominator understates
    performance as surely as dropping control cases would overstate it."""


def test_money_is_integer_paise_throughout():
    """No float arithmetic anywhere in the money path."""
