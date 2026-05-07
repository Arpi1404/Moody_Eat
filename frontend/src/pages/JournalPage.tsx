import { Link, useNavigate } from 'react-router-dom'
import { useJournal } from '../hooks/useJournal'
import type { JournalEntry } from '../types/journal'
import type { Quest } from '../types/quest'
import '../App.css'

const RATING_FACES = ['😞', '😕', '🙂', '😄', '🤩']

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

function formatJournalDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
  })
}

function JournalCard({ entry }: { entry: JournalEntry }) {
  const navigate = useNavigate()
  const quest = readQuest(entry.questId)
  const ratingFace = RATING_FACES[entry.rating - 1] ?? '🙂'

  const openQuest = () => {
    if (quest) {
      navigate(`/quest/${quest.id}`, { state: { quest } })
      return
    }
    navigate(`/quest/${entry.questId}`)
  }

  return (
    <button type="button" className="journal-card" onClick={openQuest}>
      <div className="journal-card-main">
        <div>
          <p className="journal-card-title">{quest?.title ?? 'Completed quest'}</p>
          <p className="journal-card-date">{formatJournalDate(entry.completedAt)}</p>
        </div>
        <span className="journal-card-rating" aria-label={`Rating ${entry.rating} out of 5`}>
          {ratingFace}
        </span>
      </div>
      {entry.note && <p className="journal-card-note">{entry.note}</p>}
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
  const sortedEntries = [...entries].sort(
    (a, b) =>
      new Date(b.completedAt).getTime() - new Date(a.completedAt).getTime(),
  )

  return (
    <main className="journal-page">
      <header className="journal-header">
        <p className="saved-back">
          <Link to="/">← Home</Link>
        </p>
        <h1 className="journal-title">Journal</h1>
        <p className="journal-sub">
          {sortedEntries.length === 0
            ? 'Completed quests will become memories here.'
            : `${sortedEntries.length} memor${sortedEntries.length === 1 ? 'y' : 'ies'}`}
        </p>
      </header>

      {sortedEntries.length === 0 ? (
        <div className="saved-empty">
          <span className="saved-empty-emoji" aria-hidden>
            ✍️
          </span>
          <p className="saved-empty-title">No memories yet</p>
          <p className="saved-empty-body">
            Start a quest, mark it done, and save a rating to build your journal.
          </p>
          <Link to="/" className="saved-empty-cta">
            Find a quest
          </Link>
        </div>
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
