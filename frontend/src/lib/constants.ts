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
