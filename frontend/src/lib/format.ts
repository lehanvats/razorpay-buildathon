// Formatting helpers.

/**
 * Paise -> displayed rupees, in the Indian digit grouping (1,23,456 — lakhs
 * and crores, not thousands). `Intl.NumberFormat('en-IN')` handles this;
 * hand-rolled grouping will be wrong and an Indian judging panel will notice
 * immediately.
 */
export function formatPaise(paise: number): string {
  // TODO(step-08): Intl.NumberFormat('en-IN', { style: 'currency',
  // currency: 'INR', maximumFractionDigits: 0 }) over paise / 100
  throw new Error('not implemented')
}

/** Percentage with one decimal, for recovery rates. */
export function formatRate(rate: number): string {
  throw new Error('not implemented')
}

/** Timestamps render in IST — the salary-window logic reasons in IST, so a
 * timeline shown in UTC would make correct scheduling look wrong. */
export function formatIST(iso: string): string {
  throw new Error('not implemented')
}
