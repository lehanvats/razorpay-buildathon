"""Webhook ingress tests — signature verification and idempotency."""

import pytest

pytestmark = pytest.mark.skip(reason="step-01 not implemented")


def test_valid_signature_accepted():
    """HMAC-SHA256 over the raw body with the webhook secret."""


def test_invalid_signature_rejected_with_400():
    """And no case is opened."""


def test_signature_computed_over_raw_bytes_not_reserialised_json():
    """Send a body with unusual key order / whitespace and confirm it still
    verifies. Re-serialising a parsed dict changes the digest — this is the
    classic way webhook auth breaks in production.
    """


def test_duplicate_event_id_is_a_noop():
    """Razorpay redelivers. A duplicate must not open a second case or fire
    a second retry at a customer."""


def test_raw_payload_stored_before_processing():
    """A crash mid-processing must leave a replayable record."""
