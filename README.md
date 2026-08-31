# Recoup

A payment-failure recovery agent for Indian payment rails.

**The LLM proposes, a policy engine disposes, and a built-in holdout proves the recovery is real.**

Razorpay Buildathon — Track 3, AI Revenue Recovery.

> **Status: scaffolding.** Structure and contracts are in place; implementations
> are stubbed with `NotImplementedError` and tagged by build step (`step-01` …
> `step-08`).

---

## Why this is not another dunning tool

Recovery itself is a commodity — Stripe Smart Retries, Recurly, Butter, FlyCode,
and Razorpay's own Failed Payment Recovery all do ML retries plus dunning. Three
things here are not commodity:

**Compliance-native retries.** In India every retry lives inside a rulebook: RBI's
24-hour pre-debit notification, AFA above ₹15,000, NPCI's hard cap of 1 debit + 3
retries. US tools ignore it. Recoup makes the rulebook the engine.

**Rail-aware timing.** When regulation gives you exactly three retries, each one is
scarce. Insufficient funds → salary-window scheduling. Bank technical decline →
wait out the degraded bank. Hard decline → never spend an attempt at all.

**Honest attribution.** ~21% of failed payments recover on their own before any
outreach, yet every vendor books them as wins. Recoup holds out 20% of cases as an
untouched control group and reports *incremental* recovery — the number no product
in this market publishes.

---

## The compliance rulebook

Every rule is a deterministic, individually tested function. A blocked proposal is
always logged with the `rule_id` that blocked it. Source: `backend/app/policy/rules.py`.

| Rule | Trigger | Effect | Grounded in |
|---|---|---|---|
| Hard-decline block | `failure_class = HARD_DECLINE` | Never retry, never message; escalate | Card-network rules; fraud hygiene |
| Attempt budget | Any charge attempt | ≤ 1 original + 3 retries per case, then stop | NPCI AutoPay cap |
| Pre-debit notice | Mandate/subscription retry | Customer notified ≥ 24h before debit; retry scheduled after | RBI e-mandate framework |
| AFA threshold | Amount > ₹15,000 | No auto-charge; customer-authenticated payment link only | RBI e-mandate framework |
| Salary window | `SOFT_FUNDS` | Retry scheduled into the 1st–5th, or +72h, whichever is nearer | NACH bounce pattern |
| Contact cooldown | Any outreach | ≥ 24h between messages, ≤ 3 messages per case | Anti-spam; brand safety |
| Discount bound | `OFFER_DISCOUNT` | ≤ 10%, once per case, expires in 48h | Margin cap |
| Stopping rule | Budget exhausted or `confidence < 0.6` | Escalate to human queue; agent goes silent | Compliant escalation |

---

## Architecture

```
Razorpay webhook  ──▶  case opened  ──┬──▶  control 20%: observed, no action ever
                                      │
                                      └──▶  treatment 80%
                                              │
                                              ▼
                                     diagnosis (LLM proposes)
                                              │  Proposal
                                              ▼
                                   ╔══════════════════════╗
                                   ║  POLICY GATE         ║  ← sole path to money
                                   ║  RBI · NPCI · budget ║
                                   ╚══════════════════════╝
                                        │           │
                            Verdict     ▼           ▼  blocked
                                   executors    escalation queue
                                        │
                                   scheduler (durable delay across days)
                                        │
        every step ──────────▶  append-only audit trail  ──────▶  dashboard
                                                                  gross vs incremental
```

The design invariant everything hangs on: **the LLM can only propose; the policy
gate is the sole path to any money action.** It is enforced by types — executors
accept a `Verdict`, never a `Proposal` — and by purity: `app/policy/` imports
nothing from `app/db/`, `app/integrations/`, or `app/executors/`.

### Failure taxonomy

| Class | Meaning | Strategy |
|---|---|---|
| `HARD_DECLINE` | Stolen/blocked card, revoked mandate | Unrecoverable — never spend an attempt |
| `SOFT_FUNDS` | Insufficient balance | A *timing* problem — salary-window retry |
| `SOFT_TECHNICAL` | Bank/gateway timeout | A *patience* problem — wait out the bank |
| `DROPOFF` | Customer abandoned | A *persuasion* problem — link + dunning |

---

## Layout

```
backend/                    FastAPI, Python 3.12
  app/
    core/                   taxonomy · holdout · audit   (pure, no I/O)
    policy/                 snapshot · rules · gate      (pure, no I/O)
    agent/                  prompts · providers · diagnose  (proposes only)
    executors/              retry · payment_link · dunning  (takes Verdicts)
    scheduler/              durable delayed execution
    services/               case lifecycle · metrics
    api/routes/             webhooks · cases · dashboard · escalations · demo
    db/                     SQLAlchemy models, session
    schemas/                proposal (LLM contract) · api (HTTP contract)
  scripts/                  batch seeder · customer simulator
  tests/                    policy and holdout tests run with no database
frontend/                   React 18 + TypeScript + Vite
  src/components/dashboard/ the gross-vs-incremental headline
  src/components/cases/     the audit timeline — the explainability view
```

---

## Running it

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in Razorpay TEST-mode keys
alembic upgrade head
uvicorn app.main:app --reload # :8000

# Scheduler — a separate process, so restarting the API never drops a
# pending retry
python -m app.scheduler.poller

# Frontend
cd frontend
npm install
cp .env.example .env.local
npm run dev                   # :5173, proxies /api to :8000
```

Point a Razorpay test-mode webhook at `POST /api/webhooks/razorpay` for
`payment.failed`, `payment.captured`, `order.paid`, `payment_link.paid`.

Tests: `cd backend && pytest`. The policy and holdout suites need no database.

---

## Demo simulation — stated assumptions

Customer behaviour in the batch demo is **simulated**. Saying so is deliberate: a
judged demo that names its simulation beats one that hides it.

- Control cases self-recover at a non-zero baseline rate. If the simulator only
  paid treated cases, the control rate would be zero by construction and the
  incremental number would be fabricated rather than measured.
- The treatment effect comes from *timing*, not a thumb on the scale: a
  `SOFT_FUNDS` case is likelier to pay when retried inside the salary window than
  outside it. That is the mechanism claimed, so it is the mechanism modelled.
- Per-class probabilities live in `backend/scripts/simulate_customers.py` and are
  reproduced here once tuned.
- With ~100 cases a 20% holdout is ~20 control cases, so the incremental estimate
  is **noisy**. The dashboard says so.

Incremental recovery can come out negative. It is not clamped — a floor at zero
would quietly reintroduce exactly the dishonesty the holdout exists to prevent.

---

## Stack

| Layer | Choice |
|---|---|
| API + webhooks | FastAPI (Python 3.12) |
| Database | Postgres (Neon) + SQLAlchemy + Alembic |
| Durable steps | `actions.scheduled_for` + claiming poller (`FOR UPDATE SKIP LOCKED`) |
| LLM | Claude (primary) · Gemini Flash (zero-cost fallback) |
| Email | Resend (100/day free) |
| Payments | Razorpay **test mode**: Orders, Payment Links, webhooks |
| Frontend | React 18 + TypeScript + Vite |

Money is integer **paise** end to end — never float, never rupees, formatted only
at the UI edge.
