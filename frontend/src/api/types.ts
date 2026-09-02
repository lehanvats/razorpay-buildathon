// Mirrors backend/app/schemas/api.py. Keep the two in sync by hand for now;
// if this drifts often, generate from the FastAPI OpenAPI schema instead.
//
// Money crosses the wire as integer paise, never rupees and never a float.
// Format at the edge with lib/format.ts.

export type FailureClass = 'HARD_DECLINE' | 'SOFT_FUNDS' | 'SOFT_TECHNICAL' | 'DROPOFF'

export const FAILURE_CLASSES: FailureClass[] = [
  'HARD_DECLINE',
  'SOFT_FUNDS',
  'SOFT_TECHNICAL',
  'DROPOFF',
]

export type Arm = 'treatment' | 'control'

export type Decision = 'APPROVE' | 'REWRITE' | 'BLOCK' | 'ESCALATE'

export type Actor = 'webhook' | 'llm' | 'policy' | 'executor' | 'scheduler' | 'human'

export type EventType =
  | 'webhook_received'
  | 'case_opened'
  | 'arm_assigned'
  | 'classified'
  | 'llm_proposed'
  | 'llm_rejected'
  | 'policy_approved'
  | 'policy_blocked'
  | 'action_scheduled'
  | 'action_started'
  | 'action_completed'
  | 'action_failed'
  | 'escalated'
  | 'recovered'
  | 'escalation_resolved'

export interface CaseSummary {
  id: string
  orderId: string
  amountPaise: number
  method: string
  failureClass: FailureClass
  arm: Arm
  status: string
  attemptsUsed: number
  createdAt: string
  recoveredAmountPaise: number | null
}

export interface TimelineEntry {
  ts: string
  actor: Actor
  eventType: EventType
  payload: Record<string, unknown>
  ruleId: string | null
}

export interface CaseDetail extends CaseSummary {
  timeline: TimelineEntry[]
}

export interface FunnelCounts {
  failed: number
  eligible: number
  treated: number
  recovered: number
}

export interface ArmMetrics {
  arm: Arm
  cases: number
  recoveredCases: number
  recoveredAmountPaise: number
  recoveryRate: number
}

export interface DashboardMetrics {
  funnel: FunnelCounts
  grossRecoveredPaise: number
  incrementalRecoveredPaise: number
  treatment: ArmMetrics
  control: ArmMetrics
  byFailureClass: Partial<Record<FailureClass, ArmMetrics>>
  escalationsOpen: number
}

export interface EscalationItem {
  case: CaseSummary
  reason: string
  ruleId: string
  blockedDecision: Decision
  escalatedAt: string
}

export interface SeedResult {
  count: number
  byClass: Record<string, number>
  byArm: Record<string, number>
}

export interface SimulateResult {
  considered: number
  paid: number
}
