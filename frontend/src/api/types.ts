// Mirrors backend/app/schemas/api.py. Keep the two in sync by hand for now;
// if this drifts often, generate from the FastAPI OpenAPI schema instead.
//
// Money crosses the wire as integer paise, never rupees and never a float.
// Format at the edge with lib/format.ts.

export type FailureClass =
  | 'HARD_DECLINE'
  | 'SOFT_FUNDS'
  | 'SOFT_TECHNICAL'
  | 'DROPOFF'

export type Arm = 'treatment' | 'control'

export type Decision = 'APPROVE' | 'REWRITE' | 'BLOCK' | 'ESCALATE'

export type Actor =
  | 'webhook'
  | 'llm'
  | 'policy'
  | 'executor'
  | 'scheduler'
  | 'human'

export interface CaseSummary {
  // TODO(step-08): id, orderId, amountPaise, method, failureClass, arm,
  // status, attemptsUsed, createdAt, recoveredAmountPaise
}

export interface TimelineEntry {
  // TODO(step-07): ts, actor, eventType, payload, ruleId
}

export interface CaseDetail extends CaseSummary {
  // TODO(step-07): timeline: TimelineEntry[]
}

export interface DashboardMetrics {
  // TODO(step-08): funnel, grossRecoveredPaise, incrementalRecoveredPaise,
  // treatment, control, byFailureClass, escalationsOpen
}

export interface EscalationItem {
  // TODO(step-05): case, reason, ruleId, blockedDecision, escalatedAt
}
