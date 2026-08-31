"""The honest number.

Two counters sit side by side on the dashboard:

    gross        every rupee recovered on treated cases. What every vendor
                 in this market reports.
    incremental  (treated_rate - control_rate) * treated_volume * avg_amount.
                 What we actually caused. Nobody else publishes this.

Gross is always the larger and more flattering number. Showing both, with
incremental given equal weight, is the pitch.
"""

from typing import Any

from app.schemas.api import ArmMetrics, DashboardMetrics, FunnelCounts


def compute_funnel(session: Any) -> FunnelCounts:
    """failed -> eligible -> treated -> recovered.

    `eligible` excludes HARD_DECLINE: those are unrecoverable by design, and
    counting them in the denominator would understate performance as surely
    as omitting control cases would overstate it.
    """
    raise NotImplementedError("step-08: dashboard metrics")


def compute_arm_metrics(session: Any, arm: Any) -> ArmMetrics:
    """Cases, recoveries, amount and rate for one arm."""
    raise NotImplementedError("step-08: dashboard metrics")


def compute_incremental_paise(treatment: ArmMetrics, control: ArmMetrics) -> int:
    """Incremental recovery in paise.

        (treatment.recovery_rate - control.recovery_rate)
        * treatment.cases * avg_recovered_amount

    Can legitimately be negative or zero — if the agent underperforms doing
    nothing, that is a real finding and the dashboard shows it. Do not clamp
    to zero; a floor here would quietly reintroduce the dishonesty the
    holdout exists to prevent.

    With ~100 demo cases and a 20% holdout the control arm is ~20 cases, so
    this estimate is noisy. State that in the README rather than presenting
    it as precise — a judged demo that names its error bars beats one that
    hides them.
    """
    raise NotImplementedError("step-08: incremental recovery")


def compute_dashboard(session: Any) -> DashboardMetrics:
    """Assemble the full dashboard payload in one pass."""
    raise NotImplementedError("step-08: dashboard metrics")
