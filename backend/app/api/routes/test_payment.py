"""Test payment — a real Razorpay Payment Link against a simulated failure.

    POST /api/test-payment             open a case, mint the link, return its URL
    POST /api/test-payment/reconcile   confirm payment from the callback redirect

Gated behind `settings.demo_mode` like the seeder: a link is a real money
instrument, and this must be unreachable from anything pointed at live keys.
See services/test_payment.py for the flow and why nothing here bypasses the
policy gate.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from razorpay.errors import BadRequestError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_demo_mode
from app.schemas.api import (
    PaymentReconcileRequest,
    PaymentReconcileResult,
    TestPaymentRequest,
    TestPaymentResult,
)
from app.services.test_payment import TestPaymentFailed, create_test_payment, reconcile

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/test-payment", tags=["test-payment"], dependencies=[Depends(require_demo_mode)]
)


@router.post("", response_model=TestPaymentResult)
def start_test_payment(req: TestPaymentRequest, db: Session = Depends(get_db)) -> TestPaymentResult:
    try:
        result = create_test_payment(
            db, amount_paise=req.amount_paise, customer_email=req.customer_email
        )
    except TestPaymentFailed as exc:
        # 502 with the case id: the case exists and its timeline carries the
        # executor's error, which is the most useful thing to point at.
        raise HTTPException(
            status_code=502, detail={"message": str(exc), "caseId": exc.case_id}
        ) from exc
    return TestPaymentResult(**result)


@router.post("/reconcile", response_model=PaymentReconcileResult)
def reconcile_test_payment(
    req: PaymentReconcileRequest, db: Session = Depends(get_db)
) -> PaymentReconcileResult:
    try:
        result = reconcile(
            db,
            payment_link_id=req.payment_link_id,
            payment_id=req.payment_id,
            reference_id=req.reference_id,
            link_status=req.payment_link_status,
            signature=req.signature,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BadRequestError as exc:
        # Razorpay answers a fetch for an id it has never issued with a 400
        # ("id does not exist"). To this API's caller that is "no such
        # link", not "Razorpay is down".
        raise HTTPException(
            status_code=404, detail=f"Razorpay has no payment link {req.payment_link_id}: {exc}"
        ) from exc
    except Exception as exc:  # noqa: BLE001 — a Razorpay API failure is a 502, not a 500
        log.exception("payment-link reconcile failed for %s", req.payment_link_id)
        raise HTTPException(
            status_code=502, detail=f"could not verify the payment with Razorpay: {exc}"
        ) from exc
    return PaymentReconcileResult(**result)
