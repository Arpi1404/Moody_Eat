import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import 'leaflet/dist/leaflet.css'
import type { Quest } from '../types/quest'
import { useSavedQuests } from '../hooks/useSavedQuests'
import { QuestCard } from './QuestCard'
import '../App.css'

const BUDGET_LABELS: Record<string, string> = {
  cheap: '$ Budget',
  mid: '$$ Mid',
  splurge: '$$$ Splurge',
}

// ── QuestPage ─────────────────────────────────────────────────────────────────

export function QuestPage({ preview = false }: { preview?: boolean }) {
  const { id } = useParams<{ id: string }>()
  const { state } = useLocation() as { state: { quest?: Quest } | null }
  const { saveQuest, isQuestSaved } = useSavedQuests()
  const [quest, setQuest] = useState<Quest | null>(null)
  const [title, setTitle] = useState('')
  const [justSaved, setJustSaved] = useState(false)
  const [started, setStarted] = useState(false)

  const savedToCollection = quest ? isQuestSaved(quest.id) : false

  useEffect(() => {
    if (state?.quest) {
      setQuest(state.quest)
      setTitle(state.quest.title)
      return
    }
    if (!id) return
    const raw =
      localStorage.getItem(`quest_${id}`) ?? sessionStorage.getItem(`quest_${id}`)
    if (raw) {
      const q = JSON.parse(raw) as Quest
      setQuest(q)
      setTitle(q.title)
    }
  }, [id, state])

  if (!quest) {
    return (
      <main className="hello-page">
        <div className="hello-card" style={{ textAlign: 'center' }}>
          <p className="hello-label">Quest</p>
          <p className="hello-subtitle">Quest not found — it may have expired.</p>
          <Link to="/" className="explore-home-link">
            ← Back home
          </Link>
        </div>
      </main>
    )
  }

  const durationHours = quest.total_duration_minutes / 60
  const durationLabel = Number.isInteger(durationHours)
    ? `${durationHours}h`
    : `${durationHours.toFixed(1)}h`

  const handleSave = () => {
    const titledQuest = { ...quest, title }
    saveQuest(titledQuest)
    localStorage.setItem(`quest_${titledQuest.id}`, JSON.stringify(titledQuest))
    setJustSaved(true)
    setTimeout(() => setJustSaved(false), 2000)
  }

  const handleQuestChange = (nextQuest: Quest) => {
    const titledQuest = { ...nextQuest, title }
    setQuest(titledQuest)
    localStorage.setItem(`quest_${titledQuest.id}`, JSON.stringify(titledQuest))
    if (isQuestSaved(titledQuest.id)) {
      saveQuest(titledQuest)
    }
  }

  const handleShare = async () => {
    const url = window.location.href
    if (navigator.share) {
      try {
        await navigator.share({ title, url })
        return
      } catch {
        // fall through to clipboard
      }
    }
    try {
      await navigator.clipboard.writeText(url)
    } catch {
      // ignore
    }
  }

  const handleStart = () => {
    localStorage.setItem(
      'moodyeat:activeQuest',
      JSON.stringify({ ...quest, title, started_at: new Date().toISOString() }),
    )
    setStarted(true)
  }

  return (
    <main className="qp-page">
      <div className="qp-inner">
        <p className="qp-back">
          <Link to="/">← Home</Link>
        </p>

        <header className="qp-header">
          <input
            className="qp-title-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            aria-label="Quest title"
            maxLength={80}
          />
          <div className="qp-header-chips">
            <span className="qp-chip">{durationLabel}</span>
            <span className="qp-chip">
              {BUDGET_LABELS[quest.total_cost_estimate] ?? quest.total_cost_estimate}
            </span>
            <span className="qp-chip qp-chip--occasion">{quest.occasion}</span>
          </div>
        </header>

        {quest.narrative && <p className="qp-narrative">{quest.narrative}</p>}

        <QuestCard
          quest={quest}
          onQuestChange={handleQuestChange}
          readOnly={preview && !savedToCollection}
        />

        <div className="qp-bottom-bar">
          <button
            type="button"
            className={`qp-action-btn qp-action-btn--save${savedToCollection ? ' qp-action-btn--saved' : ''}`}
            onClick={handleSave}
          >
            {justSaved
              ? '✓ Saved'
              : savedToCollection
                ? 'Saved ✓'
                : 'Save'}
          </button>
          <button
            type="button"
            className="qp-action-btn qp-action-btn--share"
            onClick={handleShare}
          >
            ↑ Share
          </button>
          <button
            type="button"
            className="qp-action-btn qp-action-btn--start"
            onClick={handleStart}
          >
            {started ? '✓ Started' : '▶ Start'}
          </button>
        </div>
      </div>
    </main>
  )
}
