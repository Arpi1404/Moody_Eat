import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import 'leaflet/dist/leaflet.css'
import type { Quest } from '../types/quest'
import { QuestCard } from './QuestCard'
import '../App.css'

const BUDGET_LABELS: Record<string, string> = {
  cheap: '$ Budget',
  mid: '$$ Mid',
  splurge: '$$$ Splurge',
}

// ── QuestPage ─────────────────────────────────────────────────────────────────

export function QuestPage() {
  const { id } = useParams<{ id: string }>()
  const { state } = useLocation() as { state: { quest?: Quest } | null }
  const [quest, setQuest] = useState<Quest | null>(null)
  const [title, setTitle] = useState('')
  const [saved, setSaved] = useState(false)

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
    const key = 'moodyeat:quests'
    const existing: Quest[] = JSON.parse(localStorage.getItem(key) ?? '[]')
    const updated = [{ ...quest, title }, ...existing.filter((q) => q.id !== quest.id)]
    localStorage.setItem(key, JSON.stringify(updated))
    localStorage.setItem(`quest_${quest.id}`, JSON.stringify({ ...quest, title }))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleQuestChange = (nextQuest: Quest) => {
    const titledQuest = { ...nextQuest, title }
    setQuest(titledQuest)
    localStorage.setItem(`quest_${titledQuest.id}`, JSON.stringify(titledQuest))

    const key = 'moodyeat:quests'
    const existing = JSON.parse(localStorage.getItem(key) ?? '[]') as Quest[]
    if (existing.some((q) => q.id === titledQuest.id)) {
      localStorage.setItem(
        key,
        JSON.stringify(
          existing.map((q) => (q.id === titledQuest.id ? titledQuest : q)),
        ),
      )
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

        <QuestCard quest={quest} onQuestChange={handleQuestChange} />

        <div className="qp-bottom-bar">
          <button
            type="button"
            className={`qp-action-btn qp-action-btn--save${saved ? ' qp-action-btn--saved' : ''}`}
            onClick={handleSave}
          >
            {saved ? '✓ Saved' : '♡ Save'}
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
            disabled
            title="Coming soon"
          >
            ▶ Start
          </button>
        </div>
      </div>
    </main>
  )
}
