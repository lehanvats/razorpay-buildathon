// Demo controls: seed a batch, run the customer simulator, reset.
//
// Hidden when the backend has demo_mode off (the /api/demo routes 404).
//
// Show the simulation assumptions on this page — the per-class payment
// probabilities, stated plainly. Naming the simulation is more credible than
// letting a judge discover it.
//
// Numbers below must be kept in sync by hand with
// backend/app/services/seeding.FAILURE_CLASS_MIX and
// backend/app/services/simulation.PAYMENT_PROBABILITIES — there is no
// endpoint that exposes them, since they are simulator internals, not part
// of the recovery agent's own contract.

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api, ApiError } from '@/api/client'

const CLASS_MIX = [
  ['Insufficient funds', '35%'],
  ['Bank / gateway technical', '30%'],
  ['Abandoned checkout', '20%'],
  ['Hard decline', '15%'],
] as const

const PAYMENT_PROBABILITIES = [
  ['Class', 'Control (baseline)', 'Treated, in salary window', 'Treated, off window'],
  ['Insufficient funds', '15%', '55%', '20%'],
  ['Bank / gateway technical', '25%', '50%', '35%'],
  ['Abandoned checkout', '20%', '45%', '—'],
  ['Hard decline', '2%', '2%', '— (never treated)'],
] as const

function Step({
  n,
  title,
  children,
  danger,
}: {
  n: number
  title: string
  children: React.ReactNode
  danger?: boolean
}) {
  return (
    <section className={`card${danger ? ' card--danger' : ''}`}>
      <div className="step-head">
        <span className="step-num">{n}</span>
        <h2 className="card-title">{title}</h2>
      </div>
      {children}
    </section>
  )
}

export default function DemoPage() {
  const [count, setCount] = useState(100)
  const [seed, setSeed] = useState<string>('')
  const [disabled, setDisabled] = useState(false)
  const queryClient = useQueryClient()

  function onError(err: unknown) {
    if (err instanceof ApiError && err.status === 404) setDisabled(true)
  }
  function onSettled() {
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    queryClient.invalidateQueries({ queryKey: ['cases'] })
    queryClient.invalidateQueries({ queryKey: ['escalations'] })
  }

  const seedMutation = useMutation({
    mutationFn: () => api.seed(count, seed ? Number(seed) : undefined),
    onError,
    onSettled,
  })
  const simulateMutation = useMutation({
    mutationFn: api.simulate,
    onError,
    onSettled,
  })
  const resetMutation = useMutation({
    mutationFn: api.reset,
    onError,
    onSettled,
  })

  if (disabled) {
    return (
      <div className="stack">
        <header className="page-head">
          <h1 className="page-title">Demo controls</h1>
        </header>
        <div className="notice">
          Demo controls are disabled on this server (<code className="mono">DEMO_MODE=false</code>
          ). This is the correct state for anything pointed at live Razorpay keys.
        </div>
      </div>
    )
  }

  return (
    <div className="stack">
      <header className="page-head">
        <h1 className="page-title">Demo controls</h1>
        <p className="page-sub">
          Seed a batch of failed payments, then play the customers paying or not. Customer
          behaviour is simulated and the assumptions are stated below — naming the simulation
          beats hiding it.
        </p>
      </header>

      <Step n={1} title="Seed a batch">
        <div className="controls-row">
          <label className="field">
            <span className="field-label">Count</span>
            <input
              className="input"
              type="number"
              min={1}
              max={500}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              style={{ width: 96 }}
            />
          </label>
          <label className="field">
            <span className="field-label">Seed (optional)</span>
            <input
              className="input"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              placeholder="42"
              style={{ width: 96 }}
            />
          </label>
          <button
            className="btn btn-primary"
            onClick={() => seedMutation.mutate()}
            disabled={seedMutation.isPending}
          >
            {seedMutation.isPending ? 'Seeding…' : 'Seed'}
          </button>
          <span className="muted" style={{ fontSize: 'var(--text-sm)', paddingBottom: 6 }}>
            A seed makes the run reproducible.
          </span>
        </div>

        {seedMutation.data && (
          <p className="readout" role="status">
            seeded {seedMutation.data.count} — by class{' '}
            {JSON.stringify(seedMutation.data.byClass)}, by arm{' '}
            {JSON.stringify(seedMutation.data.byArm)}
          </p>
        )}

        <table className="mini-table" style={{ marginTop: 'var(--space-4)' }}>
          <caption className="field-label" style={{ textAlign: 'left', paddingBottom: 4 }}>
            Failure-class mix
          </caption>
          <tbody>
            {CLASS_MIX.map(([label, pct]) => (
              <tr key={label}>
                <td className="muted">{label}</td>
                <td className="mono">{pct}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Step>

      <Step n={2} title="Simulate customer behaviour">
        <p className="stat-note" style={{ marginBottom: 'var(--space-3)' }}>
          Every failed payment is simulated to pay or not, using the probabilities below — control
          cases self-recover too, and the treatment effect comes from salary-window timing, not a
          flat bonus for having been treated.
        </p>
        <button
          className="btn btn-primary"
          onClick={() => simulateMutation.mutate()}
          disabled={simulateMutation.isPending}
        >
          {simulateMutation.isPending ? 'Simulating…' : 'Simulate'}
        </button>

        {simulateMutation.data && (
          <p className="readout" role="status">
            considered {simulateMutation.data.considered}, {simulateMutation.data.paid} paid
          </p>
        )}

        <div style={{ overflowX: 'auto', marginTop: 'var(--space-4)' }}>
          <table className="mini-table">
            <thead>
              <tr>
                {PAYMENT_PROBABILITIES[0].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {PAYMENT_PROBABILITIES.slice(1).map((row) => (
                <tr key={row[0]}>
                  {row.map((cell, i) => (
                    <td key={i} className={i === 0 ? 'muted' : 'mono'}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Step>

      <Step n={3} title="Reset" danger>
        <p className="stat-note" style={{ marginBottom: 'var(--space-3)' }}>
          Clears every case, action, outcome and audit event. Cannot be undone.
        </p>
        <button
          className="btn btn-danger"
          onClick={() => {
            if (confirm('Clear all demo data?')) resetMutation.mutate()
          }}
          disabled={resetMutation.isPending}
        >
          {resetMutation.isPending ? 'Resetting…' : 'Reset all demo data'}
        </button>
      </Step>
    </div>
  )
}
