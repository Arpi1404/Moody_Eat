// The two ways the home page shows a catalogue quest: the plan at the top of
// the page, and the cards in the row further down.
//
// Everything inside a button is a <span>: a button may only hold phrasing
// content. What a screen reader hears is the button's label (cardLabel).

import { useState } from 'react'
import { getApiBase } from '../api'
import {
  cardLabel,
  costText,
  durationText,
  leadStop,
  startText,
  stopNames,
} from '../lib/catalogue'
import { closedTodayLine, notOnLine } from '../lib/closedDays'
import { OCCASION_LABELS, occasionPhoto } from '../lib/occasions'
import type { Quest, Weekday } from '../types/quest'

/** The quest's lead photo, or the occasion's own picture when there is none.
 *
 * The preview and the card ask for the same address, so a quest shown in both
 * places costs one photo request. */
function QuestPhoto({ quest, eager = false }: { quest: Quest; eager?: boolean }) {
  const placeId = leadStop(quest)?.place.provider_id
  const src = placeId
    ? `${getApiBase()}/api/places/photo?place_id=${encodeURIComponent(placeId)}&max_width=800`
    : ''
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  const fallback = !src || failedSrc === src

  return (
    // Decorative: the button's label already says what the quest is.
    <img
      className={fallback ? 'quest-photo quest-photo--fallback' : 'quest-photo'}
      src={fallback ? occasionPhoto(quest.occasion) : src}
      alt=""
      loading={eager ? 'eager' : 'lazy'}
      decoding="async"
      onError={() => setFailedSrc(src)}
    />
  )
}

function StopList({ quest }: { quest: Quest }) {
  return (
    <span className="quest-stops">
      {stopNames(quest).map((name, i) => (
        <span key={i} className="quest-stop">
          <span className="quest-stop-number">{i + 1}</span>
          <span className="quest-stop-name">{name}</span>
        </span>
      ))}
    </span>
  )
}

/** "Not on Mondays", and on that day which stop is shut. */
function QuestDays({ quest, today }: { quest: Quest; today: Weekday }) {
  const notOn = notOnLine(quest)
  if (!notOn) return null
  const shutToday = closedTodayLine(quest, today)
  if (!shutToday) return <span className="curated-quest-days">{notOn}</span>
  return (
    <span className="curated-quest-days curated-quest-days--today">
      <strong>{shutToday}.</strong> {notOn}.
    </span>
  )
}

export function QuestCardButton({
  quest,
  today,
  onOpen,
}: {
  quest: Quest
  today: Weekday
  onOpen: () => void
}) {
  return (
    <button
      type="button"
      className="curated-quest-card"
      aria-label={cardLabel(quest, today)}
      onClick={onOpen}
    >
      <span className="curated-quest-image">
        <QuestPhoto quest={quest} />
        <span className="curated-quest-occasion-badge">
          {OCCASION_LABELS[quest.occasion]}
        </span>
      </span>
      <span className="curated-quest-body">
        <span className="curated-quest-title">{quest.title}</span>
        {quest.audience_line && (
          <span className="curated-quest-for">{quest.audience_line}</span>
        )}
        <StopList quest={quest} />
        <span className="curated-quest-chips">
          <span className="chip chip--accent">
            {durationText(quest.total_duration_minutes)}
          </span>
          <span className="chip chip--gold">{costText(quest)}</span>
        </span>
        <QuestDays quest={quest} today={today} />
      </span>
    </button>
  )
}

/** One ready-made quest, shown as a plan at the top of the page. It holds the
 * same shape while the catalogue loads, and when there is nothing to show. */
export function HeroPlan({
  quest,
  loading,
  today,
  onOpen,
}: {
  quest: Quest | null
  loading: boolean
  today: Weekday
  onOpen: (quest: Quest) => void
}) {
  if (loading) {
    return (
      <div className="hero-plan hero-plan--loading" role="status">
        <span className="hero-plan-photo" />
        <span className="hero-plan-body">
          <span className="visually-hidden">Loading a ready-made quest</span>
          <span className="hero-plan-bar hero-plan-bar--kicker" aria-hidden />
          <span className="hero-plan-bar hero-plan-bar--title" aria-hidden />
          <span className="hero-plan-bar" aria-hidden />
          <span className="hero-plan-bar" aria-hidden />
          <span className="hero-plan-bar" aria-hidden />
        </span>
      </div>
    )
  }

  // The request failed, or there is no quest to show today.
  if (!quest) {
    return (
      <div className="hero-plan hero-plan--empty">
        <span className="hero-plan-photo">
          <img className="quest-photo" src={occasionPhoto('friends')} alt="" />
        </span>
        <span className="hero-plan-body">
          <span className="hero-plan-kicker">What you get</span>
          <span className="hero-plan-title">A few good places, in the right order</span>
          <span className="hero-plan-explain">
            Pick who you're with and where. Your plan comes timed and mapped,
            and you can change any stop you don't fancy.
          </span>
        </span>
      </div>
    )
  }

  const start = startText(quest)
  const notOn = notOnLine(quest)

  return (
    <button
      type="button"
      className="hero-plan"
      aria-label={cardLabel(quest, today, { withAudience: false, withStart: true })}
      onClick={() => onOpen(quest)}
    >
      <span className="hero-plan-photo">
        <QuestPhoto quest={quest} eager />
        <span className="curated-quest-occasion-badge">
          {OCCASION_LABELS[quest.occasion]}
        </span>
        {notOn && <span className="hero-plan-days">{notOn}</span>}
      </span>
      <span className="hero-plan-body">
        <span className="hero-plan-kicker">
          Ready to go{start && ` · starts ${start}`}
        </span>
        <span className="hero-plan-title">{quest.title}</span>
        <StopList quest={quest} />
        <span className="hero-plan-foot">
          <span className="hero-plan-facts">
            {durationText(quest.total_duration_minutes)} · {costText(quest)}
          </span>
          <span className="hero-plan-open">
            See the plan <span aria-hidden>→</span>
          </span>
        </span>
      </span>
    </button>
  )
}
