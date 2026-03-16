import { FormEvent, useState } from 'react'
import './App.css'

type Cafe = {
  name: string
  address: string
  distance_minutes_walk: number
  vibe: string
}

type QuestResponse = {
  location: string
  mood: string
  cafes: Cafe[]
}

const MOODS = [
  { value: 'cozy', label: 'Cozy' },
  { value: 'productive', label: 'Productive' },
]

function App() {
  const [location, setLocation] = useState('Paris')
  const [mood, setMood] = useState(MOODS[0]?.value ?? 'cozy')
  const [result, setResult] = useState<QuestResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const res = await fetch('http://127.0.0.1:8000/api/generate-quest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          location,
          mood,
        }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        const detail =
          typeof data.detail === 'string'
            ? data.detail
            : data.detail?.message ?? 'Unable to generate quest.'
        throw new Error(detail)
      }

      const data: QuestResponse = await res.json()
      setResult(data)
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Something went wrong.'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="hello-page">
      <section className="hello-card">
        <p className="hello-label">Travel Planner</p>
        <h1 className="hello-title">
          Cafe <span className="hello-name">Quest</span>
        </h1>
        <p className="hello-subtitle">
          Pick a starting point and a mood, and we will suggest three nearby
          cafes from the backend proof of concept.
        </p>

        <form className="quest-form" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="location">Start Location</label>
            <input
              id="location"
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder='e.g. "Paris" or "Bangalore"'
            />
          </div>

          <div className="field">
            <label htmlFor="mood">Mood</label>
            <div className="select-wrapper">
              <select
                id="mood"
                value={mood}
                onChange={(e) => setMood(e.target.value)}
              >
                {MOODS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
              <span className="select-chevron">▾</span>
            </div>
          </div>

          <button className="generate-button" type="submit" disabled={loading}>
            {loading ? 'Generating…' : 'Generate'}
          </button>
        </form>

        <div className="divider" />

        <div className="results">
          {error && <p className="error-text">{error}</p>}

          {!error && !result && !loading && (
            <p className="placeholder">
              Try <span className="pill">Paris · Cozy</span> or{' '}
              <span className="pill">Bangalore · Productive</span> to see a
              sample route.
            </p>
          )}

          {result && (
            <>
              <p className="results-label">
                Showing top 3 cafes for{' '}
                <span className="highlight">
                  {result.location} · {result.mood}
                </span>
              </p>
              <ul className="cafe-list">
                {result.cafes.map((cafe) => (
                  <li key={cafe.name} className="cafe-item">
                    <div className="cafe-header">
                      <span className="cafe-name">{cafe.name}</span>
                      <span className="cafe-distance">
                        {cafe.distance_minutes_walk} min walk
                      </span>
                    </div>
                    <p className="cafe-address">{cafe.address}</p>
                    <p className="cafe-vibe">{cafe.vibe}</p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </section>
    </main>
  )
}

export default App
