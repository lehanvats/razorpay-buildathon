"""Holdout assignment tests.

The incremental-recovery number is the pitch, and it rests entirely on the
control group being a genuine random-but-stable 20% sample. These tests are
not optional polish.
"""

import pytest

pytestmark = pytest.mark.skip(reason="step-03 not implemented")


def test_assignment_is_stable_across_processes():
    """THE regression test.

    Python's builtin hash() is salted per process for str inputs, so
    `hash(case_id) % 5` returns different answers after a restart — the same
    case would silently switch arms and corrupt the control group.

    Run assignment in a subprocess with a different PYTHONHASHSEED and assert
    the arm matches this process's answer for the same ids.
    """


def test_distribution_is_approximately_twenty_percent():
    """Over ~10k synthetic ids, control should land near 20%.

    Allow a tolerance band; assert it is neither ~0% (assignment broken) nor
    ~50% (wrong modulus).
    """


def test_same_id_always_same_arm():
    """Idempotence: repeated calls agree."""


def test_control_cases_are_never_actionable():
    """is_actionable(CONTROL) is False, unconditionally."""


def test_control_outcomes_are_still_measured():
    """The holdout gates actions, not measurement.

    A control case that self-recovers must still produce an outcome row.
    If this fails, the control recovery rate reads as zero and the
    incremental number becomes a lie in our own favour.
    """
