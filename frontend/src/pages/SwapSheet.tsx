import { useEffect, useState } from 'react'
import { getApiBase } from '../api'
import type { Stop, StopAlternative } from '../types/quest'

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

export function SwapSheet({
  stop,
  alternatives,
  selected,
  loading,
  error,
  onPreview,
  onConfirm,
  onCancel,
}: {
  stop: Stop
  alternatives: StopAlternative[]
  selected: StopAlternative | null
  loading: boolean
  error: string | null
  onPreview: (alternative: StopAlternative) => void
  onConfirm: () => void
  onCancel: () => void
}) {
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
        aria-label="Cancel stop swap"
        onClick={onCancel}
      />
      <section
        className="swap-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="swap-sheet-title"
      >
        <div className="swap-sheet-handle" aria-hidden />
        <div className="swap-sheet-header">
          <p className="swap-sheet-eyebrow">Swap stop</p>
          <h2 id="swap-sheet-title">Replace {stop.place.name}</h2>
          <p>Preview a new stop, then confirm when the timeline feels right.</p>
        </div>

        {loading && (
          <div className="swap-sheet-status" role="status">
            Finding nearby alternatives...
          </div>
        )}

        {!loading && error && <p className="swap-sheet-error">{error}</p>}

        {!loading && !error && alternatives.length === 0 && (
          <p className="swap-sheet-status">
            No unused alternatives found for this stop.
          </p>
        )}

        {!loading && !error && alternatives.length > 0 && (
          <div className="swap-alt-list">
            {alternatives.map((alternative) => {
              const active =
                selected?.place.provider_id === alternative.place.provider_id
              return (
                <button
                  type="button"
                  key={alternative.place.provider_id}
                  className={`swap-alt-card${active ? ' swap-alt-card--active' : ''}`}
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
                  </span>
                </button>
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
          Confirm swap
        </button>
      </section>
    </>
  )
}
