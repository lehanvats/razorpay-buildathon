// Badge surfaces derived from a semantic tone.
//
// A tone names a `--x` / `--x-weak` / `--x-ink` triple in styles/index.css.
// Resolving it here — in one place, from a typed `Tone` — keeps the rest of
// the app from hand-writing `var(--warn-weak)` string pairs at each call
// site, which is how a renamed token turns into an invisible badge.

import type { Tone } from '@/lib/constants'
import { STATUS_LABEL, STATUS_TONE } from '@/lib/constants'

/** Inline style for a tinted badge: the -weak fill with its matching -ink
 * text, which is the pairing the palette contrast-checks. */
export function toneStyle(tone: Tone): React.CSSProperties {
  if (tone === 'neutral') {
    return { background: 'var(--surface-2)', color: 'var(--muted)' }
  }
  return { background: `var(--${tone}-weak)`, color: `var(--${tone}-ink)` }
}

export function ToneBadge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span className="badge" style={toneStyle(tone)}>
      {children}
    </span>
  )
}

/** A case status, rendered with the tone its meaning implies. Falls back to
 * the raw backend string so a newly added status degrades to plain text
 * instead of an empty badge. */
export function StatusBadge({ status }: { status: string }) {
  return (
    <ToneBadge tone={STATUS_TONE[status] ?? 'neutral'}>
      {STATUS_LABEL[status] ?? status}
    </ToneBadge>
  )
}
