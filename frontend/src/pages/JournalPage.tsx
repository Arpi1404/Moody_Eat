import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useJournal } from '../hooks/useJournal'
import { EmptyState, LoadingState } from '../components/states'
import type { JournalEntry } from '../types/journal'
import type { Quest } from '../types/quest'
import '../App.css'

const RATING_LABELS = ['Rough', 'Meh', 'Nice', 'Loved it', 'Unforgettable']

const OCCASION_LABELS: Record<string, string> = {
  date: 'Date Night',
  friends: 'Friends',
  solo: 'Solo Time',
  family: 'Family',
}

function readQuest(questId: string): Quest | null {
  try {
    const raw = localStorage.getItem(`quest_${questId}`)
    if (!raw) return null
    const value = JSON.parse(raw) as Quest
    if (typeof value.id !== 'string' || !Array.isArray(value.stops)) return null
    return value
  } catch {
    return null
  }
}

function formatJournalDay(iso: string): { day: string; month: string; year: string } {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return { day: '—', month: '', year: '' }
  return {
    day: String(date.getDate()),
    month: date.toLocaleDateString(undefined, { month: 'short' }).toUpperCase(),
    year: String(date.getFullYear()),
  }
}

function StarRating({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(5, Math.round(value)))
  return (
    <span className="journal-card-stars" aria-label={`Rating ${clamped} out of 5`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <svg
          key={i}
          width="14"
          height="14"
          viewBox="0 0 24 24"
          aria-hidden
          className={`journal-card-star${i < clamped ? ' journal-card-star--on' : ''}`}
        >
          <path
            d="M12 3.5l2.7 5.5 6 .9-4.4 4.3 1.1 6.1L12 17.4l-5.4 2.9 1.1-6.1L3.3 9.9l6-.9z"
            fill="currentColor"
          />
        </svg>
      ))}
    </span>
  )
}

function JournalCard({ entry }: { entry: JournalEntry }) {
  const navigate = useNavigate()
  const quest = readQuest(entry.questId)
  const date = formatJournalDay(entry.completedAt)
  const occasionLabel = quest ? OCCASION_LABELS[quest.occasion] ?? null : null
  const ratingLabel = RATING_LABELS[entry.rating - 1] ?? RATING_LABELS[2]

  const openQuest = () => {
    if (quest) {
      navigate(`/quest/${quest.id}`, { state: { quest } })
      return
    }
    navigate(`/quest/${entry.questId}`)
  }

  return (
    <button type="button" className="journal-card" onClick={openQuest}>
      <header className="journal-card-header">
        <div className="journal-card-date">
          <span className="journal-card-date-day">{date.day}</span>
          <span className="journal-card-date-month">{date.month}</span>
          <span className="journal-card-date-year">{date.year}</span>
        </div>
        <div className="journal-card-meta">
          {occasionLabel && (
            <span className="journal-card-occasion">{occasionLabel}</span>
          )}
          <StarRating value={entry.rating} />
          <span className="journal-card-rating-label">{ratingLabel}</span>
        </div>
      </header>

      <h3 className="journal-card-title">{quest?.title ?? 'Completed quest'}</h3>

      {entry.note && (
        <blockquote className="journal-card-note">
          <span className="journal-card-quote-mark" aria-hidden>
            “
          </span>
          {entry.note}
        </blockquote>
      )}

      {entry.photos.length > 0 && (
        <div className="journal-thumb-row">
          {entry.photos.slice(0, 4).map((photo, index) => (
            <img key={`${entry.completedAt}-${index}`} src={photo} alt="" />
          ))}
        </div>
      )}
    </button>
  )
}

export function JournalPage() {
  const { entries } = useJournal()
  const [loading, setLoading] = useState(true)
  const sortedEntries = [...entries].sort(
    (a, b) =>
      new Date(b.completedAt).getTime() - new Date(a.completedAt).getTime(),
  )

  useEffect(() => {
    const loadingTimer = window.setTimeout(() => setLoading(false), 200)
    return () => window.clearTimeout(loadingTimer)
  }, [])

  return (
    <main className="journal-page">
      <header className="journal-header">
        <h1 className="journal-title">Journal</h1>
        <p className="journal-sub">
          {sortedEntries.length === 0
            ? 'Completed quests will become memories here.'
            : `${sortedEntries.length} memor${sortedEntries.length === 1 ? 'y' : 'ies'}`}
        </p>
      </header>

      {loading ? (
        <LoadingState message="Loading memories..." />
      ) : sortedEntries.length === 0 ? (
        <EmptyState
          icon="✍️"
          title="Start a quest to begin building your memories"
          description="Complete a quest and save a rating to add your first journal entry."
          cta={<Link to="/">Find a quest</Link>}
        />
      ) : (
        <div className="journal-list">
          {sortedEntries.map((entry) => (
            <JournalCard
              key={`${entry.questId}-${entry.completedAt}`}
              entry={entry}
            />
          ))}
        </div>
      )}
    </main>
  )
}

export default JournalPage
