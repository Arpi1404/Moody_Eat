import { Link } from 'react-router-dom'

export function Footer() {
  const year = new Date().getFullYear()
  return (
    <footer className="site-footer" aria-label="Footer">
      <div className="site-footer-inner">
        <span className="site-footer-copy">
          © {year} MoodyEat — made with care in Hyderabad.
        </span>
        <nav className="site-footer-links" aria-label="Footer navigation">
          {/* Plain <a>: /guides/ is prerendered static HTML outside the SPA */}
          <a href="/guides/">City guides</a>
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
          <a
            href="https://www.instagram.com/moody_eat/"
            target="_blank"
            rel="noreferrer noopener"
          >
            Instagram
          </a>
        </nav>
      </div>
    </footer>
  )
}

export default Footer
