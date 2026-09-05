// Where Razorpay sends the payer after a Payment Link is paid.
//
// Razorpay appends razorpay_payment_id, razorpay_payment_link_id,
// razorpay_payment_link_reference_id (= our case id),
// razorpay_payment_link_status and razorpay_signature to the callback URL.
// This page forwards them to the backend, which verifies the signature and
// then asks Razorpay's API whether the link is really paid before writing
// anything — the query string is the payer's to edit, so nothing here is
// trusted for a money decision. See backend/app/services/test_payment.py.
//
// The webhook may already have closed the case by the time this runs; the
// backend treats that as a no-op and this page reads the same "recovered".
// Either way the destination is the case's audit trail, which is the thing
// the operator came to see.

import { useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { api, ApiError } from '@/api/client'
import type { PaymentCallbackParams, PaymentReconcileResult } from '@/api/types'
import { ErrorNote, Loading } from '@/components/PageState'
import { IconCheck } from '@/components/icons'
import { formatPaise } from '@/lib/format'

const OPEN_TRAIL_AFTER_MS = 2500

const LINK_STATUS_LABEL: Record<string, string> = {
  created: 'not paid yet',
  partially_paid: 'partially paid',
  paid: 'paid',
  expired: 'expired',
  cancelled: 'cancelled',
}

function readParams(search: URLSearchParams): PaymentCallbackParams | null {
  const paymentLinkId = search.get('razorpay_payment_link_id')
  if (!paymentLinkId) return null
  return {
    paymentLinkId,
    paymentId: search.get('razorpay_payment_id') ?? undefined,
    referenceId: search.get('razorpay_payment_link_reference_id') ?? undefined,
    paymentLinkStatus: search.get('razorpay_payment_link_status') ?? undefined,
    signature: search.get('razorpay_signature') ?? undefined,
  }
}

export default function PaymentReturnPage() {
  const [search] = useSearchParams()
  const params = readParams(search)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['reconcile', params?.paymentLinkId, params?.paymentId],
    queryFn: () => api.reconcilePayment(params!),
    enabled: params !== null,
    // A Razorpay API blip on the way back should not strand the payer on an
    // error; a forged signature (400) or unknown link (404) should not be
    // retried at all.
    retry: (count, err) =>
      count < 2 && !(err instanceof ApiError && (err.status === 400 || err.status === 404)),
    staleTime: Infinity,
  })

  // Once recovered: refresh everything that shows this case, then open its
  // audit trail after a beat long enough to read the confirmation.
  useEffect(() => {
    if (!data?.recovered) return
    queryClient.invalidateQueries({ queryKey: ['cases'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    queryClient.invalidateQueries({ queryKey: ['case', data.caseId] })
    const timer = window.setTimeout(
      () => navigate(`/cases/${data.caseId}`, { replace: true }),
      OPEN_TRAIL_AFTER_MS,
    )
    return () => window.clearTimeout(timer)
  }, [data, navigate, queryClient])

  if (params === null) {
    return (
      <div className="stack">
        <header className="page-head">
          <h1 className="page-title">Payment return</h1>
        </header>
        <ErrorNote>
          This is where Razorpay sends you after paying a test link, and there is no payment link
          in the address. <Link to="/pay" style={{ color: 'inherit' }}>Make a test payment</Link>{' '}
          to start one.
        </ErrorNote>
      </div>
    )
  }

  return (
    <div className="stack">
      <header className="page-head">
        <h1 className="page-title">Payment return</h1>
        <p className="page-sub">
          Razorpay sent you back. The payment is being confirmed against Razorpay’s API before the
          case is closed — the redirect alone is never trusted.
        </p>
      </header>

      {isLoading && <Loading what="the payment status from Razorpay" />}

      {error && (
        <ErrorNote>
          {error instanceof ApiError && typeof error.detail === 'string'
            ? error.detail
            : 'Could not verify the payment with Razorpay.'}
          {params.referenceId && (
            <>
              {' '}
              <Link to={`/cases/${params.referenceId}`} style={{ color: 'inherit' }}>
                Open the case
              </Link>{' '}
              — if the webhook reached the server, it will already show as recovered.
            </>
          )}
        </ErrorNote>
      )}

      {data && <Result result={data} />}
    </div>
  )
}

function Result({ result }: { result: PaymentReconcileResult }) {
  if (result.recovered) {
    return (
      <section className="card pay-result" role="status" aria-live="polite">
        <span className="pay-result-mark" aria-hidden="true">
          <IconCheck size={22} />
        </span>
        <h2 className="pay-result-title">Payment verified</h2>
        <p className="pay-result-amount">{formatPaise(result.amountPaise)}</p>
        <p className="muted" style={{ margin: 0 }}>
          Case <span className="mono">{result.caseId}</span> is recovered
          {result.signatureValid === true && ', callback signature valid'}. Opening its audit
          trail…
        </p>
        <div className="pay-actions">
          <Link to={`/cases/${result.caseId}`} className="btn btn-primary">
            Open the audit trail →
          </Link>
          <Link to="/pay" className="btn">
            Make another
          </Link>
        </div>
      </section>
    )
  }

  const label = LINK_STATUS_LABEL[result.status] ?? result.status
  return (
    <section className="card pay-result" role="status" aria-live="polite">
      <h2 className="pay-result-title">Not recovered yet</h2>
      <p className="muted" style={{ margin: 0, maxWidth: '48ch' }}>
        Razorpay reports this link as <strong style={{ color: 'var(--ink)' }}>{label}</strong>, so
        no outcome was written. The case stays open until a payment against the link is confirmed.
      </p>
      <div className="pay-actions">
        {result.status === 'created' && result.paymentUrl && (
          <a href={result.paymentUrl} className="btn btn-primary">
            Pay the link →
          </a>
        )}
        <Link to={`/cases/${result.caseId}`} className="btn">
          Open the case
        </Link>
        <Link to="/pay" className="btn">
          Start over
        </Link>
      </div>
    </section>
  )
}
