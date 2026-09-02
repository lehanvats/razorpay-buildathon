// Verdict badge: decision + the rule_id that produced it.
//
// The rule_id is always shown, never hidden behind a tooltip. During the demo
// the camera lands on HARD_DECLINE_BLOCK for exactly this reason — "the gate
// blocked it, and here is the named rule that did" is the whole beat.

import type { Decision } from '@/api/types'
import { DECISION_COLOR_VAR, DECISION_LABEL } from '@/lib/constants'

export function PolicyVerdictBadge({ decision, ruleId }: { decision: Decision; ruleId: string }) {
  const colorVar = DECISION_COLOR_VAR[decision]
  return (
    <span
      className="badge mono"
      style={{ background: `var(${colorVar}-weak)`, color: `var(${colorVar})` }}
      title={DECISION_LABEL[decision]}
    >
      {ruleId}
    </span>
  )
}
