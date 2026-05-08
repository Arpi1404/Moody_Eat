import { NavLink, useNavigate } from 'react-router-dom'

function HomeIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden fill="none">
      <path
        d="M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1v-8.5z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function SavedIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden fill="none">
      <path
        d="M7 3.5h10A2.5 2.5 0 0 1 19.5 6v15l-7.5-4.4L4.5 21V6A2.5 2.5 0 0 1 7 3.5z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function JournalIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden fill="none">
      <path
        d="M6 4.5h9.5A2.5 2.5 0 0 1 18 7v12.5H7A2.5 2.5 0 0 1 4.5 17V6A1.5 1.5 0 0 1 6 4.5z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path
        d="M8 9h6m-6 4h4"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  )
}

function ProfileIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden fill="none">
      <circle cx="12" cy="8.5" r="3.6" stroke="currentColor" strokeWidth="1.7" />
      <path
        d="M4.5 20c1.4-3.6 4.4-5.4 7.5-5.4s6.1 1.8 7.5 5.4"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function BottomNav() {
  const navigate = useNavigate()
  const openPlanner = () => navigate('/?plan=date')

  return (
    <nav className="bottom-nav" aria-label="Primary">
      <NavLink to="/" end className="bottom-nav-item">
        <HomeIcon />
        <span>Home</span>
      </NavLink>
      <NavLink to="/saved" className="bottom-nav-item">
        <SavedIcon />
        <span>Saved</span>
      </NavLink>
      <button
        type="button"
        className="bottom-nav-fab"
        onClick={openPlanner}
        aria-label="Plan a quest"
      >
        <span className="bottom-nav-fab-glyph" aria-hidden>✦</span>
      </button>
      <NavLink to="/journal" className="bottom-nav-item">
        <JournalIcon />
        <span>Journal</span>
      </NavLink>
      <button
        type="button"
        className="bottom-nav-item bottom-nav-item--placeholder"
        disabled
        aria-label="Profile (coming soon)"
        title="Coming soon"
      >
        <ProfileIcon />
        <span>Profile</span>
      </button>
    </nav>
  )
}

export default BottomNav
