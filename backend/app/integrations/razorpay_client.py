"""Razorpay API wrapper — test mode throughout.

Covers exactly what the recovery loop needs: create orders, create payment
links, and verify inbound webhook signatures. Everything else the SDK offers
is out of scope.
"""

from typing import Any


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
    raise NotImplementedError("step-01: webhook signature verification")


def create_order(amount_paise: int, currency: str = "INR", **notes: Any) -> dict:
    """Create an Order — used for the storefront checkout and for retries.

    Pass the case id in `notes` so the resulting payment webhook can be
    matched back to its case without a lookup table.
    """
    raise NotImplementedError("step-01: order creation")


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
