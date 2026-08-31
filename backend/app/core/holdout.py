"""Holdout assignment — the honest-attribution differentiator.

Exists *before* any action code by design (blueprint step 03, not step 08):
no action is ever taken outside the experiment, so the incremental number is
trustworthy from the first case rather than retrofitted.

Roughly 21% of failed payments recover on their own with no outreach at all.
Every vendor in this market books those as wins. Recoup holds out 20% of
cases, takes no action on them ever, and reports the difference:

    incremental = (treated_recovery_rate - control_recovery_rate)
                  * treated_volume * avg_amount

IMPORTANT — do not use Python's builtin `hash()` here. For str inputs it is
salted per process (PYTHONHASHSEED), so the same case_id would land in
different arms across restarts and silently corrupt the control group. Use a
stable cryptographic digest. There is a regression test pinning this.
"""

import hashlib
from enum import Enum

#: 1 in N cases is held back untouched. 5 == 20% control.
CONTROL_BUCKET_MODULUS = 5


class Arm(str, Enum):
    """Experiment arm. Stored on `cases.arm`, written once at creation."""

    TREATMENT = "treatment"
    CONTROL = "control"


def assign_arm(case_id: str) -> Arm:
    """Deterministically assign a case to control or treatment.

    Deterministic on purpose: re-running assignment for the same case_id must
    always yield the same arm — across processes, restarts and deploys — so
    the arm can be recomputed for audit without trusting the stored row.

        digest = sha256(case_id.encode())
        bucket = int.from_bytes(digest[:8], "big") % CONTROL_BUCKET_MODULUS
        CONTROL if bucket == 0 else TREATMENT

    Args:
        case_id: the case's stable identifier (uuid string).

    Returns:
        Arm.CONTROL for ~20% of ids, Arm.TREATMENT otherwise.
    """
    raise NotImplementedError("step-03: holdout assignment")


def is_actionable(arm: Arm) -> bool:
    """Whether the agent may take *any* action on this case.

    Control cases get no diagnosis, no retry, no message — ever.

    Careful: this gates *actions only*. Control-case outcomes still arrive
    through the same webhooks and must still be written to `outcomes`,
    otherwise the control recovery rate reads as zero and the incremental
    number becomes a lie in our own favour. See services/case_manager.py for
    the branch point.
    """
    raise NotImplementedError("step-03: holdout assignment")
