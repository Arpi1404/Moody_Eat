import { type FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  BUDGETS,
  filtersToSearchParams,
  mergeFiltersFromSearchParams,
  MOODS,
  PLACE_TYPES,
  type ExploreFilters,
} from '../exploreParams'
import '../App.css'

export function PlanPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [filters, setFilters] = useState<ExploreFilters>(() =>
    mergeFiltersFromSearchParams(searchParams),
  )

  useEffect(() => {
    setFilters(mergeFiltersFromSearchParams(searchParams))
  }, [searchParams])

  const [peopleEdit, setPeopleEdit] = useState<string | null>(null)

  const clampPeople = (n: number) =>
    Math.min(50, Math.max(1, Math.round(Number.isFinite(n) ? n : 1)))

  const toggleType = (value: string) => {
    setFilters((prev) => {
      const selected = prev.types
      if (selected.includes(value)) {
        if (selected.length === 1) return prev
        return { ...prev, types: selected.filter((t) => t !== value) }
      }
      return { ...prev, types: [...selected, value] }
    })
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    navigate(`/results?${filtersToSearchParams(filters).toString()}`)
  }

  return (
    <main className="hello-page explore-page">
      <section className="hello-card explore-card explore-card--plan">
        <p className="explore-back">
          <Link to="/">← Back</Link>
        </p>
        <p className="hello-label">Today</p>
        {/* TODO: replace with quest-related content */}
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
                value={filters.destination}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, destination: e.target.value }))
                }
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
                value={filters.mood}
                onChange={(e) =>
                  setFilters((f) => ({
                    ...f,
                    mood: e.target.value as ExploreFilters['mood'],
                  }))
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
                disabled={filters.people <= 1}
                onClick={() => {
                  setPeopleEdit(null)
                  setFilters((f) => ({
                    ...f,
                    people: Math.max(1, f.people - 1),
                  }))
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
                value={peopleEdit ?? String(filters.people)}
                onFocus={() => setPeopleEdit(String(filters.people))}
                onChange={(e) => {
                  const v = e.target.value.replace(/\D/g, '')
                  setPeopleEdit(v)
                  if (v !== '')
                    setFilters((f) => ({
                      ...f,
                      people: clampPeople(Number.parseInt(v, 10)),
                    }))
                }}
                onBlur={(e) => {
                  const v = e.target.value.replace(/\D/g, '')
                  setPeopleEdit(null)
                  setFilters((f) => ({
                    ...f,
                    people:
                      v === '' ? 1 : clampPeople(Number.parseInt(v, 10)),
                  }))
                }}
              />
              <button
                type="button"
                className="people-stepper-btn"
                aria-label="Increase party size"
                disabled={filters.people >= 50}
                onClick={() => {
                  setPeopleEdit(null)
                  setFilters((f) => ({
                    ...f,
                    people: Math.min(50, f.people + 1),
                  }))
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
                  className={`chip ${filters.types.includes(t.value) ? 'chip-on' : ''}`}
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
              value={filters.minRating}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  minRating: Number(e.target.value),
                }))
              }
            />
            <span className="range-value">{filters.minRating.toFixed(1)} ★</span>
          </div>

          <div className="field">
            <label htmlFor="budget">Budget</label>
            <div className="select-wrapper">
              <select
                id="budget"
                value={filters.budget}
                onChange={(e) =>
                  setFilters((f) => ({
                    ...f,
                    budget: e.target.value as ExploreFilters['budget'],
                  }))
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
              value={filters.radiusKm}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  radiusKm: Number(e.target.value),
                }))
              }
            />
            <span className="range-value">{filters.radiusKm} km</span>
          </div>

          <button className="generate-button" type="submit">
            Suggest places
          </button>
        </form>

      </section>
    </main>
  )
}
