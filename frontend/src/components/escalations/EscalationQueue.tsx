// Human review queue.
//
// Each item names the rule_id that stopped the agent. "Compliant escalation"
// is a judged criterion, and an escalation without a stated cause is just a
// stuck case.
//
// Resolving records a human decision; it does not resume the agent. A case
// that hit a stopping rule stays stopped — make that explicit in the UI copy
// so it doesn't read as a broken button.

export function EscalationQueue() {
  // TODO(step-05)
  return null
}
