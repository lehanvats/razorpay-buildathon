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

from fastapi import APIRouter

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# @router.post("/razorpay")
# async def razorpay_webhook(request: Request, db = Depends(get_db)):
#     """Ingest one Razorpay event.
#
#     Must read `await request.body()` for the raw bytes BEFORE any JSON
#     parsing — the signature is computed over exactly what was sent, and a
#     re-serialised dict will not match.
#     """
#     raise NotImplementedError("step-01: webhook ingress")
