import { useNavigate } from 'react-router-dom'
import '../App.css'

export function LoginPage() {
  const navigate = useNavigate()

  return (
    <main className="hello-page login-page">
      <section className="hello-card login-card">
        <p className="hello-label">Travel Planner</p>
        <h1 className="hello-title">
          Plan your <span className="hello-name">next outing</span>
        </h1>
        <p className="hello-subtitle">
          Demo login — continue to explore destinations, filters, and place
          suggestions powered by the API.
        </p>
        <button
          type="button"
          className="generate-button login-cta"
          onClick={() => navigate('/explore')}
        >
          Continue
        </button>
      </section>
    </main>
  )
}
