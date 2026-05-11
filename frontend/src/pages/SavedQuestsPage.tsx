import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getApiBase } from '../api'
import { useSavedQuests, type SavedQuest } from '../hooks/useSavedQuests'
import { EmptyState, LoadingState } from '../components/states'
import { track } from '../lib/analytics'
import '../App.css'

const OCCASION_ICONS: Record<string, string> = {
  date: '🕯️',
  friends: '🥂',
  solo: '🍵',
  family: '🧆',
}

const OCCASION_LABELS: Record<string, string> = {
  date: 'Date Night',
  friends: 'Friends',
  solo: 'Solo Time',
  family: 'Family',
}

function formatTotalDuration(minutes: number | undefined): string | null {
  if (!minutes || !Number.isFinite(minutes)) return null
  const hours = minutes / 60
  if (hours >= 1) {
    return Number.isInteger(hours) ? `${hours}h` : `${hours.toFixed(1)}h`
  }
  return `${Math.round(minutes)}m`
}

function costLabel(cost: SavedQuest['total_cost_estimate']): string | null {
  if (cost === 'cheap') return '₹ Light'
  if (cost === 'splurge') return '₹₹₹ Splurge'
  if (cost === 'mid') return '₹₹ Easy'
  return null
}

function SavedCardImage({ quest }: { quest: SavedQuest }) {
  const [failed, setFailed] = useState(false)
  const firstStop = quest.stops[0]
  const placeId = firstStop?.place.provider_id
  const src = placeId
    ? `${getApiBase()}/api/places/photo?place_id=${encodeURIComponent(placeId)}&max_width=600`
    : ''
  const occIcon = OCCASION_ICONS[quest.occasion] ?? '✦'

  if (!src || failed) {
    return (
      <div className="saved-card-image saved-card-image--fallback" aria-hidden>
        <span>{occIcon}</span>
      </div>
    )
  }

  return (
    <div className="saved-card-image">
      <img
        src={src}
        alt={firstStop?.place.name ?? quest.title}
        onError={() => setFailed(true)}
      />
    </div>
  )
}

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
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const toastTimer = useRef<number | null>(null)

  useEffect(() => {
    const loadingTimer = window.setTimeout(() => setLoading(false), 200)
    return () => {
      window.clearTimeout(loadingTimer)
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
      localStorage.setItem(`quest_${quest.id}`, JSON.stringify(quest))
      navigate(`/quest/${quest.id}`, {
        state: { quest, from: '/saved', fromLabel: 'Saved' },
      })
    },
    [navigate],
  )

  const confirmDelete = useCallback(
    (id: string, title: string) => {
      removeQuest(id)
      track('quest_unsaved', { quest_id: id })
      setPendingDelete(null)
      showToast(`Removed "${title}"`)
    },
    [removeQuest, showToast],
  )

  return (
    <main className="saved-page">
      <header className="saved-header">
        <h1 className="saved-title">My quests</h1>
        <p className="saved-sub">
          {savedQuests.length === 0
            ? 'Quests you save will appear here.'
            : `${savedQuests.length} saved`}
        </p>
      </header>

      {loading ? (
        <LoadingState message="Loading saved quests..." />
      ) : savedQuests.length === 0 ? (
        <EmptyState
          icon="✨"
          title="Save your first quest to see it here"
          description="Generate or open a curated quest, then tap Save to keep it handy."
          cta={<Link to="/">Plan a quest</Link>}
        />
      ) : (
        <ul className="saved-list">
          {savedQuests.map((quest) => {
            const stopCount = quest.stops.length
            const occasionIcon = OCCASION_ICONS[quest.occasion] ?? '✦'
            const occasionLabel = OCCASION_LABELS[quest.occasion] ?? 'Quest'
            const isPending = pendingDelete === quest.id
            const duration = formatTotalDuration(quest.total_duration_minutes)
            const cost = costLabel(quest.total_cost_estimate)
            return (
              <li key={quest.id} className="saved-card-wrap">
                <button
                  type="button"
                  className={`saved-card${isPending ? ' saved-card--pending' : ''}`}
                  onClick={() => openQuest(quest)}
                >
                  <SavedCardImage quest={quest} />
                  <div className="saved-card-body">
                    <span className="saved-card-eyebrow">
                      <span className="saved-card-eyebrow-emoji" aria-hidden>
                        {occasionIcon}
                      </span>
                      {occasionLabel}
                    </span>
                    <p className="saved-card-title">{quest.title}</p>
                    <div className="saved-card-chips">
                      {duration && (
                        <span className="chip chip--accent">{duration}</span>
                      )}
                      {cost && <span className="chip chip--gold">{cost}</span>}
                      <span className="chip chip--sage">
                        {stopCount} stop{stopCount === 1 ? '' : 's'}
                      </span>
                    </div>
                    <span className="saved-card-trail" aria-hidden>
                      {Array.from({ length: Math.min(stopCount, 5) }).map((_, i) => (
                        <span
                          key={i}
                          className={`saved-card-dot${i === 0 ? ' saved-card-dot--first' : ''}`}
                        />
                      ))}
                    </span>
                    <p className="saved-card-saved">
                      Saved {formatSavedDate(quest.saved_at)}
                    </p>
                  </div>
                </button>
                <button
                  type="button"
                  className="saved-card-delete"
                  aria-label={`Remove ${quest.title}`}
                  onClick={() => setPendingDelete(quest.id)}
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
                    <path
                      d="M2.5 2.5l7 7m0-7l-7 7"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      strokeLinecap="round"
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
