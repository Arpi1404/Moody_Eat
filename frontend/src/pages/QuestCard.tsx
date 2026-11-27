import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import { fetchStopAdditions, fetchStopAlternatives, getApiBase } from '../api'
import type { Quest, Stop, StopAlternative, StopKind } from '../types/quest'
import { CoachMark } from '../components/CoachMark'
import { PlaceLink } from '../components/PlaceLink'
import { EmptyState } from '../components/states'
import { track } from '../lib/analytics'
import { formatInrEstimate } from '../lib/budget'
import type { QuestHint } from '../lib/onboarding'
import {
  MAX_STOPS,
  insertStopAfter,
  removeStop,
  replaceStop,
  startingAt,
  withStops,
} from '../lib/questBuild'
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

function stopFromAlternative(alternative: StopAlternative): Stop {
  return {
    place: alternative.place,
    category: alternative.category,
    time_block_start: alternative.time_block_start,
    time_block_end: alternative.time_block_end,
    travel_to_next_minutes: alternative.travel_to_next_minutes,
    travel_mode: alternative.travel_mode,
    why_this_place: alternative.why_this_place,
    est_cost_per_person_min_inr: alternative.est_cost_per_person_min_inr,
    est_cost_per_person_max_inr: alternative.est_cost_per_person_max_inr,
    price_source: alternative.price_source,
  }
}

function reorderStops(quest: Quest, from: number, to: number): Quest {
  if (from === to || to < 0 || to >= quest.stops.length) return quest
  const stops = [...quest.stops]
  const [moved] = stops.splice(from, 1)
  stops.splice(to, 0, moved)
  return withStops(quest, startingAt(stops, quest.stops[0].time_block_start))
}

/** One places search made while the sheet is open. */
type OptionSearch =
  | { status: 'loading' }
  | { status: 'done'; options: StopAlternative[] }
  | { status: 'error'; message: string }

/** What a search is remembered under: a kind, or the stop's type as it is. */
const searchKey = (kind: StopKind | null): string => kind ?? 'similar'

const NO_ALTERNATIVES: StopAlternative[] = []

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

function StopPhoto({ place }: { place: Stop['place'] }) {
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>(
    'loading',
  )
  const placeId = place.provider_id
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
      <PlaceLink
        place={place}
        surface="quest"
        className="qp-stop-photo-link"
        decorative
      >
        <img
          className="qp-stop-photo"
          src={src}
          alt={place.name}
          onLoad={() => setStatus('loaded')}
          onError={() => setStatus('error')}
        />
      </PlaceLink>
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
  onMoveUp,
  onMoveDown,
  active = false,
  checked = false,
  onCheck,
  locked = false,
  onRemove,
  onAddAfter,
  hint = null,
  onHintDismiss,
  revealHint = false,
}: {
  stop: Stop
  index: number
  previewing: boolean
  onSwap: () => void
  onMoveUp?: () => void
  onMoveDown?: () => void
  active?: boolean
  checked?: boolean
  onCheck?: () => void
  /** Its stops cannot be changed: a preview, or a quest in progress. */
  locked?: boolean
  /** Absent on the only stop of a quest, which has to stay. */
  onRemove?: (byKeyboard: boolean) => void
  /** Add a stop between this one and the next. Absent on the last stop. */
  onAddAfter?: () => void
  /** The one-time hint to show on this card, if any. */
  hint?: QuestHint | null
  onHintDismiss?: (hint: QuestHint) => void
  /** Scroll to the hint when it appears (a replay the person asked for). */
  revealHint?: boolean
}) {
  const priceEstimate = formatInrEstimate(
    stop.est_cost_per_person_min_inr,
    stop.est_cost_per_person_max_inr,
  )
  return (
    <li
      className={`qp-stop-card${previewing ? ' qp-stop-card--preview' : ''}`}
    >
      <StopPhoto place={stop.place} />
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
      {active && hint === 'checkoff' && (
        <div className="qp-stop-check-anchor">
          <CoachMark
            placement="below-start"
            title="You're off."
            onDismiss={() => onHintDismiss?.('checkoff')}
            reveal={revealHint}
          >
            Tick each stop as you visit it.
          </CoachMark>
        </div>
      )}
      <div className="qp-stop-swap">
        {hint === 'swap' && (
          <CoachMark
            placement="left"
            title="Not feeling this one?"
            onDismiss={() => onHintDismiss?.('swap')}
            reveal={revealHint}
          >
            Swap it for a different spot.
          </CoachMark>
        )}
        <button
          type="button"
          className={`qp-stop-swap-btn${locked ? ' qp-stop-swap-btn--locked' : ''}`}
          aria-label={`Swap stop ${index + 1}`}
          onClick={onSwap}
        >
          <SwapIcon />
          <span>Swap</span>
        </button>
      </div>
      {!locked && (onMoveUp || onMoveDown) && (
        <div className="qp-stop-move">
          {hint === 'reorder' && (
            <CoachMark
              placement="left"
              title="Change the order."
              onDismiss={() => onHintDismiss?.('reorder')}
              reveal={revealHint}
            >
              The arrows move a stop earlier or later.
            </CoachMark>
          )}
          <div className="qp-stop-move-btns">
            <button
              type="button"
              className="qp-stop-move-btn"
              aria-label={`Move stop ${index + 1} earlier`}
              disabled={!onMoveUp}
              onClick={onMoveUp}
            >
              ↑
            </button>
            <button
              type="button"
              className="qp-stop-move-btn"
              aria-label={`Move stop ${index + 1} later`}
              disabled={!onMoveDown}
              onClick={onMoveDown}
            >
              ↓
            </button>
          </div>
        </div>
      )}
      <div className="qp-stop-body">
        <span className="qp-stop-index" aria-hidden>
          {index + 1}
        </span>
        <div className="qp-stop-content">
          <p className="qp-stop-name">
            <PlaceLink place={stop.place} surface="quest" />
          </p>
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
            {priceEstimate && (
              <span
                className="qp-stop-price-chip"
                title="Estimated spend per person"
              >
                {priceEstimate}
              </span>
            )}
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
            {!locked && onRemove && (
              <button
                type="button"
                className="qp-stop-remove"
                aria-label={`Remove stop ${index + 1}, ${stop.place.name}`}
                // A click with no pointer behind it came from the keyboard.
                onClick={(event) => onRemove(event.detail === 0)}
              >
                Remove
              </button>
            )}
          </div>
        </div>
      </div>
      {(stop.travel_to_next_minutes != null || (!locked && onAddAfter)) && (
        <div className="qp-travel-tag">
          {stop.travel_to_next_minutes != null && (
            <span>
              {TRAVEL_EMOJI[stop.travel_mode ?? ''] ?? '🚗'}{' '}
              {stop.travel_to_next_minutes} min {stop.travel_mode ?? 'drive'} to
              next stop
            </span>
          )}
          {!locked && onAddAfter && (
            <button
              type="button"
              className="qp-add-inline"
              aria-label={`Add a stop here, after stop ${index + 1}`}
              onClick={onAddAfter}
            >
              + Add a stop here
            </button>
          )}
        </div>
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
  onLockedSwap,
  onStopRemoved,
  onSwapSheetChange,
  hint = null,
  onHintDismiss,
  onHintUsed,
  onReplayHints,
  revealHints = false,
}: {
  quest: Quest
  onQuestChange: (quest: Quest) => void
  active?: boolean
  completedStopIndexes?: number[]
  onToggleStopComplete?: (index: number) => void
  onMarkDone?: () => void
  readOnly?: boolean
  /** Swap tapped on a quest whose stops cannot change right now: the page says
   * why, and how to unlock it. */
  onLockedSwap?: () => void
  /** A stop was removed. The page applies the change and offers to undo it. */
  onStopRemoved: (next: Quest, removed: Stop, byKeyboard: boolean) => void
  /** Told whenever the swap sheet opens or closes. Must be a stable function. */
  onSwapSheetChange?: (open: boolean) => void
  /** The one-time hint to show on the first stop, if any. */
  hint?: QuestHint | null
  onHintDismiss?: (hint: QuestHint) => void
  /** A control with a hint was used, whether or not the hint was showing. */
  onHintUsed?: (hint: QuestHint) => void
  /** When given, a "What can I do here?" link above the stops calls it. */
  onReplayHints?: () => void
  /** Scroll to each hint as it appears (during a replay). */
  revealHints?: boolean
}) {
  // The stop the open sheet is about: the one being swapped, or, when adding,
  // the one the new stop will follow.
  const [activeStopIndex, setActiveStopIndex] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const [kind, setKind] = useState<StopKind | null>(null)
  // Every search made since the sheet opened. Each one is a paid places
  // search, so going back to a kind shows what it found before.
  const [searches, setSearches] = useState<Record<string, OptionSearch>>({})
  const [selectedAlternative, setSelectedAlternative] =
    useState<StopAlternative | null>(null)

  const searched = !adding || kind != null
  const search = searched ? searches[searchKey(kind)] : undefined
  const alternatives =
    search?.status === 'done' ? search.options : NO_ALTERNATIVES
  const loadingAlternatives = search?.status === 'loading'
  const swapError = search?.status === 'error' ? search.message : null

  const previewQuest = useMemo(() => {
    if (activeStopIndex == null || selectedAlternative == null) return null
    const stop = stopFromAlternative(selectedAlternative)
    return adding
      ? insertStopAfter(quest, activeStopIndex, stop)
      : replaceStop(quest, activeStopIndex, stop)
  }, [activeStopIndex, adding, quest, selectedAlternative])
  // Where the stop being previewed sits in the previewed list.
  const previewIndex =
    previewQuest && activeStopIndex != null
      ? activeStopIndex + (adding ? 1 : 0)
      : null

  const swapSheetOpen = activeStopIndex != null
  useEffect(() => {
    onSwapSheetChange?.(swapSheetOpen)
  }, [onSwapSheetChange, swapSheetOpen])

  const displayQuest = previewQuest ?? quest
  const completedStops = useMemo(
    () => new Set(completedStopIndexes),
    [completedStopIndexes],
  )
  const positions: [number, number][] = displayQuest.stops.map((s) => [
    s.place.lat,
    s.place.lng,
  ])

  // Goes up each time the sheet opens or closes, so a response that arrives
  // for an earlier sheet is ignored (the fetch itself is not abortable here).
  const sheetSession = useRef(0)

  const closeSheet = useCallback(() => {
    sheetSession.current++
    setActiveStopIndex(null)
    setAdding(false)
    setKind(null)
    setSearches({})
    setSelectedAlternative(null)
  }, [])

  const runSearch = useCallback(
    (index: number, isAdding: boolean, wanted: StopKind | null) => {
      if (isAdding && wanted == null) return
      const session = sheetSession.current
      const remember = (result: OptionSearch) => {
        if (sheetSession.current !== session) return
        setSearches((current) => ({ ...current, [searchKey(wanted)]: result }))
      }

      remember({ status: 'loading' })
      const request =
        isAdding && wanted
          ? fetchStopAdditions(quest, index, wanted)
          : fetchStopAlternatives(quest, index, wanted)
      request
        .then((options) => remember({ status: 'done', options }))
        .catch((err) =>
          remember({
            status: 'error',
            message:
              err instanceof Error ? err.message : 'Could not load alternatives.',
          }),
        )
    },
    [quest],
  )

  const openSheet = useCallback(
    (index: number, isAdding: boolean) => {
      sheetSession.current++
      setActiveStopIndex(index)
      setAdding(isAdding)
      setKind(null)
      setSearches({})
      setSelectedAlternative(null)
    },
    [],
  )

  const openSwapSheet = useCallback(
    (index: number) => {
      onHintUsed?.('swap')
      openSheet(index, false)
      // Swapping starts with more of the same, as it always has.
      runSearch(index, false, null)
    },
    [onHintUsed, openSheet, runSearch],
  )

  // Adding waits for a kind to be chosen before it searches for anything.
  const openAddSheet = useCallback(
    (index: number) => {
      onHintUsed?.('addremove')
      openSheet(index, true)
    },
    [onHintUsed, openSheet],
  )

  // The only places a search starts are taps: nothing refetches on its own.
  const chooseKind = useCallback(
    (wanted: StopKind | null) => {
      if (activeStopIndex == null) return
      if (wanted !== kind) setSelectedAlternative(null)
      setKind(wanted)
      const known = searches[searchKey(wanted)]
      if (!known || known.status === 'error') {
        runSearch(activeStopIndex, adding, wanted)
      }
    },
    [activeStopIndex, adding, kind, runSearch, searches],
  )

  const handleRemove = useCallback(
    (index: number, byKeyboard: boolean) => {
      const next = removeStop(quest, index)
      if (next === quest) return
      onHintUsed?.('addremove')
      track('stop_removed', { stop_index: index, stop_count: next.stops.length })
      onStopRemoved(next, quest.stops[index], byKeyboard)
    },
    [onHintUsed, onStopRemoved, quest],
  )

  const confirmSwap = useCallback(() => {
    if (!previewQuest || activeStopIndex == null) return
    track('stop_swapped', {
      stop_index: activeStopIndex,
      kind: searchKey(kind),
    })
    onQuestChange(previewQuest)
    closeSheet()
  }, [activeStopIndex, closeSheet, kind, onQuestChange, previewQuest])

  const confirmAdd = useCallback(() => {
    if (!previewQuest || activeStopIndex == null || kind == null) return
    track('stop_added', {
      kind,
      stop_index: activeStopIndex + 1,
      stop_count: previewQuest.stops.length,
    })
    onQuestChange(previewQuest)
    closeSheet()
  }, [activeStopIndex, closeSheet, kind, onQuestChange, previewQuest])

  const moveStop = useCallback(
    (from: number, to: number) => {
      const next = reorderStops(quest, from, to)
      if (next === quest) return
      onHintUsed?.('reorder')
      track('stops_reordered', { from_index: from, to_index: to })
      onQuestChange(next)
    },
    [onHintUsed, onQuestChange, quest],
  )

  // A quest in progress remembers ticked-off stops by position, so its stops
  // stay put until it is finished or stopped.
  const locked = readOnly || active
  // Judged on the quest as it is, so a preview does not take the button that
  // opened the sheet off the page.
  const stopsFull = quest.stops.length >= MAX_STOPS

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

      {onReplayHints && displayQuest.stops.length > 0 && (
        <div className="qp-help">
          <button type="button" className="qp-help-link" onClick={onReplayHints}>
            <span className="qp-help-icon" aria-hidden>
              ?
            </span>
            What can I do here?
          </button>
        </div>
      )}

      {displayQuest.stops.length > 0 && (
        <ol className="qp-stops" aria-live="polite">
          {displayQuest.stops.map((stop, i) => (
            <StopCard
              key={`${stop.place.provider_id}-${i}`}
              stop={stop}
              index={i}
              previewing={previewIndex === i}
              onSwap={() => (locked ? onLockedSwap?.() : openSwapSheet(i))}
              onRemove={
                displayQuest.stops.length > 1
                  ? (byKeyboard) => handleRemove(i, byKeyboard)
                  : undefined
              }
              onAddAfter={
                !stopsFull && i < displayQuest.stops.length - 1
                  ? () => openAddSheet(i)
                  : undefined
              }
              onMoveUp={i > 0 ? () => moveStop(i, i - 1) : undefined}
              onMoveDown={
                i < displayQuest.stops.length - 1
                  ? () => moveStop(i, i + 1)
                  : undefined
              }
              active={active}
              checked={completedStops.has(i)}
              onCheck={() => {
                onHintUsed?.('checkoff')
                onToggleStopComplete?.(i)
              }}
              locked={locked}
              hint={i === 0 ? hint : null}
              onHintDismiss={onHintDismiss}
              revealHint={revealHints}
            />
          ))}
        </ol>
      )}

      {!locked && displayQuest.stops.length > 0 && !stopsFull && (
        <div className="qp-add-wrap">
          {hint === 'addremove' && (
            <CoachMark
              placement="above"
              title="Make it yours."
              onDismiss={() => onHintDismiss?.('addremove')}
              reveal={revealHints}
            >
              Add stops here, and remove any from their cards.
            </CoachMark>
          )}
          <button
            type="button"
            className="qp-add-stop"
            aria-label="Add a stop at the end"
            onClick={() => openAddSheet(quest.stops.length - 1)}
          >
            + Add a stop
          </button>
        </div>
      )}
      {!locked && stopsFull && (
        <p className="qp-add-full">
          {MAX_STOPS} stops is the most a quest can hold.
        </p>
      )}

      {active && displayQuest.stops.length > 0 && (
        <button type="button" className="qp-mark-done-btn" onClick={onMarkDone}>
          Mark as done
        </button>
      )}

      {activeStopIndex != null && (
        <SwapSheet
          mode={adding ? 'add' : 'swap'}
          stopName={quest.stops[activeStopIndex].place.name}
          kind={kind}
          searched={searched}
          alternatives={alternatives}
          selected={selectedAlternative}
          loading={loadingAlternatives}
          error={swapError}
          onChooseKind={chooseKind}
          onPreview={setSelectedAlternative}
          onConfirm={adding ? confirmAdd : confirmSwap}
          onCancel={closeSheet}
        />
      )}
    </>
  )
}
