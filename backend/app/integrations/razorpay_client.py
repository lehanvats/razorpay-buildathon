"""Razorpay API wrapper — test mode throughout.

Covers exactly what the recovery loop needs: create orders, create payment
links, and verify inbound webhook signatures. Everything else the SDK offers
is out of scope.
"""

import hmac
from hashlib import sha256
from typing import Any

import razorpay

from app.config import settings


def verify_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Verify the `X-Razorpay-Signature` header.

    HMAC-SHA256 over the **raw request body** with the webhook secret. Two
    things that are easy to get wrong and both silently break security:

      * Compute over raw bytes, not a re-serialised parsed dict — key order
        and whitespace change the digest.
      * Compare with `hmac.compare_digest`, never `==`, to avoid leaking the
        signature through timing.

    An unverified webhook is dropped and logged; it never opens a case.
    """
    if not signature or not secret:
        # No secret configured is a misconfiguration, not a pass. Fail closed:
        # an open door here means anyone can open cases and trigger retries.
        return False

    expected = hmac.new(secret.encode("utf-8"), raw_body, sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def sign_payload(raw_body: bytes, secret: str) -> str:
    """Produce a signature the way Razorpay would.

    Used by the tests and by scripts/seed_failures.py, which posts
    synthetic-but-correctly-signed webhooks so the demo can choose failure
    reasons that test mode will not produce on demand. Kept beside the
    verifier so the two can never drift apart.
    """
    return hmac.new(secret.encode("utf-8"), raw_body, sha256).hexdigest()


def _client() -> razorpay.Client:
    """Authenticated SDK client, built per call.

    Raises rather than returning a half-configured client — a silent no-op
    against the payments API is worse than a loud failure.
    """
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RuntimeError(
            "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set; "
            "cannot call the Razorpay API"
        )
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def create_order(amount_paise: int, currency: str = "INR", **notes: Any) -> dict:
    """Create an Order — used for the storefront checkout and for retries.

    Pass the case id in `notes` so the resulting payment webhook can be
    matched back to its case without a lookup table.
    """
    if amount_paise <= 0:
        raise ValueError("amount_paise must be a positive integer number of paise")

    return _client().order.create(
        {
            "amount": amount_paise,
            "currency": currency,
            # Razorpay's notes values must be strings.
            "notes": {k: str(v) for k, v in notes.items()},
        }
    )


def create_payment_link(
    amount_paise: int,
    customer_email: str,
    *,
    expires_in_hours: int = 48,
    **notes: Any,
) -> dict:
    """Create a customer-authenticated Payment Link.

    The compliant path above the AFA threshold. Expiry defaults to match the
    discount window so a stale link cannot be paid at a withdrawn price.
    """
    raise NotImplementedError("step-06: payment link creation")
