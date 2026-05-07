import { useCallback, useEffect, useRef, useState } from 'react'
import { toPng } from 'html-to-image'
import { Link, useLocation, useParams } from 'react-router-dom'
import 'leaflet/dist/leaflet.css'
import type { Quest } from '../types/quest'
import { useSavedQuests } from '../hooks/useSavedQuests'
import { QuestCard } from './QuestCard'
import { ShareableQuestCard } from './ShareableQuestCard'
import '../App.css'

const BUDGET_LABELS: Record<string, string> = {
  cheap: '$ Budget',
  mid: '$$ Mid',
  splurge: '$$$ Splurge',
}

const SHARE_BASE_URL = 'https://moodyeat.app'

function makeQuestShareUrl(quest: Quest): string {
  return `${SHARE_BASE_URL}/quest/${quest.id}`
}

function makePngFileName(title: string): string {
  const slug = title
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
    .slice(0, 48)

  return `moodyeat-${slug || 'quest'}.png`
}

function makeQuestTextSummary(quest: Quest, url: string): string {
  const stops = quest.stops
    .map((stop, index) => `${index + 1}. ${stop.place.name} - ${stop.why_this_place}`)
    .join('\n')

  return `${quest.title}\n${quest.occasion} quest · ${quest.total_duration_minutes} min\n\n${stops}\n\nPlan yours at ${url}`
}

function nextPaint(): Promise<void> {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => resolve())
    })
  })
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

async function waitForShareCardAssets(node: HTMLElement): Promise<void> {
  await document.fonts.ready.catch(() => undefined)

  const images = Array.from(node.querySelectorAll('img'))
  await Promise.all(
    images.map(async (image) => {
      if (image.complete && image.naturalWidth > 0) return
      await Promise.race([image.decode().catch(() => undefined), wait(1700)])
    }),
  )

  await nextPaint()
}

function downloadPng(dataUrl: string, fileName: string) {
  const anchor = document.createElement('a')
  anchor.href = dataUrl
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

async function copyToClipboard(text: string): Promise<void> {
  if (!navigator.clipboard?.writeText) return

  const timeout = new Promise<void>((resolve) => {
    window.setTimeout(resolve, 800)
  })

  await Promise.race([
    navigator.clipboard.writeText(text).catch(() => undefined),
    timeout,
  ])
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
  const [sharing, setSharing] = useState(false)
  const [shareMenuOpen, setShareMenuOpen] = useState(false)
  const [showShareCard, setShowShareCard] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const shareCardRef = useRef<HTMLDivElement | null>(null)
  const toastTimer = useRef<number | null>(null)

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

  useEffect(() => {
    return () => {
      if (toastTimer.current) window.clearTimeout(toastTimer.current)
    }
  }, [])

  const showToast = useCallback((message: string) => {
    setToast(message)
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 2600)
  }, [])

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

  const handleShare = () => {
    if (sharing) return
    setShareMenuOpen(true)
  }

  const handleCopyShareLink = async () => {
    const titledQuest = { ...quest, title: title.trim() || quest.title }
    await copyToClipboard(makeQuestShareUrl(titledQuest))
    setShareMenuOpen(false)
    showToast('Share link copied.')
  }

  const handleDownloadShareImage = async () => {
    if (sharing) return

    const titledQuest = { ...quest, title: title.trim() || quest.title }
    const shareUrl = makeQuestShareUrl(titledQuest)
    setSharing(true)
    setShowShareCard(true)

    try {
      await nextPaint()

      const node = shareCardRef.current
      if (!node) throw new Error('Share card was not ready.')

      await waitForShareCardAssets(node)

      const dataUrl = await toPng(node, {
        backgroundColor: '#0b1120',
        cacheBust: true,
        fontEmbedCSS: '',
        pixelRatio: 1,
        skipFonts: true,
        width: 1080,
        height: 1920,
      })
      const fileName = makePngFileName(titledQuest.title)
      setShowShareCard(false)

      downloadPng(dataUrl, fileName)
      setShareMenuOpen(false)
      showToast('PNG downloaded.')
    } catch {
      await copyToClipboard(makeQuestTextSummary(titledQuest, shareUrl))
      setShareMenuOpen(false)
      showToast("Couldn't make image — copied details instead.")
    } finally {
      setShowShareCard(false)
      setSharing(false)
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
            disabled={sharing}
            aria-busy={sharing}
          >
            {sharing ? (
              <>
                <span className="qp-action-spinner" aria-hidden />
                Sharing...
              </>
            ) : (
              '↑ Share'
            )}
          </button>
          <button
            type="button"
            className="qp-action-btn qp-action-btn--start"
            onClick={handleStart}
          >
            {started ? '✓ Started' : '▶ Start'}
          </button>
        </div>

        {shareMenuOpen && (
          <div className="qp-share-overlay" role="presentation">
            <button
              type="button"
              className="qp-share-backdrop"
              aria-label="Close share options"
              onClick={() => {
                if (!sharing) setShareMenuOpen(false)
              }}
            />
            <section
              className="qp-share-sheet"
              role="dialog"
              aria-modal="true"
              aria-labelledby="qp-share-title"
            >
              <div className="qp-share-sheet-handle" aria-hidden />
              <div className="qp-share-sheet-header">
                <p className="qp-share-eyebrow">Share quest</p>
                <h2 id="qp-share-title">Choose what to send</h2>
                <p>
                  Download the story card as a PNG, or copy the quest link to
                  paste anywhere.
                </p>
              </div>
              <div className="qp-share-actions">
                <button
                  type="button"
                  className="qp-share-option"
                  onClick={handleDownloadShareImage}
                  disabled={sharing}
                >
                  <span className="qp-share-option-icon" aria-hidden>
                    PNG
                  </span>
                  <span>
                    <span className="qp-share-option-title">
                      {sharing ? 'Making PNG...' : 'Download PNG'}
                    </span>
                    <span className="qp-share-option-subtitle">
                      Save the Instagram-story card.
                    </span>
                  </span>
                  {sharing && <span className="qp-action-spinner" aria-hidden />}
                </button>
                <button
                  type="button"
                  className="qp-share-option"
                  onClick={handleCopyShareLink}
                  disabled={sharing}
                >
                  <span className="qp-share-option-icon" aria-hidden>
                    URL
                  </span>
                  <span>
                    <span className="qp-share-option-title">Copy link</span>
                    <span className="qp-share-option-subtitle">
                      Put the quest URL on your clipboard.
                    </span>
                  </span>
                </button>
              </div>
              <button
                type="button"
                className="qp-share-cancel"
                onClick={() => setShareMenuOpen(false)}
                disabled={sharing}
              >
                Cancel
              </button>
            </section>
          </div>
        )}

        {showShareCard && (
          <div className="share-card-stage">
            <ShareableQuestCard
              ref={shareCardRef}
              quest={{ ...quest, title: title.trim() || quest.title }}
            />
          </div>
        )}
      </div>

      {toast && (
        <div className="saved-toast" role="status" aria-live="polite">
          {toast}
        </div>
      )}
    </main>
  )
}
