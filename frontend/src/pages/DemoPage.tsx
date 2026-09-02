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
      <div className="card">
        <p style={{ margin: 0 }}>
          Demo controls are disabled on this server (<code>DEMO_MODE=false</code>). This is the
          correct state for anything pointed at live Razorpay keys.
        </p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <h1 style={{ fontSize: '1.4rem', margin: 0 }}>Demo controls</h1>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: '0.75rem' }}>1. Seed a batch</div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <label className="muted" style={{ fontSize: '0.85rem' }}>
            Count
            <input
              type="number"
              min={1}
              max={500}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              style={{ marginLeft: '0.4rem', width: 80 }}
            />
          </label>
          <label className="muted" style={{ fontSize: '0.85rem' }}>
            Seed (optional, for a reproducible run)
            <input
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              placeholder="42"
              style={{ marginLeft: '0.4rem', width: 80 }}
            />
          </label>
          <button
            className="btn btn-primary"
            onClick={() => seedMutation.mutate()}
            disabled={seedMutation.isPending}
          >
            Seed
          </button>
        </div>
        {seedMutation.data && (
          <p className="muted mono" style={{ fontSize: '0.85rem', marginTop: '0.5rem' }}>
            seeded {seedMutation.data.count} — by class {JSON.stringify(seedMutation.data.byClass)}
            , by arm {JSON.stringify(seedMutation.data.byArm)}
          </p>
        )}
        <table style={{ marginTop: '0.75rem', fontSize: '0.85rem' }}>
          <tbody>
            {CLASS_MIX.map(([label, pct]) => (
              <tr key={label}>
                <td className="muted" style={{ padding: '0.15rem 0.5rem 0.15rem 0' }}>
                  {label}
                </td>
                <td className="mono">{pct}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>2. Simulate customer behaviour</div>
        <p className="muted" style={{ fontSize: '0.85rem', margin: '0 0 0.75rem' }}>
          Every failed payment is simulated to pay or not, using the probabilities below — control
          cases self-recover too, and the treatment effect comes from salary-window timing, not a
          flat bonus for having been treated.
        </p>
        <button
          className="btn btn-primary"
          onClick={() => simulateMutation.mutate()}
          disabled={simulateMutation.isPending}
        >
          Simulate
        </button>
        {simulateMutation.data && (
          <p className="muted mono" style={{ fontSize: '0.85rem', marginTop: '0.5rem' }}>
            considered {simulateMutation.data.considered}, {simulateMutation.data.paid} paid
          </p>
        )}
        <div style={{ overflowX: 'auto', marginTop: '0.75rem' }}>
          <table style={{ fontSize: '0.85rem' }}>
            <thead>
              <tr>
                {PAYMENT_PROBABILITIES[0].map((h) => (
                  <th key={h} style={{ textAlign: 'left', padding: '0.2rem 0.6rem 0.2rem 0' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {PAYMENT_PROBABILITIES.slice(1).map((row) => (
                <tr key={row[0]}>
                  {row.map((cell, i) => (
                    <td key={i} className={i === 0 ? '' : 'mono'} style={{ padding: '0.2rem 0.6rem 0.2rem 0' }}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ borderColor: 'var(--danger)' }}>
        <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>3. Reset</div>
        <p className="muted" style={{ fontSize: '0.85rem', margin: '0 0 0.75rem' }}>
          Clears every case, action, outcome and audit event. Cannot be undone.
        </p>
        <button
          className="btn"
          style={{ borderColor: 'var(--danger)', color: 'var(--danger)' }}
          onClick={() => {
            if (confirm('Clear all demo data?')) resetMutation.mutate()
          }}
          disabled={resetMutation.isPending}
        >
          Reset all demo data
        </button>
      </div>
    </div>
  )
}
