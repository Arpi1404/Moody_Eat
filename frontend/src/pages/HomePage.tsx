import { type FormEvent, type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { fetchCuratedQuests, generateQuest, getApiBase } from '../api'
import type { Quest } from '../types/quest'
import { LocationInput } from '../components/LocationInput'
import { EmptyState, ErrorState, LoadingState } from '../components/states'
import { TourSheet, WelcomeNudge } from '../components/WelcomeTour'
import { track } from '../lib/analytics'
import { budgetLabel } from '../lib/budget'
import { hasQuestHistory, markTourSeen, tourSeen } from '../lib/onboarding'
import { getRecentPlaceIds, recordQuestPlaces } from '../lib/questHistory'
import '../App.css'

// ── Static data ───────────────────────────────────────────────────────────────

const OCCASIONS = [
  {
    key: 'date',
    emoji: '🕯️',
    title: 'Date Night',
    desc: 'For nights worth remembering',
  },
  {
    key: 'friends',
    emoji: '🥂',
    title: 'Friends Hangout',
    desc: "The gang's all here",
  },
  {
    key: 'solo',
    emoji: '🍵',
    title: 'Solo Time',
    desc: 'Just you, on purpose',
  },
  {
    key: 'family',
    emoji: '🧆',
    title: 'Family Outing',
    desc: 'All of you, fed and happy',
  },
] as const

type OccasionKey = (typeof OCCASIONS)[number]['key']

const OCCASION_ICONS: Record<OccasionKey, string> = {
  date: '🕯️',
  friends: '🥂',
  solo: '🍵',
  family: '🧆',
}

const OCCASION_LABELS: Record<OccasionKey, string> = {
  date: 'Date Night',
  friends: 'Friends',
  solo: 'Solo Time',
  family: 'Family',
}

const OCCASION_TINTS: Record<OccasionKey, string> = {
  date: 'rgba(199, 82, 42, 0.10)',
  friends: 'rgba(232, 176, 75, 0.16)',
  solo: 'rgba(92, 113, 72, 0.14)',
  family: 'rgba(199, 82, 42, 0.09)',
}

const BUDGET_OPTIONS = [
  { value: 'cheap', label: 'Cheap' },
  { value: 'mid', label: 'Mid' },
  { value: 'splurge', label: 'Splurge' },
] as const

type Budget = (typeof BUDGET_OPTIONS)[number]['value']

// Stops are the honest size question ("how big an evening?"); duration is an
// output of the plan, not an input. 1 = "just pick me one good place".
const MIN_STOPS = 1
const MAX_STOPS = 4

const DAY_PART_OPTIONS = [
  { value: 'morning', label: 'Morning', hint: '~10am' },
  { value: 'afternoon', label: 'Afternoon', hint: '~1pm' },
  { value: 'evening', label: 'Evening', hint: '~5:30pm' },
  { value: 'night', label: 'Night', hint: '~8pm' },
] as const

type DayPart = (typeof DAY_PART_OPTIONS)[number]['value']

// Mirrors the backend's per-occasion default start times, so the preselected
// pill matches what the engine would do anyway.
const DAY_PART_DEFAULT_BY_OCCASION: Record<OccasionKey, DayPart> = {
  date: 'evening',
  friends: 'night',
  solo: 'morning',
  family: 'afternoon',
}

// Solo trips always count as 1 person; family trips as 4
const PEOPLE_BY_OCCASION: Record<OccasionKey, number> = {
  date: 2,
  friends: 4,
  solo: 1,
  family: 4,
}

// ── Geolocation helpers ───────────────────────────────────────────────────────

type ReverseGeocode = {
  /** City-level name — what curated quests are keyed on. */
  city: string | null
  /** Neighbourhood-level name for the location field, e.g. "Gachibowli, Hyderabad". */
  label: string | null
}

// Shown in the location field when the area name couldn't be looked up; the
// coordinates still anchor the search.
const GEO_FALLBACK_LABEL = 'Current location'

async function reverseGeocode(lat: number, lng: number): Promise<ReverseGeocode> {
  // Uses OpenStreetMap Nominatim — no API key required for light/personal use.
  const res = await fetch(
    `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`,
    { headers: { 'Accept-Language': 'en' } },
  )
  if (!res.ok) throw new Error('Geocode failed')
  const data = await res.json()
  const a = data.address ?? {}
  const city: string | null =
    a.city ?? a.town ?? a.suburb ?? a.village ?? a.county ?? null
  const area: string | null =
    a.suburb ?? a.neighbourhood ?? a.town ?? a.village ?? null
  const label = area && city && area !== city ? `${area}, ${city}` : (area ?? city)
  return { city, label }
}

function getCurrentPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Geolocation not supported'))
      return
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 8_000 })
  })
}

async function detectCity(): Promise<string> {
  const pos = await getCurrentPosition()
  const { city } = await reverseGeocode(pos.coords.latitude, pos.coords.longitude)
  const name = city?.trim()
  if (!name) {
    throw new Error('City not detected')
  }
  return name
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

function formatQuestDuration(minutes: number): string {
  const hours = minutes / 60
  return Number.isInteger(hours) ? `${hours}h` : `${hours.toFixed(1)}h`
}

function costLabel(cost: Quest['total_cost_estimate']): string {
  return budgetLabel(cost)
}

function CuratedQuestImage({ quest }: { quest: Quest }) {
  const [failed, setFailed] = useState(false)
  const firstStop = quest.stops[0]
  const placeId = firstStop?.place.provider_id
  const src = placeId
    ? `${getApiBase()}/api/places/photo?place_id=${encodeURIComponent(placeId)}&max_width=800`
    : ''

  const badge = (
    <span className="curated-quest-occasion-badge">
      <span className="curated-quest-occasion-badge-emoji" aria-hidden>
        {OCCASION_ICONS[quest.occasion]}
      </span>
      {OCCASION_LABELS[quest.occasion]}
    </span>
  )

  if (!src || failed) {
    return (
      <div className="curated-quest-image curated-quest-image--fallback">
        <span aria-hidden>{OCCASION_ICONS[quest.occasion]}</span>
        {badge}
      </div>
    )
  }

  return (
    <div className="curated-quest-image">
      <img
        src={src}
        alt={firstStop.place.name}
        onError={() => setFailed(true)}
      />
      {badge}
    </div>
  )
}

function StopTrail({ count }: { count: number }) {
  const items: ReactNode[] = []
  for (let i = 0; i < count; i++) {
    if (i > 0) items.push(<span key={`l${i}`} className="stop-trail-line" />)
    items.push(
      <span
        key={`d${i}`}
        className={`stop-trail-dot${i === 0 ? '' : ' stop-trail-dot--empty'}`}
      />,
    )
  }
  return (
    <div className="stop-trail" aria-hidden>
      {items}
      <span className="stop-trail-label">{count} {count === 1 ? 'stop' : 'stops'}</span>
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

const PLAN_PARAM_KEYS = new Set<OccasionKey>(['date', 'friends', 'solo', 'family'])

export function HomePage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [activeOccasion, setActiveOccasion] = useState<OccasionKey | null>(null)
  const [location, setLocation] = useState('')
  // Set while the location field holds a place with known coordinates — the
  // device's position (📍 button) or a picked suggestion. The quest is
  // searched around these coordinates and the field's text is only a
  // readable label. Typing in the field clears it.
  const [geoCoords, setGeoCoords] = useState<{
    lat: number
    lng: number
    source: 'device' | 'picked'
  } | null>(null)
  const [geoLoading, setGeoLoading] = useState(false)
  const [geoError, setGeoError] = useState<string | null>(null)
  const [budget, setBudget] = useState<Budget>('mid')
  const [stopCount, setStopCount] = useState(3)
  // null = follow the occasion's default start time
  const [dayPartChoice, setDayPartChoice] = useState<DayPart | null>(null)
  // First-visit tour: 'nudge' is the small "New here?" card, 'open' the tour.
  const [tour, setTour] = useState<'hidden' | 'nudge' | 'open'>('hidden')
  const [submitting, setSubmitting] = useState(false)
  const [submitSlow, setSubmitSlow] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [curatedQuests, setCuratedQuests] = useState<Quest[]>([])
  const [curatedCity, setCuratedCity] = useState('Hyderabad')
  const [curatedLoading, setCuratedLoading] = useState(true)
  const [curatedError, setCuratedError] = useState<string | null>(null)

  const sheetRef = useRef<HTMLDivElement>(null)
  const locationInputRef = useRef<HTMLInputElement>(null)
  const submitSlowTimer = useRef<number | null>(null)
  const curatedScrollRef = useRef<HTMLDivElement>(null)

  const scrollCurated = useCallback((direction: 'prev' | 'next') => {
    const el = curatedScrollRef.current
    if (!el) return
    const card = el.querySelector<HTMLElement>('.curated-quest-card')
    const step = (card?.offsetWidth ?? 296) + 16 // card + gap
    el.scrollBy({
      left: direction === 'next' ? step : -step,
      behavior: 'smooth',
    })
  }, [])

  const tryGeolocation = useCallback(() => {
    if (!navigator.geolocation) {
      setGeoError('Geolocation not supported')
      return
    }
    setGeoLoading(true)
    setGeoError(null)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude: lat, longitude: lng } = pos.coords
        let label: string | null = null
        try {
          label = (await reverseGeocode(lat, lng)).label
        } catch {
          // The area name is cosmetic — the coordinates still anchor the search.
        }
        setLocation(label ?? GEO_FALLBACK_LABEL)
        setGeoCoords({ lat, lng, source: 'device' })
        setGeoLoading(false)
      },
      () => {
        setGeoLoading(false)
        setGeoError('Location access denied — type a city instead')
      },
      { timeout: 8_000 },
    )
  }, [])

  const loadCuratedQuests = useCallback(async () => {
    setCuratedLoading(true)
    setCuratedError(null)
    let city = 'Hyderabad'

    try {
      city = await detectCity()
    } catch {
      city = 'Hyderabad'
    }
    setCuratedCity(city)

    try {
      const [quests] = await Promise.all([fetchCuratedQuests(city), wait(200)])
      setCuratedQuests(quests)
    } catch (err) {
      setCuratedQuests([])
      setCuratedError(
        err instanceof Error ? err.message : 'Could not load curated quests.',
      )
    } finally {
      setCuratedLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadCuratedQuests()
  }, [loadCuratedQuests])

  useEffect(() => {
    return () => {
      if (submitSlowTimer.current) window.clearTimeout(submitSlowTimer.current)
    }
  }, [])

  // Auto-open the occasion sheet when arriving with ?plan=<occasion>
  useEffect(() => {
    const plan = searchParams.get('plan') as OccasionKey | null
    if (plan && PLAN_PARAM_KEYS.has(plan)) {
      setActiveOccasion(plan)
      setSubmitError(null)
      const next = new URLSearchParams(searchParams)
      next.delete('plan')
      setSearchParams(next, { replace: true })
    }
  }, [searchParams, setSearchParams])

  // First visit: offer the tour a moment after the page has settled. It is
  // only ever an offer — the page stays fully usable around it.
  useEffect(() => {
    if (tourSeen() || hasQuestHistory()) return
    const timer = window.setTimeout(() => {
      setTour((state) => (state === 'hidden' ? 'nudge' : state))
    }, 1500)
    return () => window.clearTimeout(timer)
  }, [])

  // "How it works" in the footer links to /?tour=1.
  useEffect(() => {
    if (!searchParams.has('tour')) return
    track('tour_opened', { source: 'link' })
    setTour('open')
    const next = new URLSearchParams(searchParams)
    next.delete('tour')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  const closeTour = useCallback(
    (result: { step: number; completed: boolean }) => {
      markTourSeen()
      track('tour_closed', { step: result.step + 1, completed: result.completed })
      setTour('hidden')
    },
    [],
  )

  // Fade sections in as they enter the viewport
  useEffect(() => {
    if (typeof window === 'undefined' || typeof IntersectionObserver === 'undefined') {
      return
    }
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const els = Array.from(document.querySelectorAll<HTMLElement>('[data-fade]'))
    if (reduced) {
      els.forEach((el) => el.classList.add('fade-up--visible'))
      return
    }
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('fade-up--visible')
            obs.unobserve(e.target)
          }
        })
      },
      { threshold: 0.12 },
    )
    els.forEach((el) => obs.observe(el))
    return () => obs.disconnect()
  }, [curatedLoading, curatedError, curatedQuests.length])

  const openSheet = useCallback(
    (key: OccasionKey) => {
      track('home_tile_tapped', { occasion: key })
      setActiveOccasion(key)
      setSubmitError(null)
      if (!location) tryGeolocation()
      // Focus the location input after the sheet animates in
      setTimeout(() => locationInputRef.current?.focus(), 320)
    },
    [location, tryGeolocation],
  )

  const closeSheet = useCallback(() => {
    setActiveOccasion(null)
    setSubmitting(false)
    setSubmitError(null)
  }, [])

  // Close on Escape; lock body scroll while sheet is open
  useEffect(() => {
    if (!activeOccasion) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeSheet()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [activeOccasion, closeSheet])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!activeOccasion || !location.trim() || submitting) return
    setSubmitting(true)
    setSubmitSlow(false)
    setSubmitError(null)
    submitSlowTimer.current = window.setTimeout(() => {
      setSubmitSlow(true)
    }, 3000)

    const dayPart = dayPartChoice ?? DAY_PART_DEFAULT_BY_OCCASION[activeOccasion]
    const typedLocation = location.trim()
    const request = {
      // A 📍 or picked location is searched around its coordinates, not
      // around the centre of whatever the area is called — "Hyderabad"
      // resolves to a point 14 km from Gachibowli. Rounded to ~100 m: ample
      // for a 3 km search without sending an exact device position.
      location: geoCoords
        ? `${geoCoords.lat.toFixed(3)},${geoCoords.lng.toFixed(3)}`
        : typedLocation,
      // Names the quest ("… in Gachibowli") so coordinates never show up in
      // a title or a shared link.
      ...(geoCoords && typedLocation !== GEO_FALLBACK_LABEL
        ? { location_label: typedLocation }
        : {}),
      occasion: activeOccasion,
      cost_estimate: budget,
      people: PEOPLE_BY_OCCASION[activeOccasion],
      stop_count: stopCount,
      day_part: dayPart,
      // Avoid repeating places from recent quests (soft exclusion).
      exclude_place_ids: getRecentPlaceIds(),
    }

    try {
      const [quest] = await Promise.all([generateQuest(request), wait(200)])
      track('quest_generated', {
        occasion: activeOccasion,
        budget,
        day_part: dayPart,
        stops_requested: stopCount,
        stop_count: quest.stops.length,
      })
      // Only flag a shortfall against what the user actually asked for — a
      // 1- or 2-stop quest is a deliberate choice now, not a failure.
      const softMessage =
        quest.stops.length > 0 && quest.stops.length < stopCount
          ? `Found ${quest.stops.length} great stop${quest.stops.length === 1 ? '' : 's'} — couldn't fill all ${stopCount} in this area.`
          : undefined
      recordQuestPlaces(quest)
      // They found their way to a quest; no need to offer the tour again.
      markTourSeen()
      localStorage.setItem(`quest_${quest.id}`, JSON.stringify(quest))
      navigate(`/quest/${quest.id}`, {
        state: { quest, softMessage, justCreated: true, request },
      })
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : 'Something went wrong.',
      )
      setSubmitting(false)
    } finally {
      if (submitSlowTimer.current) {
        window.clearTimeout(submitSlowTimer.current)
        submitSlowTimer.current = null
      }
      setSubmitSlow(false)
    }
  }

  const openCuratedQuest = useCallback(
    (quest: Quest) => {
      track('curated_quest_tapped', { quest_id: quest.id })
      sessionStorage.setItem(`quest_${quest.id}`, JSON.stringify(quest))
      navigate(`/quest/preview/${quest.id}`, { state: { quest } })
    },
    [navigate],
  )

  const activeData = OCCASIONS.find((o) => o.key === activeOccasion) ?? null

  const browseQuests = useCallback(() => {
    document
      .getElementById('curated-quests')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  return (
    <>
      <main className="home-page">
        <header className="home-hero">
          <span className="home-eyebrow">
            <span className="home-eyebrow-dot" aria-hidden />
            Now live in Hyderabad
          </span>
          <h1 className="home-hero-title">
            Tell us the mood.<br />
            <em>We'll handle the plans.</em>
          </h1>
          <p className="home-hero-sub">
            Pick your vibe and we'll build a curated 2–3 stop quest for your
            night out — food, drinks, and the right room to end up in.
          </p>
          <div className="home-cta-row">
            <button
              type="button"
              className="home-cta-primary"
              onClick={() => openSheet('date')}
            >
              Start a quest <span aria-hidden>→</span>
            </button>
            <button type="button" className="home-cta-ghost" onClick={browseQuests}>
              Browse quests
            </button>
          </div>
          <span className="home-city-pill">
            <span className="home-city-pill-flag" aria-hidden>🇮🇳</span>
            Hyderabad · more cities coming soon
          </span>
        </header>

        <section data-fade className="fade-up">
          <div className="home-section-header">
            <h2 className="home-section-title">What's the occasion?</h2>
          </div>
          <div className="home-grid">
            {OCCASIONS.map((o) => (
              <button
                key={o.key}
                type="button"
                className={`occasion-tile occasion-tile--${o.key}`}
                onClick={() => openSheet(o.key)}
                aria-haspopup="dialog"
                aria-label={`${o.title}: ${o.desc}`}
              >
                <span className="occasion-tile-chip" aria-hidden>
                  {o.emoji}
                </span>
                <div>
                  <p className="occasion-tile-title">{o.title}</p>
                  <p className="occasion-tile-desc">{o.desc}</p>
                </div>
              </button>
            ))}
          </div>
          <Link
            to="/create"
            className="home-build-own"
            onClick={() => track('build_own_tapped')}
          >
            <span aria-hidden>🛠️</span> Know your spots? Build your own quest
            <span aria-hidden> →</span>
          </Link>
        </section>

        <section
          className="curated-quests-section fade-up"
          id="curated-quests"
          data-fade
        >
          <div className="home-section-header">
            <h2 className="home-section-title">We made these for you</h2>
          </div>
          {curatedLoading ? (
            <LoadingState message="Loading curated quests..." />
          ) : curatedError ? (
            <ErrorState
              title="Could not load pre-made quests"
              description="Check your connection and try again."
              onRetry={loadCuratedQuests}
            />
          ) : curatedQuests.length === 0 ? (
            <EmptyState
              icon="🧭"
              title="No pre-made quests here yet"
              description={`We do not have curated quests for ${curatedCity} yet. You can still make one from any occasion above.`}
            />
          ) : (
            <div className="curated-quests-outer">
              <button
                type="button"
                className="curated-nav curated-nav--prev"
                aria-label="Scroll quests left"
                onClick={() => scrollCurated('prev')}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path
                    d="M15 6l-6 6 6 6"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              <button
                type="button"
                className="curated-nav curated-nav--next"
                aria-label="Scroll quests right"
                onClick={() => scrollCurated('next')}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path
                    d="M9 6l6 6-6 6"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              <div
                ref={curatedScrollRef}
                className="curated-quests-row"
                aria-label="Curated quests"
              >
                {curatedQuests.map((quest) => (
                  <button
                    key={quest.id}
                    type="button"
                    className="curated-quest-card"
                    onClick={() => openCuratedQuest(quest)}
                  >
                    <CuratedQuestImage quest={quest} />
                    <div className="curated-quest-body">
                      <p className="curated-quest-title">{quest.title}</p>
                      <div className="curated-quest-chips">
                        <span className="chip chip--accent">
                          {formatQuestDuration(quest.total_duration_minutes)}
                        </span>
                        <span className="chip chip--gold">
                          {costLabel(quest.total_cost_estimate)}
                        </span>
                      </div>
                      <StopTrail count={quest.stops.length} />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      </main>

      {activeOccasion && activeData && (
        <>
          {/* Backdrop */}
          <div
            className="sheet-overlay"
            aria-hidden
            onClick={closeSheet}
          />

          {/* Bottom sheet */}
          <div
            ref={sheetRef}
            role="dialog"
            aria-modal="true"
            aria-label={`Plan a ${activeData.title}`}
            className="sheet"
          >
            <div className="sheet-handle" aria-hidden />
            <button
              type="button"
              className="sheet-close"
              aria-label="Close"
              onClick={closeSheet}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
                <path
                  d="M3 3l8 8M11 3l-8 8"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            </button>

            <div
              className="sheet-occasion-badge"
              style={{
                background: OCCASION_TINTS[activeData.key],
                borderColor: 'transparent',
              }}
            >
              <span className="sheet-occasion-badge-emoji" aria-hidden>
                {activeData.emoji}
              </span>
              {activeData.title}
            </div>

            <form className="sheet-fields" onSubmit={handleSubmit}>
              {/* Occasion */}
              <div>
                <span className="sheet-field-label">Occasion</span>
                <div className="sheet-pill-row" role="group" aria-label="Occasion">
                  {OCCASIONS.map((o) => (
                    <button
                      key={o.key}
                      type="button"
                      className={`sheet-pill${activeOccasion === o.key ? ' sheet-pill--active' : ''}`}
                      aria-pressed={activeOccasion === o.key}
                      onClick={() => setActiveOccasion(o.key)}
                    >
                      <span aria-hidden style={{ marginRight: 6 }}>{o.emoji}</span>
                      {o.title}
                    </button>
                  ))}
                </div>
              </div>

              {/* Location */}
              <div>
                <label className="sheet-field-label" htmlFor="sheet-location">
                  Where?
                </label>
                <div className="sheet-location-wrap">
                  <LocationInput
                    inputRef={locationInputRef}
                    id="sheet-location"
                    className="sheet-location-input"
                    placeholder="City, neighbourhood, or area"
                    value={location}
                    onChange={(text) => {
                      setLocation(text)
                      setGeoCoords(null)
                      // "Location access denied — type a city instead" has
                      // done its job once they start typing.
                      setGeoError(null)
                    }}
                    onResolve={({ lat, lng }) =>
                      setGeoCoords({ lat, lng, source: 'picked' })
                    }
                    required
                  />
                  <button
                    type="button"
                    className="sheet-geo-btn"
                    aria-label="Use my current location"
                    disabled={geoLoading}
                    onClick={tryGeolocation}
                  >
                    {geoLoading ? '⏳' : '📍'}
                  </button>
                </div>
                {geoError && (
                  <p className="sheet-geo-status sheet-geo-status--error">
                    {geoError}
                  </p>
                )}
                {geoCoords?.source === 'device' && !geoError && (
                  <p className="sheet-geo-status">
                    Searching around your current location
                  </p>
                )}
              </div>

              {/* Day part */}
              <div>
                <span className="sheet-field-label">When?</span>
                <div className="sheet-pill-row" role="group" aria-label="Time of day">
                  {DAY_PART_OPTIONS.map((d) => {
                    const selected =
                      (dayPartChoice ??
                        (activeOccasion
                          ? DAY_PART_DEFAULT_BY_OCCASION[activeOccasion]
                          : null)) === d.value
                    return (
                      <button
                        key={d.value}
                        type="button"
                        className={`sheet-pill${selected ? ' sheet-pill--active' : ''}`}
                        aria-pressed={selected}
                        title={`Starts ${d.hint}`}
                        onClick={() => setDayPartChoice(d.value)}
                      >
                        {d.label}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Budget */}
              <div>
                <span className="sheet-field-label">Budget</span>
                <div className="sheet-pill-row" role="group" aria-label="Budget">
                  {BUDGET_OPTIONS.map((b) => (
                    <button
                      key={b.value}
                      type="button"
                      className={`sheet-pill${budget === b.value ? ' sheet-pill--active' : ''}`}
                      aria-pressed={budget === b.value}
                      onClick={() => setBudget(b.value)}
                    >
                      {b.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Stop count */}
              <div>
                <span className="sheet-field-label">How many stops?</span>
                <div className="sheet-stepper" role="group" aria-label="Number of stops">
                  <button
                    type="button"
                    className="sheet-stepper-btn"
                    aria-label="Fewer stops"
                    disabled={stopCount <= MIN_STOPS}
                    onClick={() => setStopCount((c) => Math.max(MIN_STOPS, c - 1))}
                  >
                    −
                  </button>
                  <span className="sheet-stepper-value" aria-live="polite">
                    {stopCount} {stopCount === 1 ? 'stop' : 'stops'}
                  </span>
                  <button
                    type="button"
                    className="sheet-stepper-btn"
                    aria-label="More stops"
                    disabled={stopCount >= MAX_STOPS}
                    onClick={() => setStopCount((c) => Math.min(MAX_STOPS, c + 1))}
                  >
                    +
                  </button>
                </div>
              </div>

              {/* Submit */}
              <button
                type="submit"
                className="sheet-submit"
                disabled={submitting || !location.trim()}
              >
                {submitting ? (
                  'Finding spots…'
                ) : (
                  <>
                    Build my quest <span aria-hidden>✦</span>
                  </>
                )}
              </button>

              {submitting && submitSlow && (
                <LoadingState message="Finding good spots near you..." />
              )}

              {submitError && (
                <ErrorState
                  title="Could not plan that quest"
                  description={submitError}
                  retryLabel="Try again"
                  onRetry={() => {
                    setSubmitError(null)
                    sheetRef.current?.querySelector('form')?.requestSubmit()
                  }}
                />
              )}
            </form>
          </div>
        </>
      )}

      {tour === 'nudge' && !activeOccasion && (
        <WelcomeNudge
          onOpen={() => {
            track('tour_opened', { source: 'nudge' })
            setTour('open')
          }}
          onDismiss={() => {
            markTourSeen()
            track('tour_nudge_dismissed')
            setTour('hidden')
          }}
        />
      )}
      {tour === 'open' && (
        <TourSheet
          onClose={closeTour}
          onExample={
            curatedQuests.length > 0
              ? () => {
                  closeTour({ step: 3, completed: true })
                  openCuratedQuest(curatedQuests[0])
                }
              : undefined
          }
        />
      )}
    </>
  )
}
