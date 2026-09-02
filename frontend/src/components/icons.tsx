// Inline SVG icon set.
//
// Inline rather than an icon package: there are eight of them, they are
// stroke-only, and a dependency would cost more than it saves. Every icon
// draws with `currentColor` so it inherits the colour of whatever it sits
// in — a nav item, a badge, a button — and never needs its own token.
//
// All icons are decorative. Each one is labelled by adjacent text, so they
// carry `aria-hidden` and are skipped by screen readers rather than being
// announced as a second, redundant copy of the label next to them.

interface IconProps {
  /** Square edge length in px. Defaults to 16, the size used in nav and badges. */
  size?: number
}

function Svg({ size = 16, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ flexShrink: 0 }}
    >
      {children}
    </svg>
  )
}

/** Dashboard — a bar-chart read as "the numbers". */
export function IconDashboard(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 21h18" />
      <rect x="5" y="12" width="4" height="7" rx="1" />
      <rect x="14" y="6" width="4" height="13" rx="1" />
    </Svg>
  )
}

/** Cases — stacked rows, the list. */
export function IconCases(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18M9 9v11" />
    </Svg>
  )
}

/** Escalations — the warning triangle. Reserved for the human queue. */
export function IconEscalation(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4M12 17h.01" />
    </Svg>
  )
}

/** Demo — sliders, the control panel. */
export function IconDemo(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3" />
      <path d="M1 14h6M9 8h6M17 16h6" />
    </Svg>
  )
}

/** Back navigation. */
export function IconArrowLeft(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </Svg>
  )
}

/** A policy approval / a completed step. */
export function IconCheck(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M20 6 9 17l-5-5" />
    </Svg>
  )
}

/** A policy block. */
export function IconBlock(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m5.6 5.6 12.8 12.8" />
    </Svg>
  )
}

/** Scheduled / waiting — the durable delay across days. */
export function IconClock(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </Svg>
  )
}
