"""Razorpay webhook ingress — the entry point of the whole system.

    POST /api/webhooks/razorpay

Three things happen in strict order, and getting the order wrong breaks
either security or replayability:

  1. Verify `X-Razorpay-Signature` (HMAC-SHA256 over the RAW body). An
     unverified request is dropped with 400 and never opens a case.
  2. Store the raw payload, deduplicated by event id. Razorpay redelivers;
     a duplicate must be a no-op, not a second retry against a customer.
  3. Only then dispatch to the case manager.

Subscribed events: payment.failed, payment.captured, order.paid,
payment_link.paid.

Return 200 quickly. Razorpay retries on non-2xx, and a slow handler turns
one failure into a redelivery storm — do the minimum synchronously and let
the poller pick up the rest.
"""

import json
import logging
from hashlib import sha256
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import WebhookEvent
from app.db.session import get_db
from app.integrations.razorpay_client import verify_webhook_signature

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _event_id(request: Request, raw_body: bytes) -> str:
    """The idempotency key for one delivery.

    Razorpay stamps `X-Razorpay-Event-Id` and reuses it across redeliveries of
    the same event — that is the key. The digest fallback covers the seeder,
    which posts synthetic (correctly signed) webhooks without the header; it
    makes byte-identical bodies dedupe, which is the behaviour we want there.
    """
    header = request.headers.get("x-razorpay-event-id")
    if header:
        return header
    return f"sha256:{sha256(raw_body).hexdigest()}"


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Ingest one Razorpay event.

    Must read `await request.body()` for the raw bytes BEFORE any JSON
    parsing — the signature is computed over exactly what was sent, and a
    re-serialised dict will not match.
    """
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    if not verify_webhook_signature(raw_body, signature, settings.razorpay_webhook_secret):
        # Deliberately terse to the caller: a forged request learns nothing
        # about why it failed. The detail goes to our log, not the response.
        log.warning("rejected webhook with invalid signature (%d bytes)", len(raw_body))
        raise HTTPException(status_code=400, detail="invalid signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="malformed json") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    event_id = _event_id(request, raw_body)
    event_type = payload.get("event", "unknown")

    # ON CONFLICT DO NOTHING, not SELECT-then-INSERT. The read-then-write
    # version races against concurrent redelivery — which is precisely the
    # case dedupe exists to absorb — and would let two workers both open a
    # case for one failure.
    stmt = (
        pg_insert(WebhookEvent)
        .values(
            event_id=event_id,
            event_type=event_type,
            signature_valid=True,
            payload_json=payload,
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(WebhookEvent.id)
    )
    row_id = db.execute(stmt).scalar_one_or_none()
    db.commit()

    if row_id is None:
        # Already seen. 200, not 409: a non-2xx makes Razorpay redeliver
        # harder, and there is nothing here for it to fix.
        log.info("duplicate webhook %s (%s) ignored", event_id, event_type)
        return {"status": "duplicate", "event_id": event_id}

    # TODO(step-02): dispatch to services.case_manager — open or advance a
    # case, then stamp webhook_events.processed_at in the same transaction.
    # Until then every stored event stays unprocessed and replayable.

    return {"status": "accepted", "event_id": event_id, "event": event_type}
