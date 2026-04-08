import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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

function placeTypeToneClass(type: string): string {
  const normalized = type
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
  if (normalized.includes('cafe') || normalized.includes('coffee')) {
    return 'place-type-pill--cafe'
  }
  if (normalized.includes('restaurant') || normalized.includes('food')) {
    return 'place-type-pill--restaurant'
  }
  if (normalized.includes('takeaway') || normalized.includes('takeout')) {
    return 'place-type-pill--takeaway'
  }
  if (normalized.includes('bar') || normalized.includes('pub')) {
    return 'place-type-pill--bar'
  }
  if (normalized.includes('bakery') || normalized.includes('dessert')) {
    return 'place-type-pill--bakery'
  }
  return 'place-type-pill--neutral'
}

function placeMediaToneClass(typeLabels: string[]): string {
  return typeLabels.length > 0
    ? placeTypeToneClass(typeLabels[0]).replace('place-type-pill', 'place-media')
    : 'place-media--neutral'
}

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
  const [newlyVisibleFrom, setNewlyVisibleFrom] = useState<number | null>(null)
  const showMoreButtonRef = useRef<HTMLButtonElement | null>(null)

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
    setNewlyVisibleFrom(null)

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

  const showMore = useCallback((total: number) => {
    const previousButtonTop =
      showMoreButtonRef.current?.getBoundingClientRect().top ?? null
    setVisibleCount((current) => {
      const next = Math.min(current + PAGE_SIZE, total)
      setNewlyVisibleFrom(next > current ? current : null)
      return next
    })
    requestAnimationFrame(() => {
      if (previousButtonTop == null) return
      const nextTop = showMoreButtonRef.current?.getBoundingClientRect().top
      if (nextTop == null) return
      window.scrollBy({
        top: nextTop - previousButtonTop,
        behavior: 'auto',
      })
    })
  }, [])

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
                            isNewlyVisible={
                              newlyVisibleFrom != null && i >= newlyVisibleFrom
                            }
                          />
                        ))}
                    </ul>
                    {visibleCount < filteredPlaces.length && (
                      <button
                        ref={showMoreButtonRef}
                        type="button"
                        className="results-show-more"
                        onClick={() => showMore(filteredPlaces.length)}
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
                        <PlaceGenericCard
                          key={cafe.name}
                          index={i}
                          name={cafe.name}
                          distanceLabel={`${cafe.distance_minutes_walk} min walk`}
                          blurb={cafe.vibe}
                          blurbPending={false}
                          typeLabels={['Café']}
                          saved={isSaved(id)}
                          onToggleSave={() => toggle(id)}
                          rating={null}
                          ratingsTotal={null}
                          isNewlyVisible={
                            newlyVisibleFrom != null && i >= newlyVisibleFrom
                          }
                        />
                      )
                    })}
                </ul>
                {visibleCount < showCafeCards.length && (
                  <button
                    ref={showMoreButtonRef}
                    type="button"
                    className="results-show-more"
                    onClick={() => showMore(showCafeCards.length)}
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
  isNewlyVisible,
}: {
  place: PlaceItem
  index: number
  blurb: string
  blurbPending: boolean
  distanceLabel: string
  saved: boolean
  onToggleSave: () => void
  isNewlyVisible: boolean
}) {
  const labels = placeTypeLabels(place.types)
  return (
    <PlaceGenericCard
      index={index}
      name={place.name}
      distanceLabel={distanceLabel}
      blurb={blurb}
      blurbPending={blurbPending}
      typeLabels={labels}
      saved={saved}
      onToggleSave={onToggleSave}
      rating={place.rating ?? null}
      ratingsTotal={place.user_ratings_total ?? null}
      isNewlyVisible={isNewlyVisible}
    />
  )
}

function PlaceGenericCard({
  index,
  name,
  distanceLabel,
  blurb,
  blurbPending,
  typeLabels,
  saved,
  onToggleSave,
  rating,
  ratingsTotal,
  isNewlyVisible,
}: {
  index: number
  name: string
  distanceLabel: string
  blurb: string
  blurbPending: boolean
  typeLabels: string[]
  saved: boolean
  onToggleSave: () => void
  rating: number | null
  ratingsTotal: number | null
  isNewlyVisible: boolean
}) {
  const mediaToneClass = placeMediaToneClass(typeLabels)
  return (
    <li
      className={`cafe-item place-item ${index === 0 ? 'place-item--best' : ''} ${
        isNewlyVisible ? 'place-item--new' : ''
      }`}
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
      <div className="place-card-row">
        <div
          className={`place-media place-media--loading ${mediaToneClass}`}
          aria-hidden
        >
          <span className="place-media-icon">▦</span>
        </div>
        <div className="place-card-content">
          <div className="place-title-row">
            <span className="cafe-name place-name">{name}</span>
          </div>
          <div className="place-meta place-meta--row place-meta--top">
            {rating != null ? (
              <span className="place-rating-line">
                <span className="place-star">★</span>
                {rating.toFixed(1)}
                {ratingsTotal != null && (
                  <span className="place-review-count">
                    ({Math.max(1, Math.round(ratingsTotal / 1000))}k)
                  </span>
                )}
              </span>
            ) : (
              <span className="place-curated-tag">Curated pick</span>
            )}
          </div>
          <div className="place-chip-row">
            <span className="cafe-distance cafe-distance--brand place-distance-pill">
              {distanceLabel}
            </span>
            {typeLabels.length > 0 && (
              <div className="place-type-pills">
                {typeLabels.map((t) => (
                  <span
                    key={t}
                    className={`place-type-pill ${placeTypeToneClass(t)}`}
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
          <p
            className={`cafe-blurb place-blurb ${blurbPending ? 'cafe-blurb--loading' : ''}`}
          >
            {blurbPending ? 'Crafting your take…' : blurb}
          </p>
        </div>
      </div>
    </li>
  )
}
