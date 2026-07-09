import { useCallback, useEffect, useMemo, useState } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import { fetchStopAlternatives, getApiBase } from '../api'
import type { Quest, Stop, StopAlternative, TravelMode } from '../types/quest'
import { EmptyState } from '../components/states'
import { track } from '../lib/analytics'
import { SwapSheet } from './SwapSheet'

const TRAVEL_EMOJI: Record<string, string> = {
  walking: '🚶',
  cycling: '🚲',
  transit: '🚌',
  driving: '🚗',
}

function formatTime(hhmm: string): string {
  const [hStr, mStr] = hhmm.split(':')
  const h = parseInt(hStr, 10)
  const m = parseInt(mStr, 10)
  const ampm = h >= 12 ? 'pm' : 'am'
  const hour = h % 12 || 12
  return m === 0
    ? `${hour}${ampm}`
    : `${hour}:${String(m).padStart(2, '0')}${ampm}`
}

function openingHoursText(stop: Stop): string | null {
  if (stop.place.open_24h_today) return 'Open 24 hrs'
  const opens = stop.place.opens_today
  const closes = stop.place.closes_today
  if (opens && closes)
    return `Opens ${formatTime(opens)} • Closes ${formatTime(closes)}`
  if (opens) return `Opens ${formatTime(opens)}`
  if (closes) return `Closes ${formatTime(closes)}`
  return null
}

function directionsUrl(place: Stop['place']): string {
  const base = 'https://www.google.com/maps/dir/?api=1'
  if (place.provider_id) {
    return `${base}&destination=${encodeURIComponent(place.name)}&destination_place_id=${place.provider_id}`
  }
  return `${base}&destination=${place.lat},${place.lng}`
}

function toMinutes(hhmm: string): number {
  const [hStr, mStr] = hhmm.split(':')
  return parseInt(hStr, 10) * 60 + parseInt(mStr, 10)
}

function addMinutes(hhmm: string, minutes: number): string {
  const total = toMinutes(hhmm) + minutes
  const day = 24 * 60
  const wrapped = ((total % day) + day) % day
  const h = Math.floor(wrapped / 60)
  const m = wrapped % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`
}

function durationMinutes(start: string, end: string): number {
  let delta = toMinutes(end) - toMinutes(start)
  if (delta < 0) delta += 24 * 60
  return delta
}

function questDuration(stops: Stop[]): number {
  if (stops.length === 0) return 0
  return durationMinutes(
    stops[0].time_block_start,
    stops[stops.length - 1].time_block_end,
  )
}

// Travel model mirrors the backend (quest_generator.py) so recomputed legs
// after a swap match what the generator would have produced.
const WALK_M_PER_MIN = 80
const DRIVE_M_PER_MIN = 350
const WALK_THRESHOLD_M = 1400

function haversineM(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number,
): number {
  const R = 6_371_000
  const rad = (d: number) => (d * Math.PI) / 180
  const dLat = rad(lat2 - lat1)
  const dLng = rad(lng2 - lng1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, a)))
}

function travelLeg(from: Stop, to: Stop): { minutes: number; mode: TravelMode } {
  const dist = haversineM(from.place.lat, from.place.lng, to.place.lat, to.place.lng)
  if (dist <= WALK_THRESHOLD_M) {
    return { minutes: Math.max(1, Math.round(dist / WALK_M_PER_MIN)), mode: 'walking' }
  }
  return { minutes: Math.max(1, Math.round(dist / DRIVE_M_PER_MIN)), mode: 'driving' }
}

function rescheduleWithAlternative(
  quest: Quest,
  stopIndex: number,
  alternative: StopAlternative,
): Quest {
  const replacement: Stop = {
    place: alternative.place,
    category: alternative.category,
    time_block_start: alternative.time_block_start,
    time_block_end: alternative.time_block_end,
    travel_to_next_minutes: alternative.travel_to_next_minutes,
    travel_mode: alternative.travel_mode,
    why_this_place: alternative.why_this_place,
  }
  const stops = quest.stops.map((stop, index) =>
    index === stopIndex ? replacement : { ...stop },
  )

  // Recompute every leg from geometry: swapping one stop changes the travel
  // time AND mode of the legs around it, and stale minutes would silently
  // shift the whole downstream schedule.
  for (let i = 0; i < stops.length; i += 1) {
    const dwell = durationMinutes(
      stops[i].time_block_start,
      stops[i].time_block_end,
    )
    if (i > 0) {
      const leg = travelLeg(stops[i - 1], stops[i])
      stops[i - 1] = {
        ...stops[i - 1],
        travel_to_next_minutes: leg.minutes,
        travel_mode: leg.mode,
      }
      const nextStart = addMinutes(stops[i - 1].time_block_end, leg.minutes)
      stops[i] = {
        ...stops[i],
        time_block_start: nextStart,
        time_block_end: addMinutes(nextStart, dwell),
      }
    }
  }
  const last = stops.length - 1
  stops[last] = { ...stops[last], travel_to_next_minutes: null, travel_mode: null }

  return {
    ...quest,
    stops,
    total_duration_minutes: questDuration(stops),
  }
}

function makeMarker(n: number): L.DivIcon {
  return L.divIcon({
    className: '',
    html: `<div class="qp-map-marker">${n}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })
}

function FitBounds({ positions }: { positions: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (positions.length === 0) return
    if (positions.length === 1) {
      map.setView(positions[0], 15)
    } else {
      map.fitBounds(L.latLngBounds(positions), { padding: [32, 32] })
    }
  }, [map, positions])
  return null
}

function StopPhoto({ placeId, name }: { placeId: string; name: string }) {
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>(
    'loading',
  )
  const src = `${getApiBase()}/api/places/photo?place_id=${encodeURIComponent(placeId)}&max_width=600`

  if (status === 'error' || !placeId) {
    return (
      <div className="qp-stop-hero">
        <div className="qp-stop-photo-placeholder" aria-hidden>
          Place
        </div>
      </div>
    )
  }

  return (
    <div
      className={`qp-stop-hero${status === 'loading' ? ' qp-stop-hero--loading' : ''}`}
    >
      <img
        className="qp-stop-photo"
        src={src}
        alt={name}
        onLoad={() => setStatus('loaded')}
        onError={() => setStatus('error')}
      />
    </div>
  )
}

function SwapIcon() {
  return (
    <svg
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M7 7h11m0 0-3-3m3 3-3 3M17 17H6m0 0 3 3m-3-3 3-3"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function StopCard({
  stop,
  index,
  previewing,
  onSwap,
  active = false,
  checked = false,
  onCheck,
  readOnly = false,
}: {
  stop: Stop
  index: number
  previewing: boolean
  onSwap: () => void
  active?: boolean
  checked?: boolean
  onCheck?: () => void
  readOnly?: boolean
}) {
  return (
    <li
      className={`qp-stop-card${previewing ? ' qp-stop-card--preview' : ''}`}
    >
      <StopPhoto placeId={stop.place.provider_id} name={stop.place.name} />
      {active && (
        <label className="qp-stop-check">
          <input
            type="checkbox"
            checked={checked}
            aria-label={`Mark stop ${index + 1} as visited`}
            onChange={onCheck}
          />
          <span aria-hidden />
        </label>
      )}
      <button
        type="button"
        className="qp-stop-swap-btn"
        aria-label={`Swap stop ${index + 1}`}
        disabled={readOnly}
        title={readOnly ? 'Swap available after you save this quest' : undefined}
        onClick={readOnly ? undefined : onSwap}
      >
        <SwapIcon />
      </button>
      <div className="qp-stop-body">
        <span className="qp-stop-index" aria-hidden>
          {index + 1}
        </span>
        <div className="qp-stop-content">
          <p className="qp-stop-name">{stop.place.name}</p>
          {stop.place.rating != null && (
            <p className="qp-stop-rating">
              ★ {stop.place.rating.toFixed(1)}
              {stop.place.user_ratings_total != null && (
                <span className="qp-stop-rating-count">
                  {' '}
                  ({stop.place.user_ratings_total.toLocaleString()})
                </span>
              )}
            </p>
          )}
          <p className="qp-stop-why">{stop.why_this_place}</p>
          <div className="qp-stop-meta">
            <span className="qp-stop-time-chip">
              {formatTime(stop.time_block_start)} – {formatTime(stop.time_block_end)}
            </span>
            {openingHoursText(stop) && (
              <span className="qp-stop-hours">{openingHoursText(stop)}</span>
            )}
            <a
              className="qp-stop-directions"
              href={directionsUrl(stop.place)}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`Directions to ${stop.place.name}`}
              onClick={() =>
                track('directions_opened', {
                  place_id: stop.place.provider_id,
                })
              }
            >
              <span aria-hidden>🧭</span> Directions
            </a>
          </div>
        </div>
      </div>
      {stop.travel_to_next_minutes != null && (
        <p className="qp-travel-tag">
          {TRAVEL_EMOJI[stop.travel_mode ?? ''] ?? '🚗'}{' '}
          {stop.travel_to_next_minutes} min {stop.travel_mode ?? 'drive'} to
          next stop
        </p>
      )}
    </li>
  )
}

export function QuestCard({
  quest,
  onQuestChange,
  active = false,
  completedStopIndexes = [],
  onToggleStopComplete,
  onMarkDone,
  readOnly = false,
}: {
  quest: Quest
  onQuestChange: (quest: Quest) => void
  active?: boolean
  completedStopIndexes?: number[]
  onToggleStopComplete?: (index: number) => void
  onMarkDone?: () => void
  readOnly?: boolean
}) {
  const [activeStopIndex, setActiveStopIndex] = useState<number | null>(null)
  const [alternatives, setAlternatives] = useState<StopAlternative[]>([])
  const [selectedAlternative, setSelectedAlternative] =
    useState<StopAlternative | null>(null)
  const [loadingAlternatives, setLoadingAlternatives] = useState(false)
  const [swapError, setSwapError] = useState<string | null>(null)

  const previewQuest = useMemo(() => {
    if (activeStopIndex == null || selectedAlternative == null) return null
    return rescheduleWithAlternative(quest, activeStopIndex, selectedAlternative)
  }, [activeStopIndex, quest, selectedAlternative])

  const displayQuest = previewQuest ?? quest
  const completedStops = useMemo(
    () => new Set(completedStopIndexes),
    [completedStopIndexes],
  )
  const positions: [number, number][] = displayQuest.stops.map((s) => [
    s.place.lat,
    s.place.lng,
  ])

  const closeSheet = useCallback(() => {
    setActiveStopIndex(null)
    setAlternatives([])
    setSelectedAlternative(null)
    setLoadingAlternatives(false)
    setSwapError(null)
  }, [])

  useEffect(() => {
    if (activeStopIndex == null) return
    let cancelled = false
    setLoadingAlternatives(true)
    setSwapError(null)
    setAlternatives([])
    setSelectedAlternative(null)

    fetchStopAlternatives(quest, activeStopIndex)
      .then((items) => {
        if (cancelled) return
        setAlternatives(items)
      })
      .catch((err) => {
        if (cancelled) return
        setSwapError(
          err instanceof Error ? err.message : 'Could not load alternatives.',
        )
      })
      .finally(() => {
        if (!cancelled) setLoadingAlternatives(false)
      })

    return () => {
      cancelled = true
    }
  }, [activeStopIndex, quest])

  const confirmSwap = useCallback(() => {
    if (!previewQuest || activeStopIndex == null) return
    track('stop_swapped', { stop_index: activeStopIndex })
    onQuestChange(previewQuest)
    closeSheet()
  }, [activeStopIndex, closeSheet, onQuestChange, previewQuest])

  return (
    <>
      {displayQuest.stops.length === 0 && (
        <EmptyState
          icon="🧭"
          title="No stops found"
          description="We could not find enough good matches for this quest. Try another location or occasion."
        />
      )}

      {positions.length > 0 && (
        <div className="qp-map-wrap">
          <MapContainer
            center={positions[0]}
            zoom={14}
            scrollWheelZoom={false}
            style={{ width: '100%', height: '100%' }}
            zoomControl={false}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {positions.length > 1 && (
              <Polyline
                positions={positions}
                pathOptions={{
                  color: '#38bdf8',
                  weight: 2.5,
                  dashArray: '6 5',
                  opacity: 0.85,
                }}
              />
            )}
            {displayQuest.stops.map((stop, i) => (
              <Marker
                key={`${stop.place.provider_id}-${i}`}
                position={[stop.place.lat, stop.place.lng]}
                icon={makeMarker(i + 1)}
              />
            ))}
            <FitBounds positions={positions} />
          </MapContainer>
        </div>
      )}

      {displayQuest.stops.length > 0 && (
        <ol className="qp-stops" aria-live="polite">
          {displayQuest.stops.map((stop, i) => (
            <StopCard
              key={`${stop.place.provider_id}-${i}`}
              stop={stop}
              index={i}
              previewing={activeStopIndex === i && selectedAlternative != null}
              onSwap={() => setActiveStopIndex(i)}
              active={active}
              checked={completedStops.has(i)}
              onCheck={() => onToggleStopComplete?.(i)}
              readOnly={readOnly}
            />
          ))}
        </ol>
      )}

      {active && displayQuest.stops.length > 0 && (
        <button type="button" className="qp-mark-done-btn" onClick={onMarkDone}>
          Mark as done
        </button>
      )}

      {activeStopIndex != null && (
        <SwapSheet
          stop={quest.stops[activeStopIndex]}
          alternatives={alternatives}
          selected={selectedAlternative}
          loading={loadingAlternatives}
          error={swapError}
          onPreview={setSelectedAlternative}
          onConfirm={confirmSwap}
          onCancel={closeSheet}
        />
      )}
    </>
  )
}
