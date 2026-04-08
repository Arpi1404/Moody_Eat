import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  fetchPlaceBlurbs,
  fetchUserName,
  generateQuest,
  searchNearbyPlaces,
  type Cafe,
  type NearbyPlacesResponse,
  type PlaceItem,
  type QuestResponse,
} from '../api'
import {
  BUDGETS,
  filtersToSearchParams,
  placeTypeLabels,
  searchParamsToFilters,
} from '../exploreParams'
import { useBookmarks } from '../hooks/useBookmarks'
import '../App.css'

function formatDistance(m: number): string {
  if (m >= 1000) {
    return `${(m / 1000).toFixed(1)} km`
  }
  return `${Math.round(m)} m`
}

function BookmarkIcon({ active }: { active: boolean }) {
  return (
    <svg
      className="place-bookmark-svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      aria-hidden
    >
      <path
        d="M7 3.5h10A2.5 2.5 0 0120 6v14.5l-8-4.2L4 20.5V6A2.5 2.5 0 017 3.5z"
        fill={active ? 'rgba(56,189,248,0.25)' : 'none'}
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
    </svg>
  )
}

const PAGE_SIZE = 5

export function ResultsPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const filters = useMemo(
    () => searchParamsToFilters(searchParams),
    [searchParams],
  )

  const [name, setName] = useState<string | null>(null)
  const [nameError, setNameError] = useState<string | null>(null)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nearbyResult, setNearbyResult] = useState<NearbyPlacesResponse | null>(
    null,
  )
  const [questFallback, setQuestFallback] = useState<QuestResponse | null>(null)
  const [fallbackNote, setFallbackNote] = useState<string | null>(null)
  const [blurbs, setBlurbs] = useState<Record<string, string>>({})
  const [blurbsStatus, setBlurbsStatus] = useState<
    'idle' | 'loading' | 'done'
  >('idle')
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)

  const { toggle, isSaved } = useBookmarks()

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

  useEffect(() => {
    if (!filters) {
      navigate('/plan', { replace: true })
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    setNearbyResult(null)
    setQuestFallback(null)
    setFallbackNote(null)
    setBlurbs({})
    setBlurbsStatus('idle')
    setVisibleCount(PAGE_SIZE)

    const radius_meters = Math.min(
      10000,
      Math.max(100, Math.round(filters.radiusKm * 1000)),
    )

    ;(async () => {
      try {
        const nearby = await searchNearbyPlaces({
          query: filters.destination.trim(),
          categories: filters.types,
          radius_meters,
          limit: 20,
        })
        if (!cancelled) setNearbyResult(nearby)
      } catch (err) {
        const message =
          err instanceof Error ? err.message : 'Something went wrong.'
        if (!cancelled) setError(message)

        const locKey = filters.destination.trim().toLowerCase()
        if (locKey === 'paris' || locKey === 'bangalore') {
          try {
            const quest = await generateQuest(
              filters.destination.trim(),
              filters.mood,
            )
            if (!cancelled) {
              setQuestFallback(quest)
              setFallbackNote(
                'Live nearby search was unavailable, so here are curated café picks for this demo location and mood.',
              )
            }
          } catch {
            if (!cancelled) setFallbackNote(null)
          }
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [filters, navigate])

  const filteredPlaces: PlaceItem[] = useMemo(() => {
    if (!filters || !nearbyResult?.places.length) return []
    return nearbyResult.places.filter(
      (p) => (p.rating ?? 0) >= filters.minRating - 0.001,
    )
  }, [nearbyResult, filters])

  useEffect(() => {
    if (!filters || questFallback) {
      setBlurbsStatus('done')
      return
    }
    if (!filteredPlaces.length) {
      if (!loading) setBlurbsStatus('done')
      return
    }
    let cancelled = false
    setBlurbsStatus('loading')
    ;(async () => {
      try {
        const b = await fetchPlaceBlurbs({
          mood: filters.mood,
          budget: filters.budget,
          people: filters.people,
          places: filteredPlaces.map((p) => ({
            provider_id: p.provider_id,
            name: p.name,
            types: p.types ?? [],
          })),
        })
        if (!cancelled) {
          setBlurbs(b)
          setBlurbsStatus('done')
        }
      } catch {
        if (!cancelled) {
          setBlurbs({})
          setBlurbsStatus('done')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [filters, questFallback, filteredPlaces, loading])

  const showCafeCards = questFallback?.cafes ?? []

  const planHref = filters
    ? `/plan?${filtersToSearchParams(filters).toString()}`
    : '/plan'

  const fallbackBlurb = useCallback(
    (place: PlaceItem) =>
      !filters
        ? ''
        : `Fits your ${filters.mood} outing — ${place.name.split(/\s+/)[0] ?? 'This spot'} is a solid local pick.`,
    [filters],
  )

  if (!filters) {
    return null
  }

  return (
    <main className="hello-page explore-page">
      <section className="hello-card explore-card explore-card--results">
        <div className="explore-results-only">
          <div className="explore-results-toolbar">
            <Link className="explore-edit-filters" to={planHref}>
              ← Edit filters
            </Link>
            <Link to="/" className="explore-home-link">
              ← Home
            </Link>
          </div>

          <p className="hello-label">Today</p>
          <h1 className="hello-title explore-greeting explore-greeting--compact">
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

          <div className="results explore-results">
            <div
              className="trip-context-pill"
              role="status"
              aria-label="Trip context"
            >
              <span className="trip-context-pill-label">Trip context</span>
              <span className="trip-context-pill-values">
                <span className="highlight">
                  {filters.people}{' '}
                  {filters.people === 1 ? 'person' : 'people'}
                </span>
                <span className="trip-context-sep" aria-hidden>
                  ·
                </span>
                <span className="highlight">
                  {BUDGETS.find((b) => b.value === filters.budget)?.label}
                </span>
                <span className="trip-context-sep" aria-hidden>
                  ·
                </span>
                <span className="highlight">{filters.mood}</span>
              </span>
            </div>

            {loading && (
              <ul className="cafe-list place-skeleton-list" aria-busy>
                {Array.from({ length: 5 }, (_, i) => (
                  <li key={i} className="place-skeleton-card" />
                ))}
              </ul>
            )}

            {!loading && error && <p className="error-text">{error}</p>}
            {!loading && fallbackNote && (
              <p className="fallback-note">{fallbackNote}</p>
            )}

            {!loading && nearbyResult && !questFallback && (
              <>
                <p className="results-label">
                  Near{' '}
                  <span className="highlight">
                    {nearbyResult.resolved_location.name}
                  </span>{' '}
                  — {filteredPlaces.length} place
                  {filteredPlaces.length === 1 ? '' : 's'} (min{' '}
                  {filters.minRating}★)
                </p>
                {filteredPlaces.length === 0 ? (
                  <p className="placeholder">
                    No places matched your minimum rating. Try lowering the
                    rating or widening the radius.
                  </p>
                ) : (
                  <>
                    <ul className="cafe-list">
                      {filteredPlaces
                        .slice(0, visibleCount)
                        .map((p, i) => (
                          <PlaceNearbyCard
                            key={p.provider_id}
                            place={p}
                            index={i}
                            blurb={
                              blurbs[p.provider_id] ?? fallbackBlurb(p)
                            }
                            blurbPending={blurbsStatus === 'loading'}
                            distanceLabel={formatDistance(p.distance_meters)}
                            saved={isSaved(p.provider_id)}
                            onToggleSave={() => toggle(p.provider_id)}
                          />
                        ))}
                    </ul>
                    {visibleCount < filteredPlaces.length && (
                      <button
                        type="button"
                        className="results-show-more"
                        onClick={() =>
                          setVisibleCount((c) =>
                            Math.min(c + PAGE_SIZE, filteredPlaces.length),
                          )
                        }
                      >
                        Show more
                      </button>
                    )}
                  </>
                )}
              </>
            )}

            {!loading && questFallback && showCafeCards.length > 0 && (
              <>
                <p className="results-label">
                  Curated cafés for{' '}
                  <span className="highlight">
                    {questFallback.location} · {questFallback.mood}
                  </span>
                </p>
                <ul className="cafe-list">
                  {showCafeCards
                    .slice(0, visibleCount)
                    .map((cafe: Cafe, i) => {
                      const id = `quest:${cafe.name}`
                      return (
                        <li
                          key={cafe.name}
                          className={`cafe-item place-item ${i === 0 ? 'place-item--best' : ''}`}
                        >
                          {i === 0 && (
                            <span className="place-badge-best">Best match</span>
                          )}
                          <button
                            type="button"
                            className="place-bookmark"
                            aria-label={
                              isSaved(id) ? 'Remove saved place' : 'Save place'
                            }
                            aria-pressed={isSaved(id)}
                            onClick={() => toggle(id)}
                          >
                            <BookmarkIcon active={isSaved(id)} />
                          </button>
                          <div className="cafe-header">
                            <span className="cafe-name">{cafe.name}</span>
                            <span className="cafe-distance cafe-distance--brand">
                              {cafe.distance_minutes_walk} min walk
                            </span>
                          </div>
                          <p className="cafe-blurb">{cafe.vibe}</p>
                          <div className="place-type-pills">
                            <span className="place-type-pill">Café</span>
                          </div>
                        </li>
                      )
                    })}
                </ul>
                {visibleCount < showCafeCards.length && (
                  <button
                    type="button"
                    className="results-show-more"
                    onClick={() =>
                      setVisibleCount((c) =>
                        Math.min(c + PAGE_SIZE, showCafeCards.length),
                      )
                    }
                  >
                    Show more
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </section>
    </main>
  )
}

function PlaceNearbyCard({
  place,
  index,
  blurb,
  blurbPending,
  distanceLabel,
  saved,
  onToggleSave,
}: {
  place: PlaceItem
  index: number
  blurb: string
  blurbPending: boolean
  distanceLabel: string
  saved: boolean
  onToggleSave: () => void
}) {
  const labels = placeTypeLabels(place.types)
  return (
    <li
      className={`cafe-item place-item ${index === 0 ? 'place-item--best' : ''}`}
    >
      {index === 0 && <span className="place-badge-best">Best match</span>}
      <button
        type="button"
        className="place-bookmark"
        aria-label={saved ? 'Remove saved place' : 'Save place'}
        aria-pressed={saved}
        onClick={onToggleSave}
      >
        <BookmarkIcon active={saved} />
      </button>
      <div className="cafe-header">
        <span className="cafe-name">{place.name}</span>
        <span className="cafe-distance cafe-distance--brand">
          {distanceLabel}
        </span>
      </div>
      <p
        className={`cafe-blurb ${blurbPending ? 'cafe-blurb--loading' : ''}`}
      >
        {blurbPending ? 'Crafting your take…' : blurb}
      </p>
      <div className="place-meta place-meta--row">
        {place.rating != null && (
          <span>
            {place.rating.toFixed(1)}★
            {place.user_ratings_total != null &&
              ` (${place.user_ratings_total} reviews)`}
          </span>
        )}
      </div>
      {labels.length > 0 && (
        <div className="place-type-pills">
          {labels.map((t) => (
            <span key={t} className="place-type-pill">
              {t}
            </span>
          ))}
        </div>
      )}
    </li>
  )
}
