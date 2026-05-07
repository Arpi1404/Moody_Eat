import { forwardRef, useEffect, useState } from 'react'
import { getApiBase } from '../api'
import type { Quest, Stop } from '../types/quest'

const BUDGET_LABELS: Record<string, string> = {
  cheap: '$ Budget',
  mid: '$$ Mid',
  splurge: '$$$ Splurge',
}

const OCCASION_LABELS: Record<string, string> = {
  date: 'Date night',
  friends: 'Friends',
  solo: 'Solo',
  family: 'Family',
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

export const ShareableQuestCard = forwardRef<HTMLDivElement, { quest: Quest }>(
  ({ quest }, ref) => {
    const durationLabel = formatDuration(quest.total_duration_minutes)
    const costLabel =
      BUDGET_LABELS[quest.total_cost_estimate] ?? quest.total_cost_estimate
    const occasionLabel = OCCASION_LABELS[quest.occasion] ?? quest.occasion

    return (
      <div ref={ref} className="share-card" aria-hidden>
        <div className="share-card-glow share-card-glow--cyan" />
        <div className="share-card-glow share-card-glow--violet" />

        <header className="share-card-header">
          <p className="share-brand">
            MoodyEat<span>.</span>
          </p>
          <span className="share-occasion-badge">{occasionLabel}</span>
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
            <li key={`${stop.place.provider_id}-${index}`} className="share-stop">
              <div className="share-stop-number">{index + 1}</div>
              <ShareableStopThumbnail stop={stop} />
              <div className="share-stop-copy">
                <p className="share-stop-name">{stop.place.name}</p>
                <p className="share-stop-vibe">{stop.why_this_place}</p>
              </div>
            </li>
          ))}
        </ol>

        <footer className="share-card-footer">
          <div className="share-chip-row">
            <span className="share-chip">{durationLabel}</span>
            <span className="share-chip">{costLabel}</span>
          </div>
          <p className="share-footer-text">Plan yours at moodyeat.app</p>
        </footer>
      </div>
    )
  },
)

ShareableQuestCard.displayName = 'ShareableQuestCard'
