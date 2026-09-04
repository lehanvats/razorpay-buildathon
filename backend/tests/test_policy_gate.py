"""Policy gate tests — one per rule, plus interaction cases.

These run with no database and no network: the gate takes a CaseSnapshot and
a Proposal, both constructible by hand. That is the payoff of keeping the
gate pure, and it is why the compliance story is defensible — every rule in
the README table has a test naming it.
"""

from datetime import UTC, datetime, timedelta

from app.core.taxonomy import FailureClass
from app.policy.gate import gate
from app.policy.rules import MAX_CHARGE_ATTEMPTS, MAX_DISCOUNT_PERCENT, RuleId
from app.schemas.proposal import ActionKind, Decision

# --- One test per rule in the README table ---------------------------------


def test_hard_decline_blocks_retry(snapshot_factory, proposal_factory):
    """HARD_DECLINE + SCHEDULE_RETRY -> BLOCK, rule_id HARD_DECLINE_BLOCK.

    This is the demo case. The exact rule_id string appears on screen, so
    assert on it literally, not on the decision alone.
    """
    snapshot = snapshot_factory(failure_class=FailureClass.HARD_DECLINE)
    proposal = proposal_factory(action=ActionKind.SCHEDULE_RETRY)

    verdict = gate(snapshot, proposal)

    assert verdict.decision == Decision.BLOCK
    assert verdict.rule_id == "HARD_DECLINE_BLOCK"
    assert verdict.effective_action is None


def test_hard_decline_blocks_outreach_too(snapshot_factory, proposal_factory):
    """Not just charges — hard declines get no messages either."""
    snapshot = snapshot_factory(failure_class=FailureClass.HARD_DECLINE)
    proposal = proposal_factory(action=ActionKind.SEND_PAYMENT_LINK)

    verdict = gate(snapshot, proposal)

    assert verdict.decision == Decision.BLOCK
    assert verdict.rule_id == RuleId.HARD_DECLINE_BLOCK


def test_attempt_budget_allows_fourth_attempt_and_blocks_fifth(snapshot_factory, proposal_factory):
    """1 original + 3 retries. Boundary matters: attempts_used == 3 is still
    permitted, == 4 is not."""
    proposal = proposal_factory(action=ActionKind.SCHEDULE_RETRY)

    allowed = gate(snapshot_factory(attempts_used=3), proposal)
    assert allowed.decision == Decision.APPROVE
    assert allowed.rule_id == "PASS"

    blocked = gate(snapshot_factory(attempts_used=MAX_CHARGE_ATTEMPTS), proposal)
    assert blocked.decision == Decision.BLOCK
    assert blocked.rule_id == RuleId.ATTEMPT_BUDGET_EXHAUSTED


def test_payment_link_does_not_consume_attempt_budget(snapshot_factory, proposal_factory):
    """A customer-authenticated link is not an auto-debit, so it is available
    even once the NPCI retry budget is spent."""
    snapshot = snapshot_factory(attempts_used=MAX_CHARGE_ATTEMPTS)
    proposal = proposal_factory(action=ActionKind.SEND_PAYMENT_LINK)

    verdict = gate(snapshot, proposal)

    assert verdict.decision == Decision.APPROVE
    assert verdict.rule_id == "PASS"


def test_mandate_retry_requires_pre_debit_notice(snapshot_factory, proposal_factory):
    """No notice sent -> REWRITE to send notice first, debit at notice + 24h."""
    snapshot = snapshot_factory(is_mandate=True, pre_debit_notice_sent_at=None)
    proposal = proposal_factory(action=ActionKind.SCHEDULE_RETRY)

    verdict = gate(snapshot, proposal)

    assert verdict.decision == Decision.REWRITE
    assert verdict.rule_id == RuleId.PRE_DEBIT_NOTICE_REQUIRED
    assert verdict.effective_timing == snapshot.now + timedelta(hours=24)


def test_mandate_retry_allowed_after_notice_matures(snapshot_factory, proposal_factory):
    """Notice sent 25h ago -> APPROVE. Sent 23h ago -> still deferred."""
    now = snapshot_factory().now
    proposal = proposal_factory(action=ActionKind.SCHEDULE_RETRY)

    matured = snapshot_factory(is_mandate=True, pre_debit_notice_sent_at=now - timedelta(hours=25))
    matured_verdict = gate(matured, proposal)
    assert matured_verdict.decision == Decision.APPROVE

    fresh = snapshot_factory(is_mandate=True, pre_debit_notice_sent_at=now - timedelta(hours=23))
    fresh_verdict = gate(fresh, proposal)
    assert fresh_verdict.decision == Decision.REWRITE
    assert fresh_verdict.rule_id == RuleId.PRE_DEBIT_NOTICE_REQUIRED


def test_afa_threshold_rewrites_retry_to_payment_link(snapshot_factory, proposal_factory):
    """Above Rs 15,000 (1_500_000 paise) no auto-charge is permitted.

    Test the boundary in paise, and confirm exactly at the threshold is
    permitted while one paise above is not.
    """
    proposal = proposal_factory(action=ActionKind.SCHEDULE_RETRY)

    at_threshold = gate(snapshot_factory(amount_paise=1_500_000), proposal)
    assert at_threshold.decision == Decision.APPROVE
    assert at_threshold.effective_action == ActionKind.SCHEDULE_RETRY

    above_threshold = gate(snapshot_factory(amount_paise=1_500_001), proposal)
    assert above_threshold.decision == Decision.REWRITE
    assert above_threshold.rule_id == RuleId.AFA_THRESHOLD_EXCEEDED
    assert above_threshold.effective_action == ActionKind.SEND_PAYMENT_LINK


def test_salary_window_moves_soft_funds_retry(snapshot_factory, proposal_factory):
    """SOFT_FUNDS timing lands in the 1st-5th, or now + 72h if that is
    nearer. A case failing on the 6th must not wait 26 days."""
    now = datetime(2026, 9, 6, 10, 0, tzinfo=UTC)  # the 6th of the month
    snapshot = snapshot_factory(failure_class=FailureClass.SOFT_FUNDS, now=now)
    proposal = proposal_factory(action=ActionKind.SCHEDULE_RETRY)

    verdict = gate(snapshot, proposal)

    assert verdict.decision == Decision.REWRITE
    assert verdict.rule_id == RuleId.SALARY_WINDOW_RESCHEDULE
    assert verdict.effective_timing == now + timedelta(hours=72)
    assert verdict.effective_timing < now + timedelta(days=26)


def test_salary_window_does_not_undercut_a_pending_mandate_notice(
    snapshot_factory, proposal_factory
):
    """Regression: a mandate case that is ALSO SOFT_FUNDS used to have its
    debit time overwritten by salary_window, which recomputed purely from
    `snapshot.now` and ignored the notice + 24h floor pre_debit_notice had
    already set two rules earlier in the chain — a real RBI-compliance
    violation (corrections.md #10), not just a scheduling quirk.

    `now` is deliberately chosen so its own day already falls inside
    SALARY_WINDOW_DAYS: that makes salary_window's own (buggy) answer
    `now` itself — the earliest possible wrong answer, and strictly before
    the notice can have matured. The gate must still land on the notice's
    floor, not `now`.
    """
    now = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)  # the 3rd — already in 1-5
    snapshot = snapshot_factory(
        failure_class=FailureClass.SOFT_FUNDS,
        is_mandate=True,
        pre_debit_notice_sent_at=None,
        now=now,
    )
    proposal = proposal_factory(action=ActionKind.SCHEDULE_RETRY)

    verdict = gate(snapshot, proposal)

    assert verdict.decision == Decision.REWRITE
    assert verdict.rule_id == RuleId.PRE_DEBIT_NOTICE_REQUIRED
    assert verdict.effective_timing == now + timedelta(hours=24)


def test_contact_cooldown_blocks_rapid_second_message(snapshot_factory, proposal_factory):
    """< 24h since last contact -> blocked; 4th message -> blocked."""
    proposal = proposal_factory(action=ActionKind.SEND_PAYMENT_LINK)
    now = snapshot_factory().now

    rapid = snapshot_factory(last_contact_at=now - timedelta(hours=1))
    rapid_verdict = gate(rapid, proposal)
    assert rapid_verdict.decision == Decision.BLOCK
    assert rapid_verdict.rule_id == RuleId.CONTACT_COOLDOWN

    fourth = snapshot_factory(messages_sent=3)
    fourth_verdict = gate(fourth, proposal)
    assert fourth_verdict.decision == Decision.BLOCK
    assert fourth_verdict.rule_id == RuleId.CONTACT_COOLDOWN


def test_discount_is_clamped_not_blocked(snapshot_factory, proposal_factory):
    """A 30% proposal becomes a 10% REWRITE; a second discount on the same
    case is BLOCKED."""
    over_proposal = proposal_factory(action=ActionKind.OFFER_DISCOUNT, discount_percent=30)
    clamp_verdict = gate(snapshot_factory(), over_proposal)
    assert clamp_verdict.decision == Decision.REWRITE
    assert clamp_verdict.rule_id == RuleId.DISCOUNT_BOUND
    assert clamp_verdict.effective_discount_percent == MAX_DISCOUNT_PERCENT

    repeat_proposal = proposal_factory(action=ActionKind.OFFER_DISCOUNT, discount_percent=10)
    block_verdict = gate(snapshot_factory(discount_already_offered=True), repeat_proposal)
    assert block_verdict.decision == Decision.BLOCK
    assert block_verdict.rule_id == RuleId.DISCOUNT_BOUND


def test_low_confidence_escalates(snapshot_factory, proposal_factory):
    """confidence < 0.6 -> ESCALATE, and the agent goes silent afterwards."""
    proposal = proposal_factory(confidence=0.5)

    verdict = gate(snapshot_factory(), proposal)

    assert verdict.decision == Decision.ESCALATE
    assert verdict.rule_id == RuleId.LOW_CONFIDENCE_ESCALATE
    assert verdict.effective_action is None


# --- Interaction and invariant tests ---------------------------------------


def test_blocking_rules_run_before_rewriting_rules(snapshot_factory, proposal_factory):
    """A hard-decline case must never be rewritten into a payment link.

    Pins RULE_CHAIN ordering — reordering it is a policy change and should
    break a test, not slip through.
    """
    snapshot = snapshot_factory(failure_class=FailureClass.HARD_DECLINE, amount_paise=2_000_000)
    proposal = proposal_factory(action=ActionKind.SCHEDULE_RETRY)

    verdict = gate(snapshot, proposal)

    assert verdict.decision == Decision.BLOCK
    assert verdict.effective_action is None


def test_gate_is_pure(snapshot_factory, proposal_factory):
    """Same snapshot + proposal -> identical verdict, repeatedly.

    Also guards against a rule reaching for the wall clock instead of
    snapshot.now.
    """
    snapshot = snapshot_factory(failure_class=FailureClass.SOFT_FUNDS, is_mandate=True)
    proposal = proposal_factory(action=ActionKind.SCHEDULE_RETRY)

    first = gate(snapshot, proposal)
    second = gate(snapshot, proposal)

    assert first == second


def test_gate_never_raises_on_wellformed_proposal(snapshot_factory, proposal_factory):
    """Every valid ActionKind against every FailureClass returns a Verdict.
    An unrepresentable combination escalates rather than 500-ing a webhook."""
    for failure_class in FailureClass:
        for action in ActionKind:
            snapshot = snapshot_factory(failure_class=failure_class)
            kwargs = {"action": action}
            if action == ActionKind.OFFER_DISCOUNT:
                kwargs["discount_percent"] = 5
            proposal = proposal_factory(**kwargs)

            verdict = gate(snapshot, proposal)

            assert verdict is not None
            assert verdict.rule_id


def test_every_verdict_names_a_rule_id(snapshot_factory, proposal_factory):
    """Including approvals ('PASS' if untouched) — every action in the audit
    trail must name its authority."""
    verdict = gate(snapshot_factory(), proposal_factory())

    assert verdict.decision == Decision.APPROVE
    assert verdict.rule_id == "PASS"
