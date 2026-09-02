// One case: header facts plus the full audit timeline.
//
// The explainability view. Deep-linkable by case id so the demo can jump
// straight to the seeded HARD_DECLINE case where the gate blocks a retry.
//
// Retagged step-07 -> step-08 (backend audit trail landed; this component
// didn't): App.tsx's routing, main.tsx's render call and api/client.ts's
// fetch wrapper are all still stubs, so this page has no router to mount
// under and no working way to call GET /api/cases/{id} yet. Building it now
// would be dead code step-08 has to touch anyway to wire up — same call as
// corrections.md #8 on the escalations screen. Backend is proven instead by
// tests/test_cases_api.py, which exercises the real route end-to-end.

export default function CaseDetailPage() {
  // TODO(step-08)
  return null
}
