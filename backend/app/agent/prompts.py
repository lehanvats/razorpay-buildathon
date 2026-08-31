"""Prompt construction for the diagnosis step.

The prompt does three things and no more: describe the case, present the
fixed action menu, and demand structured JSON. It does NOT describe the
compliance rules as instructions to obey — that would be asking the model to
self-police, and the whole architecture exists because that is not
trustworthy. The gate enforces; the model suggests.

One deliberate exception, used by the demo: DEMO_LOOSE_SYSTEM_PROMPT omits
the hard-decline hint so the model proposes a retry on an unrecoverable case
and the gate is seen blocking it on screen with its rule_id. That is the
"graceful failure" beat judges asked for.
"""

SYSTEM_PROMPT = """\
TODO(step-04): system prompt.

Establish:
  - Role: payment recovery analyst for Indian payment rails.
  - The four failure classes and what each implies about timing.
  - The fixed action menu (SCHEDULE_RETRY, SEND_PAYMENT_LINK,
    OFFER_DISCOUNT, ESCALATE) and that nothing outside it is valid.
  - Output is JSON matching the Proposal schema. No prose outside the JSON.
  - Timing must be IST-aware ISO 8601.
  - Where the model adds value: choosing timing, channel and tone per case,
    and drafting the customer message. Not deciding what is permitted.
  - Confidence must be honest: low confidence escalates, which is a correct
    and desirable outcome, not a failure.
"""

DEMO_LOOSE_SYSTEM_PROMPT = """\
TODO(step-07): the deliberately under-constrained variant used for the
seeded HARD_DECLINE demo case, so the gate is observed doing its job.
Identical to SYSTEM_PROMPT minus any hint that hard declines are
unrecoverable.
"""


def build_case_prompt(case_context: dict) -> str:
    """Render one case into the user turn.

    Includes: failure class, amount in rupees, method, attempt history with
    timestamps, prior contact history, and how many attempts remain under the
    budget. Excludes: customer PII beyond what is needed, raw card data
    (never available to us anyway), and any internal rule text.

    Args:
        case_context: flat dict assembled by agent/diagnose.py.

    Returns:
        The user-turn string.
    """
    raise NotImplementedError("step-04: diagnosis prompt")
