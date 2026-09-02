"""services/metrics.py — the honest number.

Builds Case/Outcome/Action rows directly rather than going through
handle_payment_failed: these tests are about the aggregation queries, not
the ingestion pipeline (already covered by test_case_manager.py).
"""

from datetime import UTC, datetime

import pytest

from app.core.holdout import Arm
from app.core.taxonomy import FailureClass
from app.db.models import Action, Case, Outcome
from app.schemas.api import ArmMetrics
from app.services.metrics import (
    compute_arm_metrics,
    compute_dashboard,
    compute_funnel,
    compute_incremental_paise,
)

_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def _case(db_session, id: str, *, arm: str, failure_class: str, status: str = "open") -> Case:
    case = Case(
        id=id,
        razorpay_order_id=f"order_{id}",
        razorpay_payment_id=f"pay_{id}",
        amount_paise=100_000,
        currency="INR",
        method="card",
        is_mandate=False,
        failure_class=failure_class,
        arm=arm,
        status=status,
        attempts_used=1,
        messages_sent=0,
        discount_offered=False,
    )
    db_session.add(case)
    db_session.flush()
    return case


def _outcome(db_session, case: Case, *, amount_paise: int) -> None:
    db_session.add(
        Outcome(
            case_id=case.id,
            recovered_amount_paise=amount_paise,
            recovered_at=_NOW,
            via="retry",
            arm_at_recovery=case.arm,
        )
    )
    db_session.flush()


def test_compute_funnel_excludes_hard_decline_from_eligible(db_session):
    _case(db_session, "c1", arm="treatment", failure_class="SOFT_FUNDS")
    _case(db_session, "c2", arm="treatment", failure_class="HARD_DECLINE")
    _case(db_session, "c3", arm="control", failure_class="DROPOFF")

    funnel = compute_funnel(db_session)
    assert funnel.failed == 3
    assert funnel.eligible == 2  # HARD_DECLINE excluded


def test_compute_funnel_treated_counts_cases_with_an_action_not_just_arm(db_session):
    treated = _case(db_session, "c1", arm="treatment", failure_class="SOFT_FUNDS")
    _case(db_session, "c2", arm="treatment", failure_class="SOFT_FUNDS")  # never actioned

    db_session.add(
        Action(
            id="action_1",
            case_id=treated.id,
            kind="SCHEDULE_RETRY",
            verdict_rule_id="PASS",
            scheduled_for=_NOW,
        )
    )
    db_session.flush()

    funnel = compute_funnel(db_session)
    assert funnel.treated == 1


def test_compute_funnel_recovered_counts_both_arms(db_session):
    t = _case(db_session, "c1", arm="treatment", failure_class="SOFT_FUNDS")
    c = _case(db_session, "c2", arm="control", failure_class="SOFT_FUNDS")
    _outcome(db_session, t, amount_paise=100_000)
    _outcome(db_session, c, amount_paise=100_000)

    assert compute_funnel(db_session).recovered == 2


def test_compute_arm_metrics_rate_and_amount(db_session):
    a = _case(db_session, "c1", arm="treatment", failure_class="SOFT_FUNDS")
    _case(db_session, "c2", arm="treatment", failure_class="SOFT_FUNDS")  # not recovered
    _outcome(db_session, a, amount_paise=50_000)

    metrics = compute_arm_metrics(db_session, Arm.TREATMENT)
    assert metrics.cases == 2
    assert metrics.recovered_cases == 1
    assert metrics.recovered_amount_paise == 50_000
    assert metrics.recovery_rate == pytest.approx(0.5)


def test_compute_arm_metrics_zero_cases_is_zero_rate_not_a_crash(db_session):
    metrics = compute_arm_metrics(db_session, Arm.CONTROL)
    assert metrics.cases == 0
    assert metrics.recovered_cases == 0
    assert metrics.recovered_amount_paise == 0
    assert metrics.recovery_rate == 0.0


def test_compute_incremental_paise_can_be_negative():
    treatment = ArmMetrics(
        arm=Arm.TREATMENT,
        cases=100,
        recovered_cases=20,
        recovered_amount_paise=2_000_000,
        recovery_rate=0.20,
    )
    control = ArmMetrics(
        arm=Arm.CONTROL,
        cases=25,
        recovered_cases=8,
        recovered_amount_paise=800_000,
        recovery_rate=0.32,
    )
    incremental = compute_incremental_paise(treatment, control)
    # (0.20 - 0.32) * 100 cases * avg 100,000p = -1,200,000p. A worse-than-
    # control treatment arm must show as a real negative, never clamped.
    assert incremental == -1_200_000


def test_compute_incremental_paise_is_zero_with_no_treatment_recoveries():
    treatment = ArmMetrics(
        arm=Arm.TREATMENT,
        cases=10,
        recovered_cases=0,
        recovered_amount_paise=0,
        recovery_rate=0.0,
    )
    control = ArmMetrics(
        arm=Arm.CONTROL,
        cases=3,
        recovered_cases=1,
        recovered_amount_paise=100_000,
        recovery_rate=0.33,
    )
    assert compute_incremental_paise(treatment, control) == 0


def test_compute_dashboard_gross_is_treatment_only(db_session):
    t = _case(db_session, "c1", arm="treatment", failure_class="SOFT_FUNDS")
    c = _case(db_session, "c2", arm="control", failure_class="SOFT_FUNDS")
    _outcome(db_session, t, amount_paise=70_000)
    _outcome(db_session, c, amount_paise=999_000)  # must NOT leak into gross

    dashboard = compute_dashboard(db_session)
    assert dashboard.gross_recovered_paise == 70_000


def test_compute_dashboard_by_failure_class_is_treatment_arm_only(db_session):
    t_funds = _case(db_session, "c1", arm="treatment", failure_class="SOFT_FUNDS")
    _case(db_session, "c2", arm="control", failure_class="SOFT_FUNDS")
    _outcome(db_session, t_funds, amount_paise=40_000)

    dashboard = compute_dashboard(db_session)
    by_class = dashboard.by_failure_class[FailureClass.SOFT_FUNDS]
    assert by_class.arm == Arm.TREATMENT
    assert by_class.cases == 1
    assert by_class.recovered_amount_paise == 40_000


def test_compute_dashboard_escalations_open_counts_escalated_and_stuck_hard_decline(db_session):
    _case(db_session, "c1", arm="treatment", failure_class="SOFT_FUNDS", status="escalated")
    _case(db_session, "c2", arm="treatment", failure_class="HARD_DECLINE", status="open")
    _case(db_session, "c3", arm="treatment", failure_class="HARD_DECLINE", status="exhausted")
    _case(db_session, "c4", arm="treatment", failure_class="SOFT_FUNDS", status="open")

    assert compute_dashboard(db_session).escalations_open == 2
