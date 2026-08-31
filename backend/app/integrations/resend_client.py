"""Email delivery via Resend (100/day on the free tier).

That quota is the real constraint on batch size: a 100-case demo where every
case sends two messages will exhaust it. `settings.email_enabled = False`
turns sending into a logged no-op so the batch can be rehearsed without
burning quota — the audit trail still records the message as drafted and
approved, which is what the demo actually shows.
"""


def send_email(to: str, subject: str, body: str) -> str:
    """Send one message; returns the provider message id.

    When `settings.email_enabled` is False, logs and returns a synthetic id
    prefixed `dry-run:` so downstream code paths stay identical. Callers must
    not branch on dry-run themselves.
    """
    raise NotImplementedError("step-06: email delivery")
