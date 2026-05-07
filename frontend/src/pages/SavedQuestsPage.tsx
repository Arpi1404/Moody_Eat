import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useSavedQuests, type SavedQuest } from '../hooks/useSavedQuests'
import '../App.css'

const OCCASION_ICONS: Record<string, string> = {
  date: '🌹',
  friends: '🎉',
  solo: '🎧',
  family: '👨‍👩‍👧',
}

const LONG_PRESS_MS = 550

function formatSavedDate(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return ''
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: d.getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
    })
  } catch {
    return ''
  }
}

export function SavedQuestsPage() {
  const navigate = useNavigate()
  const { savedQuests, removeQuest } = useSavedQuests()
  const [toast, setToast] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const longPressTimer = useRef<number | null>(null)
  const longPressFired = useRef(false)
  const toastTimer = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (longPressTimer.current) window.clearTimeout(longPressTimer.current)
      if (toastTimer.current) window.clearTimeout(toastTimer.current)
    }
  }, [])

  const showToast = useCallback((message: string) => {
    setToast(message)
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 2400)
  }, [])

  const openQuest = useCallback(
    (quest: SavedQuest) => {
      if (longPressFired.current) {
        longPressFired.current = false
        return
      }
      localStorage.setItem(`quest_${quest.id}`, JSON.stringify(quest))
      navigate(`/quest/${quest.id}`, { state: { quest } })
    },
    [navigate],
  )

  const handlePressStart = useCallback((id: string) => {
    longPressFired.current = false
    if (longPressTimer.current) window.clearTimeout(longPressTimer.current)
    longPressTimer.current = window.setTimeout(() => {
      longPressFired.current = true
      setPendingDelete(id)
    }, LONG_PRESS_MS)
  }, [])

  const handlePressEnd = useCallback(() => {
    if (longPressTimer.current) {
      window.clearTimeout(longPressTimer.current)
      longPressTimer.current = null
    }
  }, [])

  const confirmDelete = useCallback(
    (id: string, title: string) => {
      removeQuest(id)
      setPendingDelete(null)
      showToast(`Removed "${title}"`)
    },
    [removeQuest, showToast],
  )

  return (
    <main className="saved-page">
      <header className="saved-header">
        <p className="saved-back">
          <Link to="/">← Home</Link>
        </p>
        <h1 className="saved-title">My quests</h1>
        <p className="saved-sub">
          {savedQuests.length === 0
            ? 'Quests you save will appear here.'
            : `${savedQuests.length} saved`}
        </p>
      </header>

      {savedQuests.length === 0 ? (
        <div className="saved-empty">
          <span className="saved-empty-emoji" aria-hidden>
            ✨
          </span>
          <p className="saved-empty-title">Nothing saved yet</p>
          <p className="saved-empty-body">
            Generate a quest from the home page and tap <strong>Save</strong> to keep it here.
          </p>
          <Link to="/" className="saved-empty-cta">
            Plan a quest
          </Link>
        </div>
      ) : (
        <ul className="saved-list">
          {savedQuests.map((quest) => {
            const stopCount = quest.stops.length
            const occasionIcon = OCCASION_ICONS[quest.occasion] ?? '✨'
            const isPending = pendingDelete === quest.id
            return (
              <li key={quest.id} className="saved-card-wrap">
                <button
                  type="button"
                  className={`saved-card${isPending ? ' saved-card--pending' : ''}`}
                  onClick={() => openQuest(quest)}
                  onMouseDown={() => handlePressStart(quest.id)}
                  onMouseUp={handlePressEnd}
                  onMouseLeave={handlePressEnd}
                  onTouchStart={() => handlePressStart(quest.id)}
                  onTouchEnd={handlePressEnd}
                  onTouchCancel={handlePressEnd}
                >
                  <span className="saved-card-icon" aria-hidden>
                    {occasionIcon}
                  </span>
                  <div className="saved-card-body">
                    <p className="saved-card-title">{quest.title}</p>
                    <p className="saved-card-meta">
                      <span>
                        {stopCount} stop{stopCount === 1 ? '' : 's'}
                      </span>
                      <span aria-hidden>·</span>
                      <span>Saved {formatSavedDate(quest.saved_at)}</span>
                    </p>
                  </div>
                </button>
                <button
                  type="button"
                  className="saved-card-delete"
                  aria-label={`Delete ${quest.title}`}
                  onClick={() => setPendingDelete(quest.id)}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden>
                    <path
                      d="M9 4h6m-9 3h12m-1 0-1 13a2 2 0 01-2 2H9a2 2 0 01-2-2L6 7m4 4v6m4-6v6"
                      stroke="currentColor"
                      strokeWidth="1.7"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      fill="none"
                    />
                  </svg>
                </button>

                {isPending && (
                  <div className="saved-confirm" role="alertdialog" aria-label="Confirm delete">
                    <p className="saved-confirm-text">Remove this quest?</p>
                    <div className="saved-confirm-actions">
                      <button
                        type="button"
                        className="saved-confirm-btn saved-confirm-btn--cancel"
                        onClick={() => setPendingDelete(null)}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        className="saved-confirm-btn saved-confirm-btn--delete"
                        onClick={() => confirmDelete(quest.id, quest.title)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {toast && (
        <div className="saved-toast" role="status" aria-live="polite">
          {toast}
        </div>
      )}
    </main>
  )
}

export default SavedQuestsPage
