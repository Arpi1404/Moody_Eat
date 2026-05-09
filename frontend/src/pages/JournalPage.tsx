import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useJournal } from '../hooks/useJournal'
import { EmptyState, LoadingState } from '../components/states'
import type { JournalEntry } from '../types/journal'
import type { Quest } from '../types/quest'
import { JournalSheet } from './JournalSheet'
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

function JournalCard({
  entry,
  onEdit,
  onDelete,
}: {
  entry: JournalEntry
  onEdit: (entry: JournalEntry) => void
  onDelete: (entry: JournalEntry) => void
}) {
  const navigate = useNavigate()
  const quest = readQuest(entry.questId)
  const date = formatJournalDay(entry.completedAt)
  const occasionLabel = quest ? OCCASION_LABELS[quest.occasion] ?? null : null
  const ratingLabel = RATING_LABELS[entry.rating - 1] ?? RATING_LABELS[2]

  const openQuest = () => {
    const navState = { from: '/journal', fromLabel: 'Journal' }
    if (quest) {
      navigate(`/quest/${quest.id}`, { state: { quest, ...navState } })
      return
    }
    navigate(`/quest/${entry.questId}`, { state: navState })
  }

  return (
    <article className="journal-card">
      <div className="journal-card-toolbar">
        <button
          type="button"
          className="journal-card-tool-btn"
          aria-label="Edit memory"
          onClick={() => onEdit(entry)}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M4 20h4l10-10-4-4L4 16v4z M14 6l4 4"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span>Edit</span>
        </button>
        <button
          type="button"
          className="journal-card-tool-btn journal-card-tool-btn--danger"
          aria-label="Delete memory"
          onClick={() => onDelete(entry)}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M9 4h6m-9 3h12m-1 0-1 13a2 2 0 01-2 2H9a2 2 0 01-2-2L6 7m4 4v6m4-6v6"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>

      <button
        type="button"
        className="journal-card-body-btn"
        onClick={openQuest}
        aria-label={`Open ${quest?.title ?? 'quest'}`}
      >
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

        <div className="journal-card-note-slot">
          {entry.note ? (
            <blockquote className="journal-card-note">
              <span className="journal-card-quote-mark" aria-hidden>
                “
              </span>
              {entry.note}
            </blockquote>
          ) : (
            <p className="journal-card-note journal-card-note--empty">
              <span className="journal-card-quote-mark" aria-hidden>
                “
              </span>
              No note yet — tap edit to add one.
            </p>
          )}
        </div>

        <div className="journal-thumb-row">
          {entry.photos.length > 0 ? (
            entry.photos
              .slice(0, 4)
              .map((photo, index) => (
                <img key={`${entry.completedAt}-${index}`} src={photo} alt="" />
              ))
          ) : (
            <div
              className="journal-thumb-empty"
              aria-label="No photos saved for this memory"
            >
              <span aria-hidden>📷</span>
              <span>No photos yet</span>
            </div>
          )}
        </div>
      </button>
    </article>
  )
}

export function JournalPage() {
  const { entries, updateEntry, removeEntry } = useJournal()
  const [loading, setLoading] = useState(true)
  const [editingEntry, setEditingEntry] = useState<JournalEntry | null>(null)
  const [pendingDelete, setPendingDelete] = useState<JournalEntry | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<number | null>(null)
  const sortedEntries = [...entries].sort(
    (a, b) =>
      new Date(b.completedAt).getTime() - new Date(a.completedAt).getTime(),
  )

  useEffect(() => {
    const loadingTimer = window.setTimeout(() => setLoading(false), 200)
    return () => {
      window.clearTimeout(loadingTimer)
      if (toastTimer.current) window.clearTimeout(toastTimer.current)
    }
  }, [])

  const showToast = (message: string) => {
    setToast(message)
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 2400)
  }

  const editingQuest = editingEntry ? readQuest(editingEntry.questId) : null

  const handleEditSave = (next: JournalEntry) => {
    if (!editingEntry) return
    const ok = updateEntry(editingEntry.questId, editingEntry.completedAt, {
      rating: next.rating,
      photos: next.photos,
      note: next.note,
    })
    setEditingEntry(null)
    showToast(ok ? 'Memory updated.' : 'Could not save changes.')
  }

  const handleDelete = (entry: JournalEntry) => {
    removeEntry(entry.questId, entry.completedAt)
    setPendingDelete(null)
    showToast('Memory removed.')
  }

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
              onEdit={setEditingEntry}
              onDelete={setPendingDelete}
            />
          ))}
        </div>
      )}

      {editingEntry && editingQuest && (
        <JournalSheet
          quest={editingQuest}
          mode="edit"
          initialEntry={editingEntry}
          onSave={handleEditSave}
          onCancel={() => setEditingEntry(null)}
          onDelete={() => {
            setPendingDelete(editingEntry)
            setEditingEntry(null)
          }}
        />
      )}

      {editingEntry && !editingQuest && (
        <div className="journal-sheet-overlay" role="presentation">
          <button
            type="button"
            className="journal-sheet-backdrop"
            aria-label="Close"
            onClick={() => setEditingEntry(null)}
          />
          <section
            className="journal-sheet"
            role="dialog"
            aria-modal="true"
          >
            <div className="journal-sheet-handle" aria-hidden />
            <header className="journal-sheet-header">
              <p className="journal-sheet-eyebrow">Edit memory</p>
              <h2>Quest details unavailable</h2>
              <p>
                The original quest for this memory is no longer available, so it
                cannot be edited. You can still remove it.
              </p>
            </header>
            <button
              type="button"
              className="journal-delete-btn"
              onClick={() => {
                setPendingDelete(editingEntry)
                setEditingEntry(null)
              }}
            >
              Delete memory
            </button>
            <button
              type="button"
              className="journal-cancel-btn"
              onClick={() => setEditingEntry(null)}
            >
              Close
            </button>
          </section>
        </div>
      )}

      {pendingDelete && (
        <div className="journal-confirm-overlay" role="presentation">
          <button
            type="button"
            className="journal-sheet-backdrop"
            aria-label="Cancel delete"
            onClick={() => setPendingDelete(null)}
          />
          <div
            className="journal-confirm"
            role="alertdialog"
            aria-label="Confirm delete"
          >
            <p className="journal-confirm-title">Remove this memory?</p>
            <p className="journal-confirm-text">
              This will erase your rating, note, and photos. The quest itself
              stays put.
            </p>
            <div className="journal-confirm-actions">
              <button
                type="button"
                className="journal-confirm-btn journal-confirm-btn--cancel"
                onClick={() => setPendingDelete(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="journal-confirm-btn journal-confirm-btn--delete"
                onClick={() => handleDelete(pendingDelete)}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className="saved-toast" role="status" aria-live="polite">
          {toast}
        </div>
      )}
    </main>
  )
}

export default JournalPage
