import { NavLink } from 'react-router-dom'

const LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/games', label: 'Games' },
  { to: '/mistakes', label: 'Mistakes' },
  { to: '/stats', label: 'Stats' },
  { to: '/settings', label: 'Settings' },
] as const

export function TopNav() {
  return (
    <header className="top-nav">
      <div className="masthead-brand">
        <span className="masthead-mark">Mistake Tracker</span>
        <span className="masthead-subtitle">A Personal Chess Journal</span>
      </div>
      <nav>
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={'end' in link ? link.end : false}
            className={({ isActive }) => (isActive ? 'active' : undefined)}
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
    </header>
  )
}
