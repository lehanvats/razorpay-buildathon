// Make a test payment: one simulated abandoned checkout, then a real
// Razorpay Payment Link the operator pays on Razorpay's own test checkout.
//
// The one place the product touches real money rails end to end. Everything
// the Demo page does is synthetic; here only the *failure* is — the link,
// the payment and the recovery are real, in test mode. The page says so in
// plain words (see the "What happens" card): naming the one simulated step
// beats letting a judge wonder which steps were.
//
// On success the browser is sent straight to the payment link. Razorpay
// brings the payer back to /pay/return (PaymentReturnPage), which verifies
// the payment server-side and opens the case's audit trail.
//
// Hidden when the backend has demo_mode off (the route 404s), same as Demo:
// a payment link is a real money instrument and must be unreachable from
// anything pointed at live keys.

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api, ApiError } from '@/api/client'
import { ErrorNote } from '@/components/PageState'
import { formatPaise } from '@/lib/format'

const STEPS = [
  {
    title: 'A checkout is abandoned',
    body: 'Simulated, for the amount you enter. The case manager opens a case, assigns the holdout arm and classifies it DROPOFF — the same code path a real payment.failed webhook takes.',
  },
  {
    title: 'A payment link is proposed',
    body: 'By you, not the model — the trail records “Operator proposed”, never “LLM proposed”. The policy gate still disposes: same rules, same verdict, same rule_id on the timeline.',
  },
  {
    title: 'Razorpay mints the link',
    body: 'The approved action runs through the real scheduler and executor, which calls Razorpay’s Payment Links API in test mode. You are redirected to the link.',
  },
  {
    title: 'You pay, and come back',
    body: 'Razorpay returns you here. The callback signature is verified, the link is fetched from Razorpay to confirm it is paid, and the case recovers through the same path a payment_link.paid webhook takes. The audit trail opens.',
  },
] as const

/** Rupees typed by the operator -> integer paise on the wire. Rounded, never
 * floored: 4.99 must become 499, not 498 from float error. */
function rupeesToPaise(rupees: string): number {
  return Math.round(Number(rupees) * 100)
}

export default function TestPaymentPage() {
  const [rupees, setRupees] = useState('499')
  const [email, setEmail] = useState('payer@example.com')
  const [disabled, setDisabled] = useState(false)
  const queryClient = useQueryClient()

  const create = useMutation({
    mutationFn: () => api.createTestPayment(rupeesToPaise(rupees), email.trim()),
    onError: (err) => {
      if (err instanceof ApiError && err.status === 404) setDisabled(true)
    },
    onSuccess: (data) => {
      // A case exists now; anything showing case counts is stale.
      queryClient.invalidateQueries({ queryKey: ['cases'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      // Straight to Razorpay. Full navigation, not window.open: the payer
      // comes back via Razorpay's own redirect, so this tab is the one that
      // should leave and return.
      window.location.assign(data.paymentUrl)
    },
  })

  const paise = rupeesToPaise(rupees)
  const amountValid = Number.isFinite(paise) && paise >= 100 && paise <= 50_000_000

  if (disabled) {
    return (
      <div className="stack">
        <header className="page-head">
          <h1 className="page-title">Make a test payment</h1>
        </header>
        <div className="notice">
          Test payments are disabled on this server (<code className="mono">DEMO_MODE=false</code>
          ). This is the correct state for anything pointed at live Razorpay keys.
        </div>
      </div>
    )
  }

  // FastAPI's 502 carries {message, caseId} so the failure can point at the
  // case whose timeline holds the executor's error.
  const failure =
    create.error instanceof ApiError && typeof create.error.detail === 'object' && create.error.detail
      ? (create.error.detail as { message?: string; caseId?: string | null })
      : create.error
        ? { message: create.error.message }
        : null

  return (
    <div className="stack">
      <header className="page-head">
        <h1 className="page-title">Make a test payment</h1>
        <p className="page-sub">
          One simulated abandoned checkout opens a real case. The policy gate approves a payment
          link, Razorpay mints it in test mode, you pay it, and the case closes with every step on
          its audit trail.
        </p>
      </header>

      <div className="pay-layout">
        <section className="card pay-form">
          <h2 className="card-title">Payment</h2>
          <form
            className="stack-tight"
            onSubmit={(e) => {
              e.preventDefault()
              if (amountValid && !create.isPending) create.mutate()
            }}
          >
            <div className="controls-row">
              <label className="field">
                <span className="field-label">Amount (₹)</span>
                <input
                  className="input mono"
                  type="number"
                  inputMode="decimal"
                  min={1}
                  max={500000}
                  step="0.01"
                  required
                  value={rupees}
                  onChange={(e) => setRupees(e.target.value)}
                  style={{ width: 140 }}
                  aria-describedby="pay-amount-hint"
                />
              </label>
              <label className="field" style={{ flex: 1, minWidth: 220 }}>
                <span className="field-label">Payer email</span>
                <input
                  className="input"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />
              </label>
            </div>
            <div className="pay-submit">
              <button
                className="btn btn-primary"
                type="submit"
                disabled={!amountValid || create.isPending}
              >
                {create.isPending ? 'Creating link…' : `Create link for ${amountValid ? formatPaise(paise) : '—'} and pay →`}
              </button>
              <span id="pay-amount-hint" className="stat-note" style={{ margin: 0 }}>
                ₹1 to ₹5,00,000. Test mode — no real money moves.
              </span>
            </div>
          </form>

          {failure && (
            <ErrorNote>
              {failure.message ?? 'The payment link could not be created.'}
              {failure.caseId && (
                <>
                  {' '}
                  <Link to={`/cases/${failure.caseId}`} style={{ color: 'inherit' }}>
                    Open the case
                  </Link>{' '}
                  — its audit trail records the failure.
                </>
              )}
            </ErrorNote>
          )}

          {create.data && (
            <p className="readout" role="status">
              case {create.data.caseId} · link {create.data.paymentLinkId} — redirecting to
              Razorpay… If nothing happens,{' '}
              <a href={create.data.paymentUrl} style={{ color: 'var(--brand-ink)' }}>
                open the payment link
              </a>
              .
            </p>
          )}

          <div className="notice notice--control">
            On Razorpay’s test checkout, pay with UPI id{' '}
            <code className="mono">success@razorpay</code> or any Razorpay test card. Test-mode
            links behave exactly like live ones; the money is not real.
          </div>
        </section>

        <section className="card">
          <h2 className="card-title">What happens</h2>
          <ol className="how-steps">
            {STEPS.map((step, i) => (
              <li key={step.title}>
                <span className="step-num" aria-hidden="true">
                  {i + 1}
                </span>
                <div>
                  <strong>{step.title}</strong> — {step.body}
                </div>
              </li>
            ))}
          </ol>
          <p className="stat-note" style={{ marginTop: 'var(--space-4)' }}>
            Only step 1 is simulated. The link, the payment and the recovery are real, in
            Razorpay test mode — and the case is a real case, held to the same rules as every
            other.
          </p>
        </section>
      </div>
    </div>
  )
}
