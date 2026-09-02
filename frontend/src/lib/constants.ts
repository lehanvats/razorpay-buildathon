// Display metadata for the enums the backend sends.
//
// Labels and colours only. The thresholds and rules themselves live in
// backend/app/policy/rules.py and must never be duplicated here — a
// compliance constant with two homes will eventually disagree with itself.

import type { FailureClass, Decision, Arm } from '@/api/types'

export const FAILURE_CLASS_LABEL: Record<FailureClass, string> = {
  HARD_DECLINE: 'Hard decline',
  SOFT_FUNDS: 'Insufficient funds',
  SOFT_TECHNICAL: 'Bank / gateway',
  DROPOFF: 'Abandoned',
}

export const FAILURE_CLASS_HINT: Record<FailureClass, string> = {
  HARD_DECLINE: 'Unrecoverable by design — never retried',
  SOFT_FUNDS: 'A timing problem — retried in the salary window',
  SOFT_TECHNICAL: 'A patience problem — waits out the degraded bank',
  DROPOFF: 'A persuasion problem — payment link, never an auto-charge',
}

export const DECISION_LABEL: Record<Decision, string> = {
  APPROVE: 'Approved',
  REWRITE: 'Amended by policy',
  BLOCK: 'Blocked by policy',
  ESCALATE: 'Escalated to human',
}

// Colour tokens are CSS custom-property names (see styles/index.css), not
// literal colour values — the light/dark swap happens in CSS, this module
// just says which token a given decision/class means.
export const DECISION_COLOR_VAR: Record<Decision, string> = {
  APPROVE: '--accent',
  REWRITE: '--accent',
  BLOCK: '--danger',
  ESCALATE: '--warn',
}

export const ARM_LABEL: Record<Arm, string> = {
  treatment: 'Treatment',
  control: 'Control (held out)',
}

/** The semantic families a badge can wear. Each maps to a `--x` / `--x-weak`
 * / `--x-ink` token triple in styles/index.css; `neutral` is the un-tinted
 * surface used for states that are simply in progress. */
export type Tone = 'accent' | 'warn' | 'danger' | 'control' | 'neutral'

/** Case statuses as the backend spells them (`app/db/models.py`). Unknown
 * values fall back to the raw string and a neutral tone, so a status added
 * on the backend degrades to plain text rather than rendering blank. */
export const STATUS_LABEL: Record<string, string> = {
  open: 'Open',
  scheduled: 'Scheduled',
  awaiting_customer: 'Awaiting customer',
  recovered: 'Recovered',
  escalated: 'Escalated',
  exhausted: 'Budget exhausted',
  control_observed: 'Observed only',
}

export const STATUS_TONE: Record<string, Tone> = {
  open: 'neutral',
  scheduled: 'neutral',
  awaiting_customer: 'neutral',
  recovered: 'accent',
  escalated: 'warn',
  // Not a failure of the agent — the attempt budget ran out, which is the
  // NPCI cap working. Amber rather than red.
  exhausted: 'warn',
  control_observed: 'control',
}
