// The headline: two counters, side by side, equal visual weight.
//
//   Gross recovered        what every vendor in this market reports
//   Incremental recovered  treated minus control — what we actually caused
//
// Design intent: do NOT make gross the hero and incremental a footnote. The
// whole pitch is that we publish the smaller, honest number next to the
// flattering one. Equal size, equal prominence, incremental labelled clearly
// as the real figure.
//
// Incremental can be negative. Render that plainly rather than hiding or
// clamping it — a floor would reintroduce exactly the dishonesty the holdout
// exists to prevent.

export function RecoveryCounters() {
  // TODO(step-08): two stat tiles + a one-line explainer of the difference
  return null
}
