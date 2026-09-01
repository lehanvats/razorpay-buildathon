"""Holdout assignment tests.

The incremental-recovery number is the pitch, and it rests entirely on the
control group being a genuine random-but-stable 20% sample. These tests are
not optional polish.
"""

import os
import subprocess
import sys

from app.core.holdout import CONTROL_BUCKET_MODULUS, Arm, assign_arm, is_actionable


def test_assignment_is_stable_across_processes():
    """THE regression test.

    Python's builtin hash() is salted per process for str inputs, so
    `hash(case_id) % 5` returns different answers after a restart — the same
    case would silently switch arms and corrupt the control group.

    Run assignment in a subprocess with a different PYTHONHASHSEED and assert
    the arm matches this process's answer for the same ids.
    """
    case_ids = ["case_a", "case_b", "case_c", "case_stability_check"]
    expected = [assign_arm(cid).value for cid in case_ids]

    script = (
        "from app.core.holdout import assign_arm; "
        "print(','.join(assign_arm(c).value for c in "
        f"{case_ids!r}))"
    )
    env = {**os.environ, "PYTHONHASHSEED": "999"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert result.stdout.strip().split(",") == expected


def test_distribution_is_approximately_twenty_percent():
    """Over ~10k synthetic ids, control should land near 20%.

    Allow a tolerance band; assert it is neither ~0% (assignment broken) nor
    ~50% (wrong modulus).
    """
    n = 10_000
    control_count = sum(1 for i in range(n) if assign_arm(f"case_{i}") is Arm.CONTROL)
    fraction = control_count / n
    expected = 1 / CONTROL_BUCKET_MODULUS
    assert expected - 0.03 < fraction < expected + 0.03


def test_same_id_always_same_arm():
    """Idempotence: repeated calls agree."""
    for case_id in ("case_x", "case_y", "case_z"):
        first = assign_arm(case_id)
        assert all(assign_arm(case_id) == first for _ in range(50))


def test_control_cases_are_never_actionable():
    """is_actionable(CONTROL) is False, unconditionally."""
    assert is_actionable(Arm.CONTROL) is False
    assert is_actionable(Arm.TREATMENT) is True


def test_control_outcomes_are_still_measured(db_session, monkeypatch):
    """The holdout gates actions, not measurement.

    A control case that self-recovers must still produce an outcome row.
    If this fails, the control recovery rate reads as zero and the
    incremental number becomes a lie in our own favour.
    """
    from app.db.models import Outcome
    from app.services.case_manager import handle_payment_failed, handle_payment_succeeded

    monkeypatch.setattr("app.services.case_manager.assign_arm", lambda _case_id: Arm.CONTROL)

    def _event(**overrides):
        entity = {
            "id": "pay_ABC",
            "order_id": "order_ABC",
            "amount": 149900,
            "currency": "INR",
            "method": "upi",
            "error_reason": "insufficient_funds",
            **overrides,
        }
        return {"payload": {"payment": {"entity": entity}}}

    case_id = handle_payment_failed(db_session, _event())
    handle_payment_succeeded(db_session, _event())

    outcome = db_session.get(Outcome, case_id)
    assert outcome is not None
    assert outcome.arm_at_recovery == Arm.CONTROL.value
    assert outcome.recovered_amount_paise == 149900
