"""Email delivery via Resend (100/day on the free tier).

That quota is the real constraint on batch size: a 100-case demo where every
case sends two messages will exhaust it. `settings.email_enabled = False`
turns sending into a logged no-op so the batch can be rehearsed without
burning quota — the audit trail still records the message as drafted and
approved, which is what the demo actually shows.
"""

import logging
from uuid import uuid4

from app.config import settings

log = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> str:
    """Send one message; returns the provider message id.

    When `settings.email_enabled` is False, logs and returns a synthetic id
    prefixed `dry-run:` so downstream code paths stay identical. Callers must
    not branch on dry-run themselves.

    The dry-run check happens *before* importing `resend` — the package is
    in requirements.txt but not every dev environment has it installed
    (mirrors the lazy-import pattern in `agent/providers.py`), and rehearsing
    a batch must work on a machine that has never `pip install`-ed it.
    """
    if not settings.email_enabled:
        log.info("dry-run email to=%s subject=%r", to, subject)
        return f"dry-run:{uuid4()}"

    import resend

    resend.api_key = settings.resend_api_key
    result = resend.Emails.send(
        {
            "from": settings.email_from,
            "to": [to],
            "subject": subject,
            "html": body,
        }
    )
    return result["id"]
