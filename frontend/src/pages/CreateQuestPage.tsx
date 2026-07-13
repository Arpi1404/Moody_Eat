import { useCallback, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { searchNearbyPlaces, type PlaceItem } from '../api'
import { track } from '../lib/analytics'
import { formatInrEstimate } from '../lib/budget'
import { buildCustomQuest } from '../lib/questBuild'
import type { DayPart, Occasion } from '../types/quest'
import '../App.css'

const MAX_STOPS = 4

const OCCASION_OPTIONS: { value: Occasion; label: string; emoji: string }[] = [
  { value: 'date', label: 'Date', emoji: '🕯️' },
  { value: 'friends', label: 'Friends', emoji: '🥂' },
  { value: 'solo', label: 'Solo', emoji: '🍵' },
  { value: 'family', label: 'Family', emoji: '🧆' },
]

const DAY_PART_OPTIONS: { value: DayPart; label: string }[] = [
  { value: 'morning', label: 'Morning' },
  { value: 'afternoon', label: 'Afternoon' },
  { value: 'evening', label: 'Evening' },
  { value: 'night', label: 'Night' },
]

const DAY_PART_DEFAULT_BY_OCCASION: Record<Occasion, DayPart> = {
  date: 'evening',
  friends: 'night',
  solo: 'morning',
  family: 'afternoon',
}

const SEARCH_CATEGORIES: { type: string; label: string }[] = [
  { type: 'restaurant', label: 'Restaurants' },
  { type: 'cafe', label: 'Cafés' },
  { type: 'bar', label: 'Bars' },
  { type: 'bakery', label: 'Bakeries' },
  { type: 'night_club', label: 'Clubs' },
  { type: 'park', label: 'Parks' },
  { type: 'tourist_attraction', label: 'Sights' },
  { type: 'museum', label: 'Museums' },
  { type: 'art_gallery', label: 'Galleries' },
  { type: 'shopping_mall', label: 'Malls' },
  { type: 'movie_theater', label: 'Movies' },
  { type: 'bowling_alley', label: 'Bowling' },
]

function distanceLabel(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)}m`
  return `${(meters / 1000).toFixed(1)}km`
}

export function CreateQuestPage() {
  const navigate = useNavigate()
  const [occasion, setOccasion] = useState<Occasion>('friends')
  const [dayPartChoice, setDayPartChoice] = useState<DayPart | null>(null)
  const [location, setLocation] = useState('')
  const [geoLoading, setGeoLoading] = useState(false)
  const [activeType, setActiveType] = useState<string | null>(null)
  const [results, setResults] = useState<PlaceItem[]>([])
  const [resolvedArea, setResolvedArea] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [selected, setSelected] = useState<PlaceItem[]>([])

  const dayPart = dayPartChoice ?? DAY_PART_DEFAULT_BY_OCCASION[occasion]
  const selectedIds = new Set(selected.map((p) => p.provider_id))
  const questFull = selected.length >= MAX_STOPS

  const runSearch = useCallback(
    async (type: string) => {
      if (!location.trim() || searching) return
      setActiveType(type)
      setSearching(true)
      setSearchError(null)
      try {
        const res = await searchNearbyPlaces({
          query: location.trim(),
          categories: [type],
          radius_meters: 3000,
          limit: 12,
        })
        setResults(res.places)
        setResolvedArea(res.resolved_location.name)
        if (res.places.length === 0) {
          setSearchError('No good matches for that category here — try another.')
        }
      } catch (err) {
        setResults([])
        setSearchError(
          err instanceof Error ? err.message : 'Search failed — try again.',
        )
      } finally {
        setSearching(false)
      }
    },
    [location, searching],
  )

  const useMyLocation = () => {
    if (!navigator.geolocation || geoLoading) return
    setGeoLoading(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocation(`${pos.coords.latitude.toFixed(5)},${pos.coords.longitude.toFixed(5)}`)
        setGeoLoading(false)
      },
      () => {
        setSearchError('Could not read your location — type an area instead.')
        setGeoLoading(false)
      },
      { timeout: 8000 },
    )
  }

  const addPlace = (place: PlaceItem) => {
    if (questFull || selectedIds.has(place.provider_id)) return
    setSelected((prev) => [...prev, place])
  }

  const removePlace = (providerId: string) => {
    setSelected((prev) => prev.filter((p) => p.provider_id !== providerId))
  }

  const movePlace = (index: number, delta: number) => {
    setSelected((prev) => {
      const to = index + delta
      if (to < 0 || to >= prev.length) return prev
      const next = [...prev]
      const [moved] = next.splice(index, 1)
      next.splice(to, 0, moved)
      return next
    })
  }

  const handleCreate = () => {
    if (selected.length === 0) return
    const quest = buildCustomQuest({
      places: selected,
      occasion,
      dayPart,
      area: resolvedArea || location.trim(),
    })
    track('custom_quest_created', {
      stop_count: selected.length,
      occasion,
      day_part: dayPart,
    })
    localStorage.setItem(`quest_${quest.id}`, JSON.stringify(quest))
    navigate(`/quest/${quest.id}`, { state: { quest, justCreated: true } })
  }

  return (
    <main className="cq-page">
      <div className="cq-inner">
        <Link to="/" className="qp-back-link">
          <span aria-hidden>←</span> Back to home
        </Link>

        <header className="cq-header">
          <h1>Build your own quest</h1>
          <p>
            Pick 1–{MAX_STOPS} places — we'll map the route, time the stops,
            and make it shareable.
          </p>
        </header>

        <div className="cq-controls">
          <div>
            <span className="sheet-field-label">Occasion</span>
            <div className="sheet-pill-row" role="group" aria-label="Occasion">
              {OCCASION_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  className={`sheet-pill${occasion === o.value ? ' sheet-pill--active' : ''}`}
                  aria-pressed={occasion === o.value}
                  onClick={() => setOccasion(o.value)}
                >
                  <span aria-hidden style={{ marginRight: 6 }}>{o.emoji}</span>
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <span className="sheet-field-label">When?</span>
            <div className="sheet-pill-row" role="group" aria-label="Time of day">
              {DAY_PART_OPTIONS.map((d) => (
                <button
                  key={d.value}
                  type="button"
                  className={`sheet-pill${dayPart === d.value ? ' sheet-pill--active' : ''}`}
                  aria-pressed={dayPart === d.value}
                  onClick={() => setDayPartChoice(d.value)}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <span className="sheet-field-label">Where?</span>
            <div className="cq-location-row">
              <input
                className="cq-location-input"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="City, neighbourhood, or area"
                aria-label="Location"
              />
              <button
                type="button"
                className="cq-geo-btn"
                onClick={useMyLocation}
                disabled={geoLoading}
                title="Use my current location"
              >
                {geoLoading ? '…' : '📍'}
              </button>
            </div>
          </div>

          <div>
            <span className="sheet-field-label">Find places</span>
            <div className="cq-category-row" role="group" aria-label="Place category">
              {SEARCH_CATEGORIES.map((c) => (
                <button
                  key={c.type}
                  type="button"
                  className={`sheet-pill cq-category-pill${activeType === c.type ? ' sheet-pill--active' : ''}`}
                  aria-pressed={activeType === c.type}
                  disabled={!location.trim() || searching}
                  onClick={() => runSearch(c.type)}
                >
                  {c.label}
                </button>
              ))}
            </div>
            {!location.trim() && (
              <p className="cq-hint">Enter a location first, then tap a category.</p>
            )}
          </div>
        </div>

        {selected.length > 0 && (
          <section className="cq-selected" aria-label="Your stops">
            <span className="sheet-field-label">
              Your stops ({selected.length}/{MAX_STOPS})
            </span>
            <ol className="cq-selected-list">
              {selected.map((place, i) => (
                <li key={place.provider_id} className="cq-selected-item">
                  <span className="cq-selected-index" aria-hidden>{i + 1}</span>
                  <span className="cq-selected-name">{place.name}</span>
                  <span className="cq-selected-actions">
                    <button
                      type="button"
                      aria-label={`Move ${place.name} earlier`}
                      disabled={i === 0}
                      onClick={() => movePlace(i, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      aria-label={`Move ${place.name} later`}
                      disabled={i === selected.length - 1}
                      onClick={() => movePlace(i, 1)}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      aria-label={`Remove ${place.name}`}
                      onClick={() => removePlace(place.provider_id)}
                    >
                      ✕
                    </button>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}

        {searching && <p className="cq-hint">Finding good spots…</p>}
        {searchError && !searching && <p className="cq-error">{searchError}</p>}

        {results.length > 0 && !searching && (
          <section className="cq-results" aria-label="Search results">
            <ul>
              {results.map((place) => {
                const added = selectedIds.has(place.provider_id)
                const priceLabel = formatInrEstimate(
                  place.price_range_start_inr,
                  place.price_range_end_inr,
                )
                return (
                  <li key={place.provider_id} className="cq-result-card">
                    <div className="cq-result-info">
                      <p className="cq-result-name">{place.name}</p>
                      <p className="cq-result-meta">
                        {place.rating != null && (
                          <>★ {place.rating.toFixed(1)}
                            {place.user_ratings_total != null && (
                              <span> ({place.user_ratings_total.toLocaleString()})</span>
                            )}
                            {' · '}
                          </>
                        )}
                        {distanceLabel(place.distance_meters)}
                        {priceLabel && <> · {priceLabel}</>}
                      </p>
                    </div>
                    <button
                      type="button"
                      className={`cq-add-btn${added ? ' cq-add-btn--added' : ''}`}
                      disabled={added || questFull}
                      title={
                        questFull && !added
                          ? `Quest is full (${MAX_STOPS} stops max)`
                          : undefined
                      }
                      onClick={() => addPlace(place)}
                    >
                      {added ? '✓ Added' : '+ Add'}
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>
        )}
      </div>

      <div className="cq-create-bar">
        <button
          type="button"
          className="cq-create-btn"
          disabled={selected.length === 0}
          onClick={handleCreate}
        >
          Create quest{selected.length > 0 ? ` (${selected.length} stop${selected.length === 1 ? '' : 's'})` : ''} ✦
        </button>
      </div>
    </main>
  )
}

export default CreateQuestPage
