import { forwardRef, useEffect, useState } from 'react'
import { getApiBase } from '../api'
import { budgetLabel } from '../lib/budget'
import type { Quest, Stop } from '../types/quest'

const OCCASION_LABELS: Record<string, string> = {
  date: 'Date night',
  friends: 'Friends',
  solo: 'Solo',
  family: 'Family',
}

const OCCASION_EMOJI: Record<string, string> = {
  date: '🕯️',
  friends: '🥂',
  solo: '🍵',
  family: '🧆',
}

function formatDuration(minutes: number): string {
  const hours = minutes / 60
  return Number.isInteger(hours) ? `${hours}h` : `${hours.toFixed(1)}h`
}

function getInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  return words
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase())
    .join('')
}

function ShareableStopThumbnail({ stop }: { stop: Stop }) {
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>(
    stop.place.provider_id ? 'loading' : 'error',
  )
  const photoUrl = stop.place.provider_id
    ? `${getApiBase()}/api/places/photo?place_id=${encodeURIComponent(stop.place.provider_id)}&max_width=360`
    : ''

  useEffect(() => {
    if (status !== 'loading') return
    const timeout = window.setTimeout(() => setStatus('error'), 1600)
    return () => window.clearTimeout(timeout)
  }, [status])

  if (!photoUrl || status === 'error') {
    return (
      <div className="share-stop-thumb share-stop-thumb--placeholder">
        <span>{getInitials(stop.place.name) || 'ME'}</span>
      </div>
    )
  }

  return (
    <div className="share-stop-thumb">
      <img
        src={photoUrl}
        alt=""
        crossOrigin="anonymous"
        onLoad={() => setStatus('loaded')}
        onError={() => setStatus('error')}
      />
    </div>
  )
}

function travelLabel(stop: Stop): string | null {
  if (stop.travel_to_next_minutes == null) return null
  const emoji = stop.travel_mode === 'driving' ? '🚗' : '🚶'
  return `${emoji} ${stop.travel_to_next_minutes} min to the next stop`
}

export const ShareableQuestCard = forwardRef<HTMLDivElement, { quest: Quest }>(
  ({ quest }, ref) => {
    const durationLabel = formatDuration(quest.total_duration_minutes)
    const costLabel = budgetLabel(quest.total_cost_estimate)
    const occasionLabel = OCCASION_LABELS[quest.occasion] ?? quest.occasion
    const occasionEmoji = OCCASION_EMOJI[quest.occasion] ?? '✦'

    return (
      <div ref={ref} className="share-card" aria-hidden>
        <div className="share-card-wash share-card-wash--top" />
        <div className="share-card-wash share-card-wash--bottom" />
        <div className="share-card-frame" />

        <header className="share-card-header">
          <p className="share-brand">
            <span className="share-brand-mark">
              <span />
            </span>
            <span>
              Moody<span className="share-brand-accent">Eat</span>
            </span>
          </p>
          <span className="share-occasion-badge">
            <span aria-hidden>{occasionEmoji}</span>
            {occasionLabel}
          </span>
        </header>

        <section className="share-card-hero">
          <p className="share-eyebrow">Your next food quest</p>
          <h1 className="share-title">{quest.title}</h1>
          {quest.narrative && (
            <p className="share-narrative">{quest.narrative}</p>
          )}
        </section>

        <ol className="share-stop-list">
          {quest.stops.map((stop, index) => (
            <li key={`${stop.place.provider_id}-${index}`} className="share-stop-block">
              <div className="share-stop">
                <div className="share-stop-media">
                  <ShareableStopThumbnail stop={stop} />
                  <span className="share-stop-number">{index + 1}</span>
                </div>
                <div className="share-stop-copy">
                  <p className="share-stop-name">{stop.place.name}</p>
                  <p className="share-stop-vibe">{stop.why_this_place}</p>
                </div>
              </div>
              {index < quest.stops.length - 1 && (
                <div className="share-stop-connector">
                  <span className="share-stop-connector-line" />
                  {travelLabel(stop) && (
                    <span className="share-stop-connector-label">
                      {travelLabel(stop)}
                    </span>
                  )}
                </div>
              )}
            </li>
          ))}
        </ol>

        <footer className="share-card-footer">
          <div className="share-chip-row">
            <span className="share-chip">{durationLabel}</span>
            <span className="share-chip">{costLabel}</span>
            <span className="share-chip">{quest.stops.length} stops</span>
          </div>
          <p className="share-footer-cta">Plan yours at {window.location.host}</p>
        </footer>
      </div>
    )
  },
)

ShareableQuestCard.displayName = 'ShareableQuestCard'
