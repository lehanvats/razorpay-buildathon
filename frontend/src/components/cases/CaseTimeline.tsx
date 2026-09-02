// The audit trail, rendered. This is the screen judges read.
//
//   webhook received
//   classified SOFT_FUNDS
//   LLM proposed retry Sep 2, 10:00 IST   <- reasoning shown VERBATIM
//   policy approved (SALARY_WINDOW_RESCHEDULE)
//   pre-debit notice sent
//   retry executed
//   recovered Rs 1,499
//
// Two rules for this component:
//
//  1. Render the model's reasoning paragraph verbatim. Do not truncate it
//     behind a "show more" — the explainability claim is that you can read
//     exactly what the model said and exactly what the policy did about it.
//  2. Never filter or reorder events. A redacted audit trail is not an audit
//     trail. Order by timestamp ascending, show everything.
//
// Retagged step-07 -> step-08: see CaseDetailPage.tsx's note. The backend
// this renders (GET /api/cases/{id} -> CaseDetail.timeline, already ordered
// (ts, id) ascending by services/case_manager.get_timeline) is done and
// tested; this component has no app shell to mount into yet.

export function CaseTimeline() {
  // TODO(step-08)
  return null
}
