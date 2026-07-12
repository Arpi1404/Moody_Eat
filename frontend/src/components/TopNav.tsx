import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'

function LogoMark() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      fill="none"
      aria-hidden
    >
      <path
        d="M9 2C9 2 4 5 4 10C4 12.76 6.24 15 9 15C11.76 15 14 12.76 14 10C14 5 9 2 9 2Z"
        fill="white"
        opacity="0.92"
      />
      <circle cx="9" cy="10" r="2.5" fill="white" />
    </svg>
  )
}

export function TopNav() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [scrolled, setScrolled] = useState(false)
  // True when the hero "Start a quest" CTA is in view — we hide our nav CTA then
  const [heroCtaInView, setHeroCtaInView] = useState(false)

  // Track scroll position for borderless-at-top → bordered-when-scrolled
  useEffect(() => {
    const onScroll = () => {
      setScrolled(window.scrollY > 8)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Hide our nav CTA while the hero "Start a quest" CTA is on screen.
  // Uses a scroll/resize listener (more reliable across browsers than IO).
  useEffect(() => {
    // Off the homepage the stale value is masked at render (ctaHidden below),
    // so no state reset is needed here.
    if (pathname !== '/') return

    let frame = 0
    const check = () => {
      const target = document.querySelector<HTMLElement>('.home-cta-primary')
      if (!target) {
        setHeroCtaInView(false)
        return
      }
      const rect = target.getBoundingClientRect()
      const navHeight = 64 // matches .topnav height
      // "In view" = at least partially visible below the nav and above the fold
      const inView = rect.bottom > navHeight && rect.top < window.innerHeight
      setHeroCtaInView(inView)
    }

    const onScrollOrResize = () => {
      if (frame) return
      frame = window.requestAnimationFrame(() => {
        frame = 0
        check()
      })
    }

    // Run once after the hero mounts (HomePage may render after this effect)
    const initial = window.requestAnimationFrame(check)
    // And again a tick later in case fonts/layout shift
    const settle = window.setTimeout(check, 250)

    window.addEventListener('scroll', onScrollOrResize, { passive: true })
    window.addEventListener('resize', onScrollOrResize)

    return () => {
      window.cancelAnimationFrame(initial)
      window.clearTimeout(settle)
      if (frame) window.cancelAnimationFrame(frame)
      window.removeEventListener('scroll', onScrollOrResize)
      window.removeEventListener('resize', onScrollOrResize)
    }
  }, [pathname])

  const openPlanner = () => {
    navigate('/?plan=date')
  }

  const ctaHidden = pathname === '/' && heroCtaInView

  return (
    <nav
      className={`topnav${scrolled ? ' topnav--scrolled' : ''}${ctaHidden ? ' topnav--cta-hidden' : ''}`}
      aria-label="Primary"
    >
      <NavLink to="/" end className="topnav-logo" aria-label="MoodyEat home">
        <span className="topnav-logo-mark" aria-hidden>
          <LogoMark />
        </span>
        <span className="topnav-logo-word">
          Moody<span>Eat</span>
        </span>
      </NavLink>

      <div className="topnav-links">
        <NavLink to="/" end className="topnav-link">
          Home
        </NavLink>
        <NavLink to="/saved" className="topnav-link">
          Saved
        </NavLink>
        <NavLink to="/journal" className="topnav-link">
          Journal
        </NavLink>
        <button
          type="button"
          className="topnav-cta"
          onClick={openPlanner}
          aria-hidden={ctaHidden}
          tabIndex={ctaHidden ? -1 : 0}
        >
          Plan a quest <span aria-hidden>✦</span>
        </button>
      </div>
    </nav>
  )
}

export default TopNav
