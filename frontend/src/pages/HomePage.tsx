import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchCuratedQuests, generateQuest, getApiBase } from '../api'
import type { Quest } from '../types/quest'
import '../App.css'

// ── Static data ───────────────────────────────────────────────────────────────

const OCCASIONS = [
  {
    key: 'date',
    emoji: '🌹',
    title: 'Date Night',
    desc: 'A romantic evening for two',
  },
  {
    key: 'friends',
    emoji: '🎉',
    title: 'Friends Hangout',
    desc: 'A great night out with the crew',
  },
  {
    key: 'solo',
    emoji: '🎧',
    title: 'Solo Time',
    desc: 'Your city, your pace',
  },
  {
    key: 'family',
    emoji: '👨‍👩‍👧',
    title: 'Family Outing',
    desc: 'Fun for everyone',
  },
] as const

type OccasionKey = (typeof OCCASIONS)[number]['key']

const OCCASION_ICONS: Record<OccasionKey, string> = {
  date: '🌹',
  friends: '🎉',
  solo: '🎧',
  family: '👨‍👩‍👧',
}

const BUDGET_OPTIONS = [
  { value: 'cheap', label: 'Cheap' },
  { value: 'mid', label: 'Mid' },
  { value: 'splurge', label: 'Splurge' },
] as const

type Budget = (typeof BUDGET_OPTIONS)[number]['value']

const DURATION_OPTIONS = [
  { value: 2, label: '2 hr' },
  { value: 3, label: 'Half Evening' },
  { value: 5, label: 'Full Night' },
] as const

type DurationHours = (typeof DURATION_OPTIONS)[number]['value']

// Solo trips always count as 1 person; family trips as 4
const PEOPLE_BY_OCCASION: Record<OccasionKey, number> = {
  date: 2,
  friends: 4,
  solo: 1,
  family: 4,
}

// ── Geolocation helpers ───────────────────────────────────────────────────────

async function reverseGeocode(lat: number, lng: number): Promise<string> {
  // Uses OpenStreetMap Nominatim — no API key required for light/personal use.
  const res = await fetch(
    `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`,
    { headers: { 'Accept-Language': 'en' } },
  )
  if (!res.ok) throw new Error('Geocode failed')
  const data = await res.json()
  const a = data.address ?? {}
  return (
    a.city ?? a.town ?? a.suburb ?? a.village ?? a.county ?? 'your location'
  )
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
  const city = (await reverseGeocode(pos.coords.latitude, pos.coords.longitude)).trim()
  if (!city || city === 'your location') {
    throw new Error('City not detected')
  }
  return city
}

function formatQuestDuration(minutes: number): string {
  const hours = minutes / 60
  return Number.isInteger(hours) ? `${hours}h` : `${hours.toFixed(1)}h`
}

function costLabel(cost: Quest['total_cost_estimate']): string {
  if (cost === 'cheap') return 'Cheap'
  if (cost === 'splurge') return 'Splurge'
  return 'Mid'
}

function CuratedQuestImage({ quest }: { quest: Quest }) {
  const [failed, setFailed] = useState(false)
  const firstStop = quest.stops[0]
  const placeId = firstStop?.place.provider_id
  const src = placeId
    ? `${getApiBase()}/api/places/photo?place_id=${encodeURIComponent(placeId)}&max_width=800`
    : ''

  if (!src || failed) {
    return (
      <div className="curated-quest-image curated-quest-image--fallback">
        <span aria-hidden>{OCCASION_ICONS[quest.occasion]}</span>
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
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export function HomePage() {
  const navigate = useNavigate()

  const [activeOccasion, setActiveOccasion] = useState<OccasionKey | null>(null)
  const [location, setLocation] = useState('')
  const [geoLoading, setGeoLoading] = useState(false)
  const [geoError, setGeoError] = useState<string | null>(null)
  const [budget, setBudget] = useState<Budget>('mid')
  const [duration, setDuration] = useState<DurationHours>(3)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [curatedQuests, setCuratedQuests] = useState<Quest[]>([])

  const sheetRef = useRef<HTMLDivElement>(null)
  const locationInputRef = useRef<HTMLInputElement>(null)

  const tryGeolocation = useCallback(() => {
    if (!navigator.geolocation) {
      setGeoError('Geolocation not supported')
      return
    }
    setGeoLoading(true)
    setGeoError(null)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const name = await reverseGeocode(
            pos.coords.latitude,
            pos.coords.longitude,
          )
          setLocation(name)
        } catch {
          // silent — user can type manually
        } finally {
          setGeoLoading(false)
        }
      },
      () => {
        setGeoLoading(false)
        setGeoError('Location access denied — type a city instead')
      },
      { timeout: 8_000 },
    )
  }, [])

  useEffect(() => {
    let cancelled = false

    async function loadCuratedQuests() {
      let city = 'Hyderabad'
      try {
        city = await detectCity()
      } catch {
        city = 'Hyderabad'
      }

      try {
        const quests = await fetchCuratedQuests(city)
        if (!cancelled && quests.length > 0) {
          setCuratedQuests(quests)
        }
      } catch {
        if (!cancelled) setCuratedQuests([])
      }
    }

    loadCuratedQuests()
    return () => {
      cancelled = true
    }
  }, [])

  const openSheet = useCallback(
    (key: OccasionKey) => {
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
    setSubmitError(null)
    try {
      const quest = await generateQuest({
        location: location.trim(),
        occasion: activeOccasion,
        cost_estimate: budget,
        people: PEOPLE_BY_OCCASION[activeOccasion],
        duration_hours: duration,
      })
      localStorage.setItem(`quest_${quest.id}`, JSON.stringify(quest))
      navigate(`/quest/${quest.id}`, { state: { quest } })
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : 'Something went wrong.',
      )
      setSubmitting(false)
    }
  }

  const openCuratedQuest = useCallback(
    (quest: Quest) => {
      sessionStorage.setItem(`quest_${quest.id}`, JSON.stringify(quest))
      navigate(`/quest/preview/${quest.id}`, { state: { quest } })
    },
    [navigate],
  )

  const activeData = OCCASIONS.find((o) => o.key === activeOccasion) ?? null

  return (
    <>
      <main className="home-page">
        <header className="home-header">
          <h1 className="home-brand">
            Moody<span>Eat</span>
          </h1>
          <p className="home-tagline">Pick a vibe. We'll handle the rest.</p>
        </header>

        <section>
          <p className="home-section-label">What's the occasion?</p>
          <div className="home-grid">
            {OCCASIONS.map((o) => (
              <button
                key={o.key}
                type="button"
                className={`occasion-tile occasion-tile--${o.key}`}
                onClick={() => openSheet(o.key)}
                aria-haspopup="dialog"
              >
                <span className="occasion-tile-emoji" aria-hidden>
                  {o.emoji}
                </span>
                <p className="occasion-tile-title">{o.title}</p>
                <p className="occasion-tile-desc">{o.desc}</p>
              </button>
            ))}
          </div>
        </section>

        {curatedQuests.length > 0 && (
          <section className="curated-quests-section">
            <p className="home-section-label">Pre-made for tonight.</p>
            <div className="curated-quests-row" aria-label="Curated quests">
              {curatedQuests.map((quest) => (
                <button
                  key={quest.id}
                  type="button"
                  className="curated-quest-card"
                  onClick={() => openCuratedQuest(quest)}
                >
                  <CuratedQuestImage quest={quest} />
                  <div className="curated-quest-body">
                    <div className="curated-quest-title-row">
                      <span className="curated-quest-icon" aria-hidden>
                        {OCCASION_ICONS[quest.occasion]}
                      </span>
                      <p className="curated-quest-title">{quest.title}</p>
                    </div>
                    <div className="curated-quest-chips">
                      <span>{formatQuestDuration(quest.total_duration_minutes)}</span>
                      <span>{costLabel(quest.total_cost_estimate)}</span>
                      <span>{quest.stops.length} stops</span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}
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

            <div className="sheet-occasion-badge">
              <span className="sheet-occasion-badge-emoji" aria-hidden>
                {activeData.emoji}
              </span>
              {activeData.title}
            </div>

            <form className="sheet-fields" onSubmit={handleSubmit}>
              {/* Location */}
              <div>
                <label className="sheet-field-label" htmlFor="sheet-location">
                  Where?
                </label>
                <div className="sheet-location-wrap">
                  <input
                    ref={locationInputRef}
                    id="sheet-location"
                    className="sheet-location-input"
                    type="text"
                    placeholder="City, neighbourhood, or area"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    required
                    autoComplete="off"
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

              {/* Duration */}
              <div>
                <span className="sheet-field-label">How long?</span>
                <div className="sheet-pill-row" role="group" aria-label="Duration">
                  {DURATION_OPTIONS.map((d) => (
                    <button
                      key={d.value}
                      type="button"
                      className={`sheet-pill${duration === d.value ? ' sheet-pill--active' : ''}`}
                      aria-pressed={duration === d.value}
                      onClick={() => setDuration(d.value)}
                    >
                      {d.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Submit */}
              <button
                type="submit"
                className="sheet-submit"
                disabled={submitting || !location.trim()}
              >
                {submitting ? 'Finding spots…' : 'Plan my evening'}
              </button>

              {submitError && (
                <p className="sheet-error" role="alert">
                  {submitError}
                </p>
              )}
            </form>
          </div>
        </>
      )}
    </>
  )
}
