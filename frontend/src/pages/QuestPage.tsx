import { useCallback, useEffect, useRef, useState } from 'react'
import { toPng } from 'html-to-image'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import 'leaflet/dist/leaflet.css'
import type { Quest, QuestGenerationRequest } from '../types/quest'
import type { JournalEntry } from '../types/journal'
import { generateQuest } from '../api'
import { useSavedQuests } from '../hooks/useSavedQuests'
import { useJournal } from '../hooks/useJournal'
import { ErrorState, LoadingState } from '../components/states'
import { track } from '../lib/analytics'
import { budgetLabel, formatInrEstimate } from '../lib/budget'
import { makeQuestShareUrl, readQuestFromLocationHash } from '../lib/questShare'
import { shareCardFontEmbedCss } from '../lib/shareFonts'
import { JournalSheet } from './JournalSheet'
import { QuestCard } from './QuestCard'
import { ShareableQuestCard } from './ShareableQuestCard'
import '../App.css'

const ACTIVE_QUEST_KEY = 'moodyeat:active_quest'
const LEGACY_ACTIVE_QUEST_KEY = 'moodyeat:activeQuest'

interface ActiveQuest extends Quest {
  started_at: string
  completedStopIndexes?: number[]
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

const OCCASION_PHRASE: Record<string, string> = {
  date: 'date',
  friends: 'friends',
  solo: 'solo',
  family: 'family',
}

function rebuildNarrative(quest: Quest): string {
  const names = quest.stops.map((stop) => stop.place.name)
  const occasion = OCCASION_PHRASE[quest.occasion] ?? quest.occasion
  const intro = `A ${quest.total_cost_estimate} ${occasion} outing`
  if (names.length === 0) return `${intro}.`
  if (names.length === 1) return `${intro}, anchored around ${names[0]}.`
  const mid = names.slice(0, -1).join(', ')
  return `${intro}: starting at ${mid}, then finishing the night at ${names[names.length - 1]}.`
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

function readActiveQuest(): ActiveQuest | null {
  try {
    const raw =
      localStorage.getItem(ACTIVE_QUEST_KEY) ??
      localStorage.getItem(LEGACY_ACTIVE_QUEST_KEY)
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<ActiveQuest>
    if (typeof value.id !== 'string' || !Array.isArray(value.stops)) return null
    return {
      ...(value as Quest),
      started_at:
        typeof value.started_at === 'string'
          ? value.started_at
          : new Date().toISOString(),
      completedStopIndexes: Array.isArray(value.completedStopIndexes)
        ? value.completedStopIndexes.filter((item): item is number => typeof item === 'number')
        : [],
    }
  } catch {
    return null
  }
}

function writeActiveQuest(quest: Quest, completedStopIndexes: number[]) {
  const current = readActiveQuest()
  const started_at =
    current?.id === quest.id ? current.started_at : new Date().toISOString()
  localStorage.setItem(
    ACTIVE_QUEST_KEY,
    JSON.stringify({ ...quest, started_at, completedStopIndexes }),
  )
  localStorage.removeItem(LEGACY_ACTIVE_QUEST_KEY)
}

function clearActiveQuest() {
  localStorage.removeItem(ACTIVE_QUEST_KEY)
  localStorage.removeItem(LEGACY_ACTIVE_QUEST_KEY)
}

// ── QuestPage ─────────────────────────────────────────────────────────────────

export function QuestPage({ preview = false }: { preview?: boolean }) {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { state } = useLocation() as {
    state: {
      quest?: Quest
      softMessage?: string
      justCreated?: boolean
      from?: string
      fromLabel?: string
      /** Present only right after generation — enables "Shuffle". */
      request?: QuestGenerationRequest
    } | null
  }
  const backTo = state?.from ?? '/'
  const backLabel = state?.fromLabel ?? 'Home'
  const { saveQuest, removeQuest, isQuestSaved } = useSavedQuests()
  const { addEntry } = useJournal()
  const [quest, setQuest] = useState<Quest | null>(null)
  const [title, setTitle] = useState('')
  const [questLoading, setQuestLoading] = useState(true)
  const [questError, setQuestError] = useState<string | null>(null)
  const [questNotice, setQuestNotice] = useState<string | null>(null)
  const [justSaved, setJustSaved] = useState(false)
  const [activeQuestId, setActiveQuestId] = useState<string | null>(null)
  const [completedStopIndexes, setCompletedStopIndexes] = useState<number[]>([])
  const [journalOpen, setJournalOpen] = useState(false)
  const [sharing, setSharing] = useState(false)
  const [shareMenuOpen, setShareMenuOpen] = useState(false)
  const [showShareCard, setShowShareCard] = useState(false)
  const [toast, setToast] = useState<{
    message: string
    actionLabel?: string
    onAction?: () => void
  } | null>(null)
  const [createdBanner, setCreatedBanner] = useState(false)
  const [shuffling, setShuffling] = useState(false)
  const [feedbackVote, setFeedbackVote] = useState<'up' | 'down' | null>(null)
  const shareCardRef = useRef<HTMLDivElement | null>(null)
  const toastTimer = useRef<number | null>(null)
  const createdBannerTimer = useRef<number | null>(null)

  const savedToCollection = quest ? isQuestSaved(quest.id) : false
  const active = quest ? activeQuestId === quest.id : false

  useEffect(() => {
    let cancelled = false

    async function loadQuest() {
      setQuestLoading(true)
      setQuestError(null)

      try {
        await wait(200)
        let nextQuest: Quest | null = null
        const softMessage = state?.softMessage ?? null

        if (state?.quest) {
          nextQuest = state.quest
        } else if (id) {
          const raw =
            localStorage.getItem(`quest_${id}`) ??
            sessionStorage.getItem(`quest_${id}`)
          if (raw) nextQuest = JSON.parse(raw) as Quest
        }

        if (!nextQuest) {
          // Share links embed the full quest in the URL fragment — this is
          // how a recipient without any local copy can open it.
          const sharedQuest = await readQuestFromLocationHash()
          if (sharedQuest && (!id || sharedQuest.id === id)) {
            nextQuest = sharedQuest
            localStorage.setItem(`quest_${sharedQuest.id}`, JSON.stringify(sharedQuest))
          }
        }

        if (!nextQuest) {
          throw new Error('Quest not found — it may have expired.')
        }

        // No derived shortfall guess here: with the stops stepper, a 1- or
        // 2-stop quest is a deliberate choice. Only the generator flow (which
        // knows what was requested) passes a softMessage.

        if (!cancelled) {
          setQuest(nextQuest)
          setTitle(nextQuest.title)
          setQuestNotice(softMessage)
        }
      } catch (err) {
        if (!cancelled) {
          setQuest(null)
          setQuestError(
            err instanceof Error
              ? err.message
              : 'Quest not found — it may have expired.',
          )
        }
      } finally {
        if (!cancelled) setQuestLoading(false)
      }
    }

    void loadQuest()
    return () => {
      cancelled = true
    }
  }, [id, state])

  useEffect(() => {
    if (!quest) return
    const activeQuest = readActiveQuest()
    if (activeQuest?.id === quest.id) {
      setActiveQuestId(activeQuest.id)
      setCompletedStopIndexes(activeQuest.completedStopIndexes ?? [])
    } else {
      setActiveQuestId(null)
      setCompletedStopIndexes([])
    }
  }, [quest])

  useEffect(() => {
    return () => {
      if (toastTimer.current) window.clearTimeout(toastTimer.current)
      if (createdBannerTimer.current)
        window.clearTimeout(createdBannerTimer.current)
    }
  }, [])

  useEffect(() => {
    if (!quest || !state?.justCreated) return
    setCreatedBanner(true)
    if (createdBannerTimer.current)
      window.clearTimeout(createdBannerTimer.current)
    createdBannerTimer.current = window.setTimeout(
      () => setCreatedBanner(false),
      5200,
    )
  }, [quest, state?.justCreated])

  useEffect(() => {
    if (!shareMenuOpen) return
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [shareMenuOpen])

  const showToast = useCallback(
    (
      message: string,
      options?: { actionLabel?: string; onAction?: () => void; durationMs?: number },
    ) => {
      setToast({
        message,
        actionLabel: options?.actionLabel,
        onAction: options?.onAction,
      })
      if (toastTimer.current) window.clearTimeout(toastTimer.current)
      toastTimer.current = window.setTimeout(
        () => setToast(null),
        options?.durationMs ?? 2600,
      )
    },
    [],
  )

  if (questLoading) {
    return (
      <main className="qp-page">
        <div className="qp-inner">
          <LoadingState message="Loading quest..." />
        </div>
      </main>
    )
  }

  if (!quest) {
    return (
      <main className="qp-page">
        <div className="qp-inner">
          <ErrorState
            title="Quest unavailable"
            description={questError ?? 'Quest not found — it may have expired.'}
            retryLabel="Back home"
            onRetry={() => navigate('/')}
          />
        </div>
      </main>
    )
  }

  const durationHours = quest.total_duration_minutes / 60
  const durationLabel = Number.isInteger(durationHours)
    ? `${durationHours}h`
    : `${durationHours.toFixed(1)}h`
  const totalEstimateLabel = formatInrEstimate(
    quest.est_total_per_person_min_inr,
    quest.est_total_per_person_max_inr,
  )

  const handleSave = () => {
    if (savedToCollection) {
      removeQuest(quest.id)
      track('quest_unsaved', { quest_id: quest.id })
      setJustSaved(false)
      return
    }
    const titledQuest = { ...quest, title }
    saveQuest(titledQuest)
    localStorage.setItem(`quest_${titledQuest.id}`, JSON.stringify(titledQuest))
    track('quest_saved', { quest_id: titledQuest.id })
    setJustSaved(true)
    setTimeout(() => setJustSaved(false), 2000)
  }

  const handleQuestChange = (nextQuest: Quest) => {
    // The narrative names specific stops; after a swap it would keep
    // describing the replaced place, so rebuild it from the new stop list.
    const stopsChanged = nextQuest.stops.some(
      (stop, i) => stop.place.provider_id !== quest.stops[i]?.place.provider_id,
    )
    if (stopsChanged && nextQuest.narrative) {
      nextQuest = { ...nextQuest, narrative: rebuildNarrative(nextQuest) }
    }
    const titledQuest = { ...nextQuest, title }
    setQuest(titledQuest)
    localStorage.setItem(`quest_${titledQuest.id}`, JSON.stringify(titledQuest))
    if (isQuestSaved(titledQuest.id)) {
      saveQuest(titledQuest)
    }
  }

  const generationRequest = state?.request ?? null

  // One vote per quest, remembered across visits.
  const storedFeedbackVote = localStorage.getItem(
    `moodyeat:feedback_${quest.id}`,
  ) as 'up' | 'down' | null
  const effectiveFeedbackVote = feedbackVote ?? storedFeedbackVote

  const handleFeedback = (vote: 'up' | 'down') => {
    if (effectiveFeedbackVote) return
    localStorage.setItem(`moodyeat:feedback_${quest.id}`, vote)
    setFeedbackVote(vote)
    track('quest_feedback', {
      quest_id: quest.id,
      vote,
      occasion: quest.occasion,
      budget: quest.total_cost_estimate,
    })
  }

  const handleShuffle = async () => {
    if (!generationRequest || shuffling) return
    setShuffling(true)
    try {
      const nextQuest = await generateQuest({
        ...generationRequest,
        variety_seed: Math.floor(Math.random() * 2 ** 31),
      })
      track('quest_reshuffled', {
        occasion: generationRequest.occasion,
        budget: generationRequest.cost_estimate,
      })
      localStorage.setItem(`quest_${nextQuest.id}`, JSON.stringify(nextQuest))
      navigate(`/quest/${nextQuest.id}`, {
        state: { quest: nextQuest, request: generationRequest },
        replace: true,
      })
    } catch {
      showToast("Couldn't shuffle the plan — try again.")
    } finally {
      setShuffling(false)
    }
  }

  const handleShare = () => {
    if (sharing) return
    setShareMenuOpen(true)
  }

  const handleCopyShareLink = async () => {
    const titledQuest = { ...quest, title: title.trim() || quest.title }
    await copyToClipboard(await makeQuestShareUrl(titledQuest))
    track('quest_shared', {
      quest_id: titledQuest.id,
      share_method: 'clipboard_fallback',
    })
    setShareMenuOpen(false)
    showToast('Share link copied.')
  }

  const handleDownloadShareImage = async () => {
    if (sharing) return

    const titledQuest = { ...quest, title: title.trim() || quest.title }
    const shareUrl = await makeQuestShareUrl(titledQuest)
    setSharing(true)
    setShowShareCard(true)

    try {
      await nextPaint()

      const node = shareCardRef.current
      if (!node) throw new Error('Share card was not ready.')

      await waitForShareCardAssets(node)

      // Fall back to '' (system serif) rather than failing the whole export.
      const fontEmbedCSS = await shareCardFontEmbedCss().catch(() => '')
      const dataUrl = await toPng(node, {
        backgroundColor: '#1c1310',
        cacheBust: true,
        fontEmbedCSS,
        pixelRatio: 1,
        skipFonts: true,
        width: 1080,
        height: 1920,
      })
      const fileName = makePngFileName(titledQuest.title)
      setShowShareCard(false)

      downloadPng(dataUrl, fileName)
      track('quest_shared', {
        quest_id: titledQuest.id,
        share_method: 'download',
      })
      setShareMenuOpen(false)
      showToast('PNG downloaded.')
    } catch {
      await copyToClipboard(makeQuestTextSummary(titledQuest, shareUrl))
      track('quest_shared', {
        quest_id: titledQuest.id,
        share_method: 'clipboard_fallback',
      })
      setShareMenuOpen(false)
      showToast("Couldn't make image — copied details instead.")
    } finally {
      setShowShareCard(false)
      setSharing(false)
    }
  }

  const handleStart = () => {
    if (active) {
      clearActiveQuest()
      setActiveQuestId(null)
      setCompletedStopIndexes([])
      track('quest_stopped', { quest_id: quest.id })
      showToast('Quest stopped.')
      return
    }
    const titledQuest = { ...quest, title: title.trim() || quest.title }
    localStorage.setItem(`quest_${titledQuest.id}`, JSON.stringify(titledQuest))
    writeActiveQuest(titledQuest, [])
    setActiveQuestId(titledQuest.id)
    setCompletedStopIndexes([])
    track('quest_started', { quest_id: titledQuest.id })
    showToast('Quest started.')
  }

  const handleToggleStopComplete = (index: number) => {
    if (!active) return
    const titledQuest = { ...quest, title: title.trim() || quest.title }
    setCompletedStopIndexes((current) => {
      const next = current.includes(index)
        ? current.filter((item) => item !== index)
        : [...current, index].sort((a, b) => a - b)
      writeActiveQuest(titledQuest, next)
      return next
    })
  }

  const handleSaveMemory = (entry: JournalEntry) => {
    if (!addEntry(entry)) {
      showToast('Could not save memory. Try fewer photos.')
      return
    }
    const activeQuest = readActiveQuest()
    if (activeQuest?.id === quest.id) {
      localStorage.removeItem(ACTIVE_QUEST_KEY)
      localStorage.removeItem(LEGACY_ACTIVE_QUEST_KEY)
    }
    track('quest_completed', { quest_id: quest.id })
    track('journal_entry_created', { had_photo: entry.photos.length > 0 })
    setActiveQuestId(null)
    setCompletedStopIndexes([])
    setJournalOpen(false)
    showToast('Memory saved.', {
      actionLabel: 'Go to memory →',
      onAction: () => navigate('/journal'),
      durationMs: 6000,
    })
  }

  return (
    <main className="qp-page">
      <div className="qp-inner">
        <div className="qp-back">
          <Link
            to={backTo}
            className="qp-back-link"
            aria-label={`Back to ${backLabel.toLowerCase()}`}
          >
            <svg
              className="qp-back-icon"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden
            >
              <path
                d="M15 6l-6 6 6 6"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>Back to {backLabel}</span>
          </Link>
        </div>

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
            <span className="qp-chip">{budgetLabel(quest.total_cost_estimate)}</span>
            {totalEstimateLabel && (
              <span className="qp-chip" title="Estimated spend per person">
                {totalEstimateLabel}/person
              </span>
            )}
            <span className="qp-chip qp-chip--occasion">{quest.occasion}</span>
            {generationRequest && !preview && (
              <button
                type="button"
                className="qp-chip qp-chip--shuffle"
                onClick={handleShuffle}
                disabled={shuffling}
                title="Get a different mix of stops for the same plan"
              >
                {shuffling ? 'Shuffling…' : '🎲 Shuffle stops'}
              </button>
            )}
          </div>
        </header>

        {createdBanner && (
          <div className="qp-create-banner" role="status" aria-live="polite">
            <button
              type="button"
              className="qp-create-banner-close"
              aria-label="Dismiss"
              onClick={() => setCreatedBanner(false)}
            >
              ×
            </button>
            <span className="qp-create-banner-icon" aria-hidden>
              ✦
            </span>
            <span className="qp-create-banner-shimmer" aria-hidden />
            <div className="qp-create-banner-text">
              <span className="qp-create-banner-eyebrow">New quest created</span>
              <span className="qp-create-banner-title">
                Your custom plan is ready to go.
              </span>
            </div>
          </div>
        )}

        {quest.narrative && <p className="qp-narrative">{quest.narrative}</p>}
        {questNotice && <p className="qp-soft-note">{questNotice}</p>}

        <QuestCard
          quest={quest}
          onQuestChange={handleQuestChange}
          active={active}
          completedStopIndexes={completedStopIndexes}
          onToggleStopComplete={handleToggleStopComplete}
          onMarkDone={() => setJournalOpen(true)}
          readOnly={preview && !savedToCollection}
        />

        <div className="qp-feedback" role="group" aria-label="Plan feedback">
          {effectiveFeedbackVote ? (
            <p className="qp-feedback-thanks">
              Thanks — your feedback makes the plans better.
            </p>
          ) : (
            <>
              <span className="qp-feedback-label">Was this plan good?</span>
              <button
                type="button"
                className="qp-feedback-btn"
                aria-label="Good plan"
                onClick={() => handleFeedback('up')}
              >
                👍
              </button>
              <button
                type="button"
                className="qp-feedback-btn"
                aria-label="Bad plan"
                onClick={() => handleFeedback('down')}
              >
                👎
              </button>
            </>
          )}
        </div>

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
            className={`qp-action-btn qp-action-btn--start${active ? ' qp-action-btn--started' : ''}`}
            onClick={handleStart}
          >
            {active ? '✓ In progress' : '▶ Start'}
          </button>
        </div>

        {journalOpen && (
          <JournalSheet
            quest={{ ...quest, title: title.trim() || quest.title }}
            onSave={handleSaveMemory}
            onCancel={() => setJournalOpen(false)}
          />
        )}

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
        <div
          className={`saved-toast${toast.actionLabel ? ' saved-toast--action' : ''}`}
          role="status"
          aria-live="polite"
        >
          <span className="saved-toast-msg">{toast.message}</span>
          {toast.actionLabel && toast.onAction && (
            <button
              type="button"
              className="saved-toast-action"
              onClick={() => {
                toast.onAction?.()
                setToast(null)
              }}
            >
              {toast.actionLabel}
            </button>
          )}
        </div>
      )}
    </main>
  )
}
