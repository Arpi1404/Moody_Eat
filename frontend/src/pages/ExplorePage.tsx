import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  fetchUserName,
  generateQuest,
  searchNearbyPlaces,
  type Cafe,
  type NearbyPlacesResponse,
  type PlaceItem,
  type QuestResponse,
} from '../api'
import '../App.css'

const MOODS = [
  { value: 'cozy', label: 'Cozy' },
  { value: 'productive', label: 'Productive' },
] as const

const PLACE_TYPES: { value: string; label: string }[] = [
  { value: 'cafe', label: 'Café' },
  { value: 'restaurant', label: 'Restaurant' },
  { value: 'bar', label: 'Bar' },
  { value: 'bakery', label: 'Bakery' },
  { value: 'meal_takeaway', label: 'Takeaway' },
  { value: 'meal_delivery', label: 'Delivery' },
]

const BUDGETS = [
  { value: 'low', label: 'Budget-friendly' },
  { value: 'mid', label: 'Mid-range' },
  { value: 'high', label: 'Splurge' },
] as const

function formatDistance(m: number): string {
  if (m >= 1000) {
    return `${(m / 1000).toFixed(1)} km`
  }
  return `${Math.round(m)} m`
}

export function ExplorePage() {
  const [name, setName] = useState<string | null>(null)
  const [nameError, setNameError] = useState<string | null>(null)

  const [destination, setDestination] = useState('Paris')
  const [mood, setMood] = useState<(typeof MOODS)[number]['value']>('cozy')
  const [people, setPeople] = useState(2)
  const [selectedTypes, setSelectedTypes] = useState<string[]>([
    'cafe',
    'restaurant',
  ])
  const [minRating, setMinRating] = useState(3.5)
  const [budget, setBudget] = useState<(typeof BUDGETS)[number]['value']>('mid')
  const [radiusKm, setRadiusKm] = useState(3)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [nearbyResult, setNearbyResult] = useState<NearbyPlacesResponse | null>(
    null,
  )
  const [questFallback, setQuestFallback] = useState<QuestResponse | null>(null)
  const [fallbackNote, setFallbackNote] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchUserName()
      .then((n) => {
        if (!cancelled) setName(n)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setNameError(
            err instanceof Error ? err.message : 'Could not load name.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const filteredPlaces: PlaceItem[] = useMemo(() => {
    if (!nearbyResult?.places.length) return []
    return nearbyResult.places.filter(
      (p) => (p.rating ?? 0) >= minRating - 0.001,
    )
  }, [nearbyResult, minRating])

  const toggleType = (value: string) => {
    setSelectedTypes((prev) => {
      if (prev.includes(value)) {
        if (prev.length === 1) return prev
        return prev.filter((t) => t !== value)
      }
      return [...prev, value]
    })
  }

  const clampPeople = (n: number) =>
    Math.min(50, Math.max(1, Math.round(Number.isFinite(n) ? n : 1)))

  const [peopleEdit, setPeopleEdit] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setNearbyResult(null)
    setQuestFallback(null)
    setFallbackNote(null)

    const radius_meters = Math.min(
      10000,
      Math.max(100, Math.round(radiusKm * 1000)),
    )

    try {
      const nearby = await searchNearbyPlaces({
        query: destination.trim(),
        categories: selectedTypes,
        radius_meters,
        limit: 20,
      })
      setNearbyResult(nearby)
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Something went wrong.'
      setError(message)

      const locKey = destination.trim().toLowerCase()
      if (locKey === 'paris' || locKey === 'bangalore') {
        try {
          const quest = await generateQuest(destination.trim(), mood)
          setQuestFallback(quest)
          setFallbackNote(
            'Live nearby search was unavailable, so here are curated café picks for this demo location and mood.',
          )
        } catch {
          setFallbackNote(null)
        }
      }
    } finally {
      setLoading(false)
    }
  }

  const showCafeCards = questFallback?.cafes ?? []
  const greeting = nameError
    ? 'there'
    : name
      ? name
      : '…'

  return (
    <main className="hello-page explore-page">
      <section className="hello-card explore-card">
        <p className="explore-back">
          <Link to="/">← Back</Link>
        </p>
        <p className="hello-label">Today</p>
        <h1 className="hello-title explore-greeting">
          Hello,{' '}
          <span className="hello-name">
            {nameError ? 'there' : name ?? '…'}
          </span>
        </h1>
        {nameError && (
          <p className="explore-name-error" role="alert">
            {nameError}
          </p>
        )}
        <p className="hello-subtitle explore-lead">
          Where do you want to go today? Set your spot, mood, and filters — then
          get place suggestions.
        </p>

        <form className="explore-form" onSubmit={handleSubmit}>
          <div className="field field-full">
            <label htmlFor="destination">Destination / area</label>
            <div className="input-pin-wrap">
              <span className="input-pin-icon" aria-hidden>
                📍
              </span>
              <input
                id="destination"
                className="destination-input"
                type="text"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                placeholder="e.g. Paris, Indiranagar Bangalore"
                required
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="mood">Mood</label>
            <div className="select-wrapper">
              <select
                id="mood"
                value={mood}
                onChange={(e) =>
                  setMood(e.target.value as (typeof MOODS)[number]['value'])
                }
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

          <div className="field">
            <label htmlFor="people-count" className="field-section-label">
              People
            </label>
            <div className="people-stepper">
              <button
                type="button"
                className="people-stepper-btn"
                aria-label="Decrease party size"
                disabled={people <= 1}
                onClick={() => {
                  setPeopleEdit(null)
                  setPeople((p) => Math.max(1, p - 1))
                }}
              >
                −
              </button>
              <input
                id="people-count"
                className="people-stepper-input"
                type="text"
                name="people"
                inputMode="numeric"
                autoComplete="off"
                value={peopleEdit ?? String(people)}
                onFocus={() => setPeopleEdit(String(people))}
                onChange={(e) => {
                  const v = e.target.value.replace(/\D/g, '')
                  setPeopleEdit(v)
                  if (v !== '') setPeople(clampPeople(Number.parseInt(v, 10)))
                }}
                onBlur={(e) => {
                  const v = e.target.value.replace(/\D/g, '')
                  setPeopleEdit(null)
                  setPeople(v === '' ? 1 : clampPeople(Number.parseInt(v, 10)))
                }}
              />
              <button
                type="button"
                className="people-stepper-btn"
                aria-label="Increase party size"
                disabled={people >= 50}
                onClick={() => {
                  setPeopleEdit(null)
                  setPeople((p) => Math.min(50, p + 1))
                }}
              >
                +
              </button>
            </div>
          </div>

          <div className="field field-full">
            <span className="field-label-static">Type of place</span>
            <div className="chip-row" role="group" aria-label="Place types">
              {PLACE_TYPES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  className={`chip ${selectedTypes.includes(t.value) ? 'chip-on' : ''}`}
                  onClick={() => toggleType(t.value)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="field">
            <label htmlFor="rating">Min. rating</label>
            <input
              id="rating"
              type="range"
              min={1}
              max={5}
              step={0.5}
              value={minRating}
              onChange={(e) => setMinRating(Number(e.target.value))}
            />
            <span className="range-value">{minRating.toFixed(1)} ★</span>
          </div>

          <div className="field">
            <label htmlFor="budget">Budget</label>
            <div className="select-wrapper">
              <select
                id="budget"
                value={budget}
                onChange={(e) =>
                  setBudget(
                    e.target.value as (typeof BUDGETS)[number]['value'],
                  )
                }
              >
                {BUDGETS.map((b) => (
                  <option key={b.value} value={b.value}>
                    {b.label}
                  </option>
                ))}
              </select>
              <span className="select-chevron">▾</span>
            </div>
          </div>

          <div className="field field-full">
            <label htmlFor="radius">Search radius (km)</label>
            <input
              id="radius"
              type="range"
              min={0.5}
              max={10}
              step={0.5}
              value={radiusKm}
              onChange={(e) => setRadiusKm(Number(e.target.value))}
            />
            <span className="range-value">{radiusKm} km</span>
          </div>

          <button className="generate-button" type="submit" disabled={loading}>
            {loading ? 'Searching…' : 'Suggest places'}
          </button>
        </form>

        <div className="divider" />

        <div className="results explore-results">
          <div className="trip-context-pill" role="status" aria-label="Trip context">
            <span className="trip-context-pill-label">Trip context</span>
            <span className="trip-context-pill-values">
              <span className="highlight">
                {people} {people === 1 ? 'person' : 'people'}
              </span>
              <span className="trip-context-sep" aria-hidden>
                ·
              </span>
              <span className="highlight">
                {BUDGETS.find((b) => b.value === budget)?.label}
              </span>
              <span className="trip-context-sep" aria-hidden>
                ·
              </span>
              <span className="highlight">{mood}</span>
            </span>
          </div>

          {error && <p className="error-text">{error}</p>}
          {fallbackNote && (
            <p className="fallback-note">{fallbackNote}</p>
          )}

          {nearbyResult && !questFallback && (
            <>
              <p className="results-label">
                Near{' '}
                <span className="highlight">
                  {nearbyResult.resolved_location.name}
                </span>{' '}
                — {filteredPlaces.length} place
                {filteredPlaces.length === 1 ? '' : 's'} (min {minRating}★)
              </p>
              {filteredPlaces.length === 0 ? (
                <p className="placeholder">
                  No places matched your minimum rating. Try lowering the rating
                  or widening the radius.
                </p>
              ) : (
                <ul className="cafe-list">
                  {filteredPlaces.map((p) => (
                    <li key={p.provider_id} className="cafe-item place-item">
                      <div className="cafe-header">
                        <span className="cafe-name">{p.name}</span>
                        <span className="cafe-distance">
                          {formatDistance(p.distance_meters)}
                        </span>
                      </div>
                      <p className="cafe-address">{p.address}</p>
                      <div className="place-meta">
                        {p.rating != null && (
                          <span>
                            {p.rating.toFixed(1)}★
                            {p.user_ratings_total != null &&
                              ` (${p.user_ratings_total} reviews)`}
                          </span>
                        )}
                        {p.types?.length ? (
                          <span className="place-types">
                            {p.types.slice(0, 4).join(' · ')}
                          </span>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}

          {questFallback && showCafeCards.length > 0 && (
            <>
              <p className="results-label">
                Curated cafés for{' '}
                <span className="highlight">
                  {questFallback.location} · {questFallback.mood}
                </span>
              </p>
              <ul className="cafe-list">
                {showCafeCards.map((cafe: Cafe) => (
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

          {!error &&
            !nearbyResult &&
            !questFallback &&
            !loading &&
            greeting !== '…' && (
              <p className="placeholder">
                Hi <span className="pill">{greeting}</span> — set filters above
                and tap <span className="pill">Suggest places</span>.
              </p>
            )}
        </div>
      </section>
    </main>
  )
}
