"""Policy gate tests — one per rule, plus interaction cases.

These run with no database and no network: the gate takes a CaseSnapshot and
a Proposal, both constructible by hand. That is the payoff of keeping the
gate pure, and it is why the compliance story is defensible — every rule in
the README table has a test naming it.
"""

import pytest

pytestmark = pytest.mark.skip(reason="step-05 not implemented")


# --- One test per rule in the README table ---------------------------------


def test_hard_decline_blocks_retry():
    """HARD_DECLINE + SCHEDULE_RETRY -> BLOCK, rule_id HARD_DECLINE_BLOCK.

    This is the demo case. The exact rule_id string appears on screen, so
    assert on it literally, not on the decision alone.
    """


def test_hard_decline_blocks_outreach_too():
    """Not just charges — hard declines get no messages either."""


def test_attempt_budget_allows_fourth_attempt_and_blocks_fifth():
    """1 original + 3 retries. Boundary matters: attempts_used == 3 is still
    permitted, == 4 is not."""


def test_payment_link_does_not_consume_attempt_budget():
    """A customer-authenticated link is not an auto-debit, so it is available
    even once the NPCI retry budget is spent."""


def test_mandate_retry_requires_pre_debit_notice():
    """No notice sent -> REWRITE to send notice first, debit at notice + 24h."""


def test_mandate_retry_allowed_after_notice_matures():
    """Notice sent 25h ago -> APPROVE. Sent 23h ago -> still deferred."""


def test_afa_threshold_rewrites_retry_to_payment_link():
    """Above Rs 15,000 (1_500_000 paise) no auto-charge is permitted.

    Test the boundary in paise, and confirm exactly at the threshold is
    permitted while one paise above is not.
    """


def test_salary_window_moves_soft_funds_retry():
    """SOFT_FUNDS timing lands in the 1st-5th, or now + 72h if that is
    nearer. A case failing on the 6th must not wait 26 days."""


def test_contact_cooldown_blocks_rapid_second_message():
    """< 24h since last contact -> blocked; 4th message -> blocked."""


def test_discount_is_clamped_not_blocked():
    """A 30% proposal becomes a 10% REWRITE; a second discount on the same
    case is BLOCKED."""


def test_low_confidence_escalates():
    """confidence < 0.6 -> ESCALATE, and the agent goes silent afterwards."""


# --- Interaction and invariant tests ---------------------------------------


def test_blocking_rules_run_before_rewriting_rules():
    """A hard-decline case must never be rewritten into a payment link.

    Pins RULE_CHAIN ordering — reordering it is a policy change and should
    break a test, not slip through.
    """


def test_gate_is_pure():
    """Same snapshot + proposal -> identical verdict, repeatedly.

    Also guards against a rule reaching for the wall clock instead of
    snapshot.now.
    """


def test_gate_never_raises_on_wellformed_proposal():
    """Every valid ActionKind against every FailureClass returns a Verdict.
    An unrepresentable combination escalates rather than 500-ing a webhook."""


def test_every_verdict_names_a_rule_id():
    """Including approvals ('PASS' if untouched) — every action in the audit
    trail must name its authority."""
