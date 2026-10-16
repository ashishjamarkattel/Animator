import { Link } from 'react-router-dom'

/** `compact` shows only the mark, for the icon rail. */
export function Logo({ to = '/', compact = false }: { to?: string; compact?: boolean }) {
  return (
    <Link to={to} className="logo" aria-label="Animator home">
      <svg width={compact ? 34 : 28} height={compact ? 34 : 28} viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="7" fill="var(--tray)" />
        <path d="M7 21c3-7 6-11 8-11s1 8 3 8 3-5 7-9" fill="none" stroke="var(--marker-blue-bright)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {!compact && <span>Animator</span>}
    </Link>
  )
}
