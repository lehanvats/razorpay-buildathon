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
  // An operator's proposal in the LLM's seat (the test-payment flow) — still
  // gated, just not model-written. Payload carries `reasoning` verbatim.
  | 'operator_proposed'
  // A payment link's `paid` status confirmed against Razorpay's API on the
  // payer's return redirect, as opposed to arriving by webhook.
  | 'payment_verified'

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

/** `POST /api/test-payment` — a case was opened and a real Razorpay Payment
 * Link minted against it; `paymentUrl` is where the operator goes to pay. */
export interface TestPaymentResult {
  caseId: string
  paymentLinkId: string
  paymentUrl: string
  amountPaise: number
  status: string
}

/** The query string Razorpay appends to the callback redirect after a
 * Payment Link is paid. Forwarded to the backend verbatim; only the link id
 * is guaranteed, since a payer can land on the return page without paying. */
export interface PaymentCallbackParams {
  paymentLinkId: string
  paymentId?: string
  referenceId?: string
  paymentLinkStatus?: string
  signature?: string
}

/** `POST /api/test-payment/reconcile`. `status` is Razorpay's own link
 * status (created | partially_paid | paid | expired | cancelled);
 * `recovered` is whether the case now has an outcome. */
export interface PaymentReconcileResult {
  caseId: string
  status: string
  recovered: boolean
  amountPaise: number
  paymentId: string | null
  paymentUrl: string | null
  signatureValid: boolean | null
}
