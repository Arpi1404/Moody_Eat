import { useEffect, useRef, useState } from 'react'
import { getApiBase } from '../api'
import { PlaceLink } from '../components/PlaceLink'
import { formatInrEstimate } from '../lib/budget'
import { STOP_KINDS } from '../lib/stopKinds'
import type { StopAlternative, StopKind } from '../types/quest'

function formatDistanceDelta(meters: number): string {
  const sign = meters > 0 ? '+' : ''
  const abs = Math.abs(meters)
  if (abs >= 1000) {
    return `${sign}${(meters / 1000).toFixed(1)}km`
  }
  return `${sign}${Math.round(meters)}m`
}

function formatMoneyDelta(value: number): string | null {
  if (value === 0) return null
  return `${value > 0 ? '+' : '-'}₹${Math.abs(value)}`
}

function formatMinuteDelta(value: number): string {
  if (value === 0) return '0 min'
  return `${value > 0 ? '+' : ''}${value} min`
}

/** What adding a place does to the quest. Nothing here is better or worse than
 * the other, so the badges carry no colour. */
function AdditionBadges({ option }: { option: StopAlternative }) {
  const price = formatInrEstimate(
    option.est_cost_per_person_min_inr,
    option.est_cost_per_person_max_inr,
  )
  const away = option.place.distance_meters
  return (
    <span className="swap-delta-row">
      <span className="swap-delta-badge">
        {away >= 1000 ? `${(away / 1000).toFixed(1)}km` : `${Math.round(away)}m`}{' '}
        away
      </span>
      <span className="swap-delta-badge">
        {formatMinuteDelta(option.delta.time_change_minutes)} longer
      </span>
      {price && <span className="swap-delta-badge">{price}</span>}
    </span>
  )
}

function AlternativePhoto({
  placeId,
  name,
}: {
  placeId: string
  name: string
}) {
  const [failed, setFailed] = useState(false)
  const src = `${getApiBase()}/api/places/photo?place_id=${encodeURIComponent(placeId)}&max_width=400`

  if (failed || !placeId) {
    return (
      <div className="swap-alt-photo swap-alt-photo--placeholder" aria-hidden>
        <span>Place</span>
      </div>
    )
  }

  return (
    <img
      className="swap-alt-photo"
      src={src}
      alt={name}
      onError={() => setFailed(true)}
    />
  )
}

/** The sheet for swapping a stop, and for adding one after it. */
export function SwapSheet({
  mode,
  stopName,
  dropsNote,
  kind,
  searched,
  alternatives,
  selected,
  loading,
  error,
  onChooseKind,
  onPreview,
  onConfirm,
  onCancel,
}: {
  mode: 'swap' | 'add'
  /** The stop being replaced, or the one a new stop will follow. */
  stopName: string
  /** The stop has a note someone typed, which a swap would remove. */
  dropsNote: boolean
  /** null: the same type as the stop now (swap), or nothing chosen yet (add). */
  kind: StopKind | null
  /** False until a search has been asked for: adding starts with a choice. */
  searched: boolean
  alternatives: StopAlternative[]
  selected: StopAlternative | null
  loading: boolean
  error: string | null
  /** Also how a failed search is tried again: choose the same kind. */
  onChooseKind: (kind: StopKind | null) => void
  onPreview: (alternative: StopAlternative) => void
  onConfirm: () => void
  onCancel: () => void
}) {
  const adding = mode === 'add'
  const plural = STOP_KINDS.find((option) => option.key === kind)?.plural
  const settled = searched && !loading && !error
  const sheetRef = useRef<HTMLElement>(null)

  // Take the keyboard into the sheet, and hand it back on the way out.
  useEffect(() => {
    const opener = document.activeElement
    sheetRef.current?.focus({ preventScroll: true })
    return () => {
      if (opener instanceof HTMLElement && opener.isConnected) {
        opener.focus({ preventScroll: true })
      }
    }
  }, [])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKeyDown)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = ''
    }
  }, [onCancel])

  return (
    <>
      <button
        type="button"
        className="swap-sheet-overlay"
        aria-label={adding ? 'Cancel adding a stop' : 'Cancel stop swap'}
        onClick={onCancel}
      />
      <section
        ref={sheetRef}
        tabIndex={-1}
        className="swap-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="swap-sheet-title"
      >
        <div className="swap-sheet-handle" aria-hidden />
        <div className="swap-sheet-header">
          <p className="swap-sheet-eyebrow">
            {adding ? 'Add a stop' : 'Swap stop'}
          </p>
          <h2 id="swap-sheet-title">
            {adding ? 'After' : 'Replace'} {stopName}
          </h2>
          <p>
            {adding
              ? 'Pick a kind, preview a place, then add it.'
              : 'Preview a new stop, then confirm when the timeline feels right.'}
          </p>
          {dropsNote && !adding && (
            <p className="swap-sheet-note">
              The personal note on this stop is about {stopName}. Swapping
              removes it.
            </p>
          )}
        </div>

        <div className="swap-kind-row" role="group" aria-label="Kind of stop">
          {!adding && (
            <button
              type="button"
              className={`swap-kind-chip${kind === null ? ' swap-kind-chip--active' : ''}`}
              aria-pressed={kind === null}
              onClick={() => onChooseKind(null)}
            >
              Similar
            </button>
          )}
          {STOP_KINDS.map((option) => (
            <button
              key={option.key}
              type="button"
              className={`swap-kind-chip${kind === option.key ? ' swap-kind-chip--active' : ''}`}
              aria-pressed={kind === option.key}
              onClick={() => onChooseKind(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>

        {!searched && (
          <p className="swap-sheet-status">
            We'll look for places near {stopName}.
          </p>
        )}

        {loading && (
          <div className="swap-sheet-status" role="status">
            Finding nearby places...
          </div>
        )}

        {!loading && error && (
          <div role="alert">
            <p className="swap-sheet-error">{error}</p>
            <button
              type="button"
              className="swap-sheet-retry"
              onClick={() => onChooseKind(kind)}
            >
              Try again
            </button>
          </div>
        )}

        {settled && alternatives.length === 0 && (
          <p className="swap-sheet-status" role="status">
            {plural
              ? `No well-reviewed ${plural} found near ${adding ? stopName : 'here'}. `
              : 'No unused alternatives found for this stop. '}
            {adding
              ? 'Your quest is unchanged.'
              : `${stopName} stays as it is.`}
          </p>
        )}

        {settled && alternatives.length > 0 && (
          <div className="swap-alt-list">
            <p className="swap-sheet-note">
              Opening hours aren't checked for these. Look on Google Maps before
              you go.
            </p>
            {alternatives.map((alternative) => {
              const active =
                selected?.place.provider_id === alternative.place.provider_id
              // The card is a wrapper, not a button, so the Google Maps link
              // can sit inside it: a link nested in a button is invalid HTML.
              return (
                <div
                  key={alternative.place.provider_id}
                  className={`swap-alt-card${active ? ' swap-alt-card--active' : ''}`}
                >
                  <button
                    type="button"
                    className="swap-alt-select"
                    aria-pressed={active}
                    onClick={() => onPreview(alternative)}
                  >
                    <AlternativePhoto
                      placeId={alternative.place.provider_id}
                      name={alternative.place.name}
                    />
                    <span className="swap-alt-body">
                      <span className="swap-alt-name">
                        {alternative.place.name}
                      </span>
                      <span className="swap-alt-vibe">
                        {alternative.why_this_place}
                      </span>
                      {adding ? (
                        <AdditionBadges option={alternative} />
                      ) : (
                        <span className="swap-delta-row">
                          <span
                            className={`swap-delta-badge${alternative.delta.time_change_minutes > 0 ? ' swap-delta-badge--negative' : alternative.delta.time_change_minutes < 0 ? ' swap-delta-badge--positive' : ''}`}
                          >
                            {formatMinuteDelta(
                              alternative.delta.time_change_minutes,
                            )}
                          </span>
                          {formatMoneyDelta(alternative.delta.cost_change) !==
                            null && (
                            <span
                              className={`swap-delta-badge${alternative.delta.cost_change > 0 ? ' swap-delta-badge--negative' : ' swap-delta-badge--positive'}`}
                            >
                              {formatMoneyDelta(alternative.delta.cost_change)}
                            </span>
                          )}
                          <span
                            className={`swap-delta-badge${alternative.delta.distance_change_meters > 0 ? ' swap-delta-badge--negative' : alternative.delta.distance_change_meters < 0 ? ' swap-delta-badge--positive' : ''}`}
                          >
                            {formatDistanceDelta(
                              alternative.delta.distance_change_meters,
                            )}
                          </span>
                        </span>
                      )}
                    </span>
                  </button>
                  <PlaceLink
                    place={alternative.place}
                    surface="swap"
                    className="swap-alt-link"
                  >
                    View on Google Maps
                  </PlaceLink>
                </div>
              )
            })}
          </div>
        )}

        <button
          type="button"
          className="swap-confirm-btn"
          disabled={!selected}
          onClick={onConfirm}
        >
          {adding ? 'Add this stop' : 'Confirm swap'}
        </button>
      </section>
    </>
  )
}
