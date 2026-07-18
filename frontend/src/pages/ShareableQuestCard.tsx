import { forwardRef, useEffect, useState } from 'react'
import { getApiBase } from '../api'
import { budgetLabel, formatInrEstimate } from '../lib/budget'
import type { Quest, Stop, StopCategory } from '../types/quest'

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

const CATEGORY_LABELS: Record<StopCategory, string> = {
  cafe: 'Café',
  restaurant: 'Restaurant',
  bar: 'Bar',
  activity: 'Activity',
  attraction: 'Attraction',
  other: 'Spot',
}

const CATEGORY_EMOJI: Record<StopCategory, string> = {
  cafe: '☕',
  restaurant: '🍽️',
  bar: '🍸',
  activity: '🎯',
  attraction: '🌆',
  other: '📍',
}

function formatDuration(minutes: number): string {
  const hours = minutes / 60
  return Number.isInteger(hours) ? `${hours} hrs` : `${hours.toFixed(1)} hrs`
}

/** "17:30" or "17:30:00" → "5:30 PM"; null when the value isn't a clock time.
 * The backend serializes Python `time` as HH:MM:SS. */
function formatClock(hhmm: string): string | null {
  const match = /^(\d{1,2}):(\d{2})(?::\d{2}(?:\.\d+)?)?$/.exec(hhmm)
  if (!match) return null
  const hours = Number(match[1])
  const minutes = match[2]
  const suffix = hours >= 12 ? 'PM' : 'AM'
  const hour12 = hours % 12 === 0 ? 12 : hours % 12
  return `${hour12}:${minutes} ${suffix}`
}

/** Public host for the CTA, without a leading www. Local dev (including the
 * marketing-card export harness) shows the real domain — an exported PNG
 * must never say "localhost". */
function displayHost(): string {
  const host = window.location.host.replace(/^www\./, '')
  if (host.startsWith('localhost') || host.startsWith('127.')) {
    return 'moodyeat.in'
  }
  return host
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
        <span aria-hidden>{CATEGORY_EMOJI[stop.category] ?? '📍'}</span>
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

function stopMeta(stop: Stop): string {
  const parts: string[] = [CATEGORY_LABELS[stop.category] ?? 'Spot']
  if (stop.place.rating != null) parts.push(`★ ${stop.place.rating.toFixed(1)}`)
  return parts.join('  ·  ')
}

function travelLabel(stop: Stop): string | null {
  if (stop.travel_to_next_minutes == null) return null
  const emoji = stop.travel_mode === 'driving' ? '🚗' : '🚶'
  const verb = stop.travel_mode === 'driving' ? 'drive' : 'walk'
  return `${emoji} ${stop.travel_to_next_minutes} min ${verb}`
}

export const ShareableQuestCard = forwardRef<HTMLDivElement, { quest: Quest }>(
  ({ quest }, ref) => {
    const occasionLabel = OCCASION_LABELS[quest.occasion] ?? quest.occasion
    const occasionEmoji = OCCASION_EMOJI[quest.occasion] ?? '✦'
    // Known occasions tint the card's accents; unknown ones keep the
    // terracotta defaults declared on .share-card.
    const occasionClass = OCCASION_LABELS[quest.occasion]
      ? ` share-card--${quest.occasion}`
      : ''
    // Long quests get a 4th stop; tighten the layout so it still fits.
    const denseClass = quest.stops.length >= 4 ? ' share-card--dense' : ''
    const budget =
      formatInrEstimate(
        quest.est_total_per_person_min_inr,
        quest.est_total_per_person_max_inr,
      ) ?? budgetLabel(quest.total_cost_estimate)

    return (
      <div ref={ref} className={`share-card${occasionClass}${denseClass}`} aria-hidden>
        <div className="share-glow share-glow--ember" />
        <div className="share-glow share-glow--amber" />
        <div className="share-grain" />
        <div className="share-frame" />

        <header className="share-header">
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

        <section className="share-hero">
          <p className="share-eyebrow">Tonight's food quest</p>
          <h1 className="share-title">{quest.title}</h1>
          {quest.created_by && (
            <p className="share-byline">Curated by {quest.created_by}</p>
          )}
          {quest.narrative && (
            <p className="share-narrative">{quest.narrative}</p>
          )}
        </section>

        <ol className="share-route">
          {quest.stops.map((stop, index) => {
            const last = index === quest.stops.length - 1
            const clock = formatClock(stop.time_block_start)
            const travel = travelLabel(stop)
            return (
              <li
                key={`${stop.place.provider_id ?? stop.place.name}-${index}`}
                className="share-leg"
              >
                <div className="share-leg-rail">
                  <span className="share-node">{index + 1}</span>
                  {!last && <span className="share-rail-line" />}
                </div>
                <div className={`share-leg-body${last ? ' share-leg-body--last' : ''}`}>
                  <div className="share-stop-row">
                    <div className="share-stop-copy">
                      {clock && <p className="share-stop-time">{clock}</p>}
                      <p className="share-stop-name">{stop.place.name}</p>
                      <p className="share-stop-meta">{stopMeta(stop)}</p>
                      <p className="share-stop-vibe">{stop.why_this_place}</p>
                    </div>
                    <ShareableStopThumbnail stop={stop} />
                  </div>
                  {!last && travel && (
                    <span className="share-travel">{travel}</span>
                  )}
                </div>
              </li>
            )
          })}
        </ol>

        <footer className="share-footer">
          <div className="share-stats">
            <div className="share-stat">
              <span className="share-stat-label">Duration</span>
              <span className="share-stat-value">
                {formatDuration(quest.total_duration_minutes)}
              </span>
            </div>
            <span className="share-stat-divider" />
            <div className="share-stat">
              <span className="share-stat-label">Budget</span>
              <span className="share-stat-value">{budget}</span>
            </div>
            <span className="share-stat-divider" />
            <div className="share-stat">
              <span className="share-stat-label">Stops</span>
              <span className="share-stat-value">{quest.stops.length}</span>
            </div>
          </div>
          <p className="share-cta">
            Plan yours&nbsp;→&nbsp;<strong>{displayHost()}</strong>
          </p>
        </footer>
      </div>
    )
  },
)

ShareableQuestCard.displayName = 'ShareableQuestCard'
