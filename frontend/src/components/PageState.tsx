// Shared loading and error states.
//
// Every page fetches and so every page needs these two. Keeping them in one
// place stops four pages drifting into four different ways of saying the
// same thing — and gives the error case a real surface rather than a line of
// red text, which is easy to miss on a dense screen.

/** Announced politely so a screen reader hears that a fetch is in flight
 * without the message stealing focus. */
export function Loading({ what }: { what: string }) {
  return (
    <p className="muted" role="status">
      Loading {what}…
    </p>
  )
}

/** `role="alert"` because a failed fetch is the one thing on the page the
 * reader must not miss. */
export function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="card card--danger"
      role="alert"
      style={{ color: 'var(--danger)', maxWidth: '60ch' }}
    >
      {children}
    </div>
  )
}
