// Verdict badge: decision + the rule_id that produced it.
//
// The rule_id is always shown, never hidden behind a tooltip. During the demo
// the camera lands on HARD_DECLINE_BLOCK for exactly this reason — "the gate
// blocked it, and here is the named rule that did" is the whole beat.
//
// The decision is carried three ways so it never rests on colour alone: the
// tint, a shape (check / cross / triangle), and an `aria-label` that spells
// out the decision for anyone not reading either.

import type { Decision } from '@/api/types'
import { IconBlock, IconCheck, IconEscalation } from '@/components/icons'
import { DECISION_COLOR_VAR, DECISION_LABEL } from '@/lib/constants'

const DECISION_ICON: Record<Decision, () => JSX.Element> = {
  APPROVE: () => <IconCheck size={12} />,
  REWRITE: () => <IconCheck size={12} />,
  BLOCK: () => <IconBlock size={12} />,
  ESCALATE: () => <IconEscalation size={12} />,
}

export function PolicyVerdictBadge({ decision, ruleId }: { decision: Decision; ruleId: string }) {
  const colorVar = DECISION_COLOR_VAR[decision]
  const Icon = DECISION_ICON[decision]
  return (
    <span
      className="badge mono"
      // `--x-weak` fill with `--x-ink` text: the pairing the palette
      // contrast-checks. Both halves are built by concatenation from the same
      // `colorVar`, so the triple must stay whole in styles/index.css.
      style={{ background: `var(${colorVar}-weak)`, color: `var(${colorVar}-ink)` }}
      aria-label={`${DECISION_LABEL[decision]}: rule ${ruleId}`}
      title={DECISION_LABEL[decision]}
    >
      <Icon />
      {ruleId}
    </span>
  )
}
