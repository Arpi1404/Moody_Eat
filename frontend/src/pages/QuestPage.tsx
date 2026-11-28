import { useCallback, useEffect, useRef, useState } from 'react'
import { toBlob, toPng } from 'html-to-image'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import 'leaflet/dist/leaflet.css'
import type { Quest, QuestGenerationRequest, Stop } from '../types/quest'
import type { JournalEntry } from '../types/journal'
import {
  fetchCuratedQuest,
  fetchStoredQuest,
  generateQuest,
  storeQuestForShare,
} from '../api'
import { TooManyQuestsError } from '../lib/tooManyQuests'
import { isSavedQuestId, useSavedQuests } from '../hooks/useSavedQuests'
import { useJournal } from '../hooks/useJournal'
import { useQuestHints } from '../hooks/useQuestHints'
import { CoachMark } from '../components/CoachMark'
import { ErrorState, LoadingState } from '../components/states'
import { track } from '../lib/analytics'
import { budgetLabel, formatInrEstimate } from '../lib/budget'
import { closedNotice, indiaWeekday } from '../lib/closedDays'
import { CONTACT_URL } from '../lib/contact'
import { addMyQuest, CreatorError, isDeadKey } from '../lib/creatorApi'
import { forgetKeys, storedKey } from '../lib/creatorKey'
import { withoutLinks } from '../lib/creatorText'
import { QUEST_HINTS, QUEST_HINTS_REPLAY_ORDER } from '../lib/onboarding'
import { MAX_STOPS } from '../lib/questBuild'
import { recordQuestPlaces } from '../lib/questHistory'
import { makeQuestShareUrl, readQuestFromLocationHash } from '../lib/questShare'
import {
  readEditedQuest,
  samePlan,
  storeEditedQuest,
} from '../lib/questStorage'
import { shareCardFontEmbedCss } from '../lib/shareFonts'
import { narrativeAfterEdit } from '../lib/narrative'
import { JournalSheet } from './JournalSheet'
import { QuestCard } from './QuestCard'
import { ShareableQuestCard } from './ShareableQuestCard'
import '../App.css'

const ACTIVE_QUEST_KEY = 'moodyeat:active_quest'
const LEGACY_ACTIVE_QUEST_KEY = 'moodyeat:activeQuest'

interface Undo {
  to: Quest
  /** Bring back the title that quest had, not just its stops. */
  restoreTitle?: boolean
  /** Analytics event for taking the change back. */
  event?: string
}

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

function makeQuestTextSummary(quest: Quest, url: string): string {
  // The title and the notes can be anyone's words: no links from them in chat.
  const stops = quest.stops
    .map(
      (stop, index) =>
        `${index + 1}. ${stop.place.name} - ${withoutLinks(stop.why_this_place)}`,
    )
    .join('\n')

  return `${withoutLinks(quest.title)}\n${quest.occasion} quest · ${quest.total_duration_minutes} min\n\n${stops}\n\nPlan yours at ${url}`
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

// iPhone/iPad browsers mostly ignore <a download> (in-app browsers drop it,
// Safari files it under Files → Downloads), so those devices get the native
// share sheet instead — it has "Save Image" and the Instagram/WhatsApp
// targets. Every other platform keeps the plain download above.
function isIosDevice(): boolean {
  if (/iPad|iPhone|iPod/.test(navigator.userAgent)) return true
  // iPadOS reports itself as a Mac; a touch-capable "Mac" is an iPad.
  return navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1
}

function canShareFile(file: File): boolean {
  try {
    return (
      typeof navigator.share === 'function' &&
      typeof navigator.canShare === 'function' &&
      navigator.canShare({ files: [file] })
    )
  } catch {
    return false
  }
}

function shareCardCaptureOptions(fontEmbedCSS: string) {
  return {
    backgroundColor: '#1c1310',
    cacheBust: true,
    fontEmbedCSS,
    // Photo URLs differ only in ?place_id=; without this, html-to-image
    // caches by path and every stop gets the first stop's photo.
    includeQueryParams: true,
    pixelRatio: 1,
    skipFonts: true,
    width: 1080,
    height: 1920,
  }
}

/** What the prepared iOS image was rendered from — a reopened share sheet
 *  reuses the image unless the title or the stops changed in between. */
function iosShareImageKey(quest: Quest): string {
  const stops = quest.stops.map((stop) => stop.place.provider_id ?? stop.place.name)
  return [quest.id, quest.title, ...stops].join('|')
}

type IosShareImage =
  | { status: 'idle' }
  | { status: 'preparing' }
  | { status: 'ready'; file: File }
  | { status: 'error' }

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
  const { id, shortId } = useParams<{ id: string; shortId: string }>()
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
  // Set while a short link shows a plan that this browser has its own, changed
  // version of: that version, waiting for a choice.
  const [ownVersion, setOwnVersion] = useState<Quest | null>(null)
  const [activeQuestId, setActiveQuestId] = useState<string | null>(null)
  const [completedStopIndexes, setCompletedStopIndexes] = useState<number[]>([])
  const [journalOpen, setJournalOpen] = useState(false)
  const [sharing, setSharing] = useState(false)
  const [addingToPage, setAddingToPage] = useState(false)
  const [shareMenuOpen, setShareMenuOpen] = useState(false)
  const [showShareCard, setShowShareCard] = useState(false)
  const [toast, setToast] = useState<{
    message: string
    actionLabel?: string
    onAction?: () => void
    /** What the action puts back: the quest from before a removal, or the
     * edited version that was just replaced. */
    undo?: Undo
    /** Put the keyboard on the action, for someone who got here with it. */
    focusAction?: boolean
    durationMs: number
  } | null>(null)
  const [createdBanner, setCreatedBanner] = useState(false)
  const [shuffling, setShuffling] = useState(false)
  const [swapSheetOpen, setSwapSheetOpen] = useState(false)
  // Set once a memory is saved: the moment to point at Share.
  const [sharePrompt, setSharePrompt] = useState(false)
  // Set by "What can I do here?": the hints are being shown on request.
  const [replaying, setReplaying] = useState(false)
  const [feedbackVote, setFeedbackVote] = useState<'up' | 'down' | null>(null)
  const [iosShareImage, setIosShareImage] = useState<IosShareImage>({
    status: 'idle',
  })
  const [sharePreviewUrl, setSharePreviewUrl] = useState<string | null>(null)
  const shareCardRef = useRef<HTMLDivElement | null>(null)
  const iosShareImageKeyRef = useRef<string | null>(null)
  const sharePreviewUrlRef = useRef<string | null>(null)
  const toastTimer = useRef<number | null>(null)
  const createdBannerTimer = useRef<number | null>(null)

  const savedToCollection = quest ? isQuestSaved(quest.id) : false
  // Until the choice is made, nothing on this page may write over their
  // version: no edits, no Save, no Start.
  const choosingVersion = quest != null && ownVersion?.id === quest.id
  const active = quest ? activeQuestId === quest.id && !choosingVersion : false

  useEffect(() => {
    let cancelled = false

    async function loadQuest() {
      setQuestLoading(true)
      setQuestError(null)

      try {
        await wait(200)
        let nextQuest: Quest | null = null
        let changedCopy: Quest | null = null
        // A reload keeps the history entry, which still holds the quest as it
        // was when the page was first opened. If its stops were changed since,
        // the stored copy is the real one, and the generator's note about
        // missing stops no longer describes it. A curated preview that is not
        // saved is always shown as it was made.
        const edited =
          state?.quest && (!preview || isSavedQuestId(state.quest.id))
            ? readEditedQuest(state.quest.id)
            : null
        const softMessage = edited ? null : (state?.softMessage ?? null)

        if (state?.quest) {
          nextQuest = edited ?? state.quest
        } else if (shortId) {
          // Short share link (/q/<shortId>): the quest lives in the
          // server-side store. The fetch also counts a view — the receiving
          // side of the share loop.
          nextQuest = await fetchStoredQuest(shortId)
          // The link keeps the plan as it was shared. Show that, but never
          // write it over a copy this browser has since changed: offer it.
          const mine = readEditedQuest(nextQuest.id)
          if (!mine) {
            localStorage.setItem(`quest_${nextQuest.id}`, JSON.stringify(nextQuest))
          } else if (!samePlan(mine, nextQuest)) {
            changedCopy = mine
          }
          track('shared_quest_opened', { short_id: shortId })
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

        if (!nextQuest && preview && id) {
          // A curated quest opened from a link on a device that never loaded
          // it from the home page: the server still has it.
          nextQuest = await fetchCuratedQuest(id).catch(() => null)
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
          setOwnVersion(changedCopy)
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
  }, [id, shortId, state, preview])

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
      if (sharePreviewUrlRef.current)
        URL.revokeObjectURL(sharePreviewUrlRef.current)
    }
  }, [])

  // Keyed on the id: changing a stop must not bring the banner back.
  const questId = quest?.id
  useEffect(() => {
    if (!questId || !state?.justCreated) return
    setCreatedBanner(true)
    if (createdBannerTimer.current)
      window.clearTimeout(createdBannerTimer.current)
    createdBannerTimer.current = window.setTimeout(
      () => setCreatedBanner(false),
      5200,
    )
  }, [questId, state?.justCreated])

  useEffect(() => {
    if (!shareMenuOpen) return
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [shareMenuOpen])

  const hideToastAfter = useCallback((durationMs: number) => {
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), durationMs)
  }, [])

  const showToast = useCallback(
    (
      message: string,
      options?: {
        actionLabel?: string
        onAction?: () => void
        undo?: Undo
        focusAction?: boolean
        durationMs?: number
      },
    ) => {
      const durationMs = options?.durationMs ?? 2600
      setToast({ ...options, message, durationMs })
      hideToastAfter(durationMs)
    },
    [hideToastAfter],
  )

  // Curated previews are read-only until saved.
  const readOnly = preview && !savedToCollection
  const stopCount = quest?.stops.length ?? 0
  const canEdit = stopCount > 0 && !readOnly && !active && !choosingVersion
  const { hint, dismissHint, hintUsed, replayHints } = useQuestHints(
    {
      share: sharePrompt || replaying,
      checkoff: active && stopCount > 0,
      swap: canEdit,
      reorder: canEdit && stopCount > 1,
      addremove: canEdit && stopCount < MAX_STOPS,
      shuffle: canEdit && !preview && Boolean(state?.request),
    },
    // One thing at a time: hints wait for sheets and toasts to clear.
    questLoading || swapSheetOpen || journalOpen || shareMenuOpen || toast != null,
    replaying ? QUEST_HINTS_REPLAY_ORDER : QUEST_HINTS,
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

  const daysNotice = closedNotice(quest, indiaWeekday())

  const openOwnVersion = () => {
    if (!ownVersion) return
    navigate(`/quest/${ownVersion.id}`, {
      replace: true,
      state: { quest: ownVersion },
    })
  }

  const pointToOwnVersion = () =>
    showToast('You have an edited version of this quest.', {
      actionLabel: 'Open it',
      onAction: openOwnVersion,
      durationMs: 5000,
    })

  const handleSave = () => {
    if (choosingVersion) {
      pointToOwnVersion()
      return
    }
    if (savedToCollection) {
      removeQuest(quest.id)
      // An unsaved preview is read-only again, so nothing may be undone on it.
      if (preview) setToast((current) => (current?.undo ? null : current))
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

  /** Make this the quest, on screen and everywhere this browser keeps it. */
  const persistQuest = (nextQuest: Quest, nextTitle: string = title) => {
    const titledQuest = { ...nextQuest, title: nextTitle }
    setQuest(titledQuest)
    setTitle(nextTitle)
    storeEditedQuest(titledQuest)
    if (isQuestSaved(titledQuest.id)) {
      saveQuest(titledQuest)
    }
    // A short link still holds the plan as it was shared. This one is no
    // longer that plan, so give it its own address: a reload keeps the change.
    if (shortId) {
      window.history.replaceState(
        window.history.state,
        '',
        `/quest/${titledQuest.id}`,
      )
    }
  }

  const handleQuestChange = (nextQuest: Quest) => {
    persistQuest({ ...nextQuest, narrative: narrativeAfterEdit(quest, nextQuest) })
    setQuestNotice(null)
    // Undoing an older removal now would throw this change away.
    setToast((current) => (current?.undo ? null : current))
  }

  const handleStopRemoved = (
    next: Quest,
    removed: Stop,
    byKeyboard: boolean,
  ) => {
    const previous = quest
    handleQuestChange(next)
    // A note someone typed goes with its stop: say so while Undo can bring
    // both back.
    const lost = removed.note_by_creator ? ' and the note on it' : ''
    showToast(`Removed ${removed.place.name}${lost}.`, {
      actionLabel: 'Undo',
      undo: { to: previous, event: 'stop_removal_undone' },
      focusAction: byKeyboard,
      durationMs: 8000,
    })
  }

  // Puts back exactly what was there, narrative included.
  const applyUndo = ({ to, restoreTitle, event }: Undo) => {
    if (to.id !== quest.id) return
    if (event) track(event, { stop_count: to.stops.length })
    persistQuest(to, restoreTitle ? to.title : title)
  }

  // The one way an edited version is given up, and it can be taken back.
  const replaceOwnVersion = () => {
    if (!ownVersion) return
    const mine = ownVersion
    setOwnVersion(null)
    persistQuest(quest)
    showToast('Replaced your edited version.', {
      actionLabel: 'Undo',
      undo: { to: mine, restoreTitle: true },
      durationMs: 8000,
    })
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
    hintUsed('shuffle')
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
      recordQuestPlaces(nextQuest)
      localStorage.setItem(`quest_${nextQuest.id}`, JSON.stringify(nextQuest))
      const handEdited = readEditedQuest(quest.id)
      navigate(`/quest/${nextQuest.id}`, {
        state: { quest: nextQuest, request: generationRequest },
        replace: true,
      })
      // A new plan replaces this one on screen. Someone who had changed this
      // one by hand needs a way back to it.
      if (handEdited) {
        showToast('New plan drawn.', {
          actionLabel: 'Back to my edit',
          onAction: () =>
            navigate(`/quest/${handEdited.id}`, {
              state: { quest: handEdited, request: generationRequest },
              replace: true,
            }),
          durationMs: 8000,
        })
      }
    } catch (err) {
      // "Try again" would be wrong at the limit: trying at once fails again.
      showToast(
        err instanceof TooManyQuestsError
          ? err.message
          : "Couldn't shuffle the plan — try again.",
      )
    } finally {
      setShuffling(false)
    }
  }

  const iosDevice = isIosDevice()

  const closeSharePreview = () => {
    if (sharePreviewUrlRef.current) {
      URL.revokeObjectURL(sharePreviewUrlRef.current)
      sharePreviewUrlRef.current = null
    }
    setSharePreviewUrl(null)
  }

  // iOS only allows navigator.share() directly inside a tap, and rendering
  // the card takes a few seconds — so the image is rendered as soon as the
  // share sheet opens and the button enables once it is ready.
  const prepareIosShareImage = async () => {
    const titledQuest = { ...quest, title: title.trim() || quest.title }
    const key = iosShareImageKey(titledQuest)
    if (iosShareImageKeyRef.current === key && iosShareImage.status !== 'error') return
    iosShareImageKeyRef.current = key
    const isCurrent = () => iosShareImageKeyRef.current === key

    setIosShareImage({ status: 'preparing' })
    setShowShareCard(true)
    try {
      await nextPaint()

      const node = shareCardRef.current
      if (!node) throw new Error('Share card was not ready.')

      await waitForShareCardAssets(node)

      const fontEmbedCSS = await shareCardFontEmbedCss().catch(() => '')
      const blob = await toBlob(node, shareCardCaptureOptions(fontEmbedCSS))
      if (!blob) throw new Error('Share card produced no image.')

      const file = new File([blob], makePngFileName(titledQuest.title), {
        type: 'image/png',
      })
      if (isCurrent()) setIosShareImage({ status: 'ready', file })
    } catch {
      if (isCurrent()) setIosShareImage({ status: 'error' })
    } finally {
      if (isCurrent()) setShowShareCard(false)
    }
  }

  const handleShare = () => {
    hintUsed('share')
    if (sharing) return
    setShareMenuOpen(true)
    if (iosDevice) {
      closeSharePreview()
      void prepareIosShareImage()
    }
  }

  const iosImagePreparing =
    iosDevice &&
    (iosShareImage.status === 'preparing' || iosShareImage.status === 'idle')

  const closeShareMenu = () => {
    setShareMenuOpen(false)
    closeSharePreview()
  }

  const openSharePreview = (file: File) => {
    closeSharePreview()
    const url = URL.createObjectURL(file)
    sharePreviewUrlRef.current = url
    setSharePreviewUrl(url)
  }

  const handleIosShareImage = async () => {
    if (iosShareImage.status === 'preparing' || iosShareImage.status === 'idle') return

    const titledQuest = { ...quest, title: title.trim() || quest.title }

    if (iosShareImage.status === 'error') {
      await copyToClipboard(
        makeQuestTextSummary(titledQuest, await makeQuestShareUrl(titledQuest)),
      )
      track('quest_shared', {
        quest_id: titledQuest.id,
        share_method: 'clipboard_fallback',
      })
      closeShareMenu()
      showToast("Couldn't make image — copied details instead.")
      return
    }

    const { file } = iosShareImage

    // No file sharing here (some in-app browsers): show the image so it can
    // be saved with a long-press.
    if (!canShareFile(file)) {
      openSharePreview(file)
      track('share_image_preview_shown', {
        quest_id: titledQuest.id,
        reason: 'share_unsupported',
      })
      return
    }

    try {
      // Must stay the first await: Safari rejects share() once the tap that
      // triggered it is no longer the current user gesture.
      await navigator.share({ files: [file] })
      track('quest_shared', {
        quest_id: titledQuest.id,
        share_method: 'native_share',
      })
      closeShareMenu()
    } catch (err) {
      // The person closed the share sheet — leave the menu as it was.
      if (err instanceof DOMException && err.name === 'AbortError') return
      openSharePreview(file)
      track('share_image_preview_shown', {
        quest_id: titledQuest.id,
        reason: 'share_failed',
      })
    }
  }

  const handleShareWhatsApp = async () => {
    const titledQuest = { ...quest, title: title.trim() || quest.title }
    // Open the window synchronously inside the tap gesture: building the
    // share URL now involves a network call (short-link store), and Safari
    // blocks window.open after an await.
    const popup = window.open('about:blank', '_blank')
    if (popup) popup.opener = null
    const url = await makeQuestShareUrl(titledQuest)
    const text = `${withoutLinks(titledQuest.title)} — here's the plan 👇\n${url}`
    const waUrl = `https://wa.me/?text=${encodeURIComponent(text)}`
    if (popup) {
      popup.location.href = waUrl
    } else {
      window.open(waUrl, '_blank', 'noopener,noreferrer')
    }
    track('quest_shared', {
      quest_id: titledQuest.id,
      share_method: 'whatsapp',
    })
    setShareMenuOpen(false)
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

  // Only offered in a browser that has opened a creator's manage link.
  const handleAddToMyPage = async () => {
    const key = storedKey()
    if (!key || addingToPage) return
    setAddingToPage(true)
    const titledQuest = { ...quest, title: title.trim() || quest.title }
    try {
      // Stored as any share is; the page then lists that link.
      const shortId = await storeQuestForShare(titledQuest)
      const { added, page } = await addMyQuest(key, shortId)
      track('creator_quest_added', {
        source: 'share_sheet',
        result: added ? 'added' : 'already',
      })
      closeShareMenu()
      showToast(added ? 'Added to your page.' : "It's already on your page.", {
        actionLabel: 'View',
        onAction: () => navigate(`/by/${page.handle}`),
        durationMs: 6000,
      })
    } catch (err) {
      track('creator_quest_added', { source: 'share_sheet', result: 'failed' })
      // A replaced key is no use any more: stop offering the button.
      if (isDeadKey(err)) forgetKeys()
      closeShareMenu()
      showToast(
        err instanceof CreatorError
          ? err.message
          : "Couldn't add it to your page. Try again.",
        { durationMs: 6000 },
      )
    } finally {
      setAddingToPage(false)
    }
  }

  const handleDownloadShareImage = async () => {
    if (iosDevice) return handleIosShareImage()
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
      const dataUrl = await toPng(node, shareCardCaptureOptions(fontEmbedCSS))
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
    if (choosingVersion) {
      pointToOwnVersion()
      return
    }
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
    setSharePrompt(true)
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
              <span className="qp-shuffle-anchor">
                <button
                  type="button"
                  className="qp-chip qp-chip--shuffle"
                  onClick={handleShuffle}
                  disabled={shuffling}
                  title="Get a different mix of stops for the same plan"
                >
                  {shuffling ? 'Shuffling…' : '🎲 Shuffle stops'}
                </button>
                {hint === 'shuffle' && (
                  <CoachMark
                    placement="below"
                    title="Want a fresh mix?"
                    onDismiss={() => dismissHint('shuffle')}
                    reveal={replaying}
                  >
                    Shuffle redraws every stop for the same plan.
                  </CoachMark>
                )}
              </span>
            )}
          </div>
        </header>

        {choosingVersion && (
          <section className="qp-own-version" aria-label="Your edited version">
            <p>
              You changed this quest in this browser. This link still shows it as
              it was shared.
            </p>
            <div className="qp-own-version-actions">
              <button
                type="button"
                className="qp-own-version-open"
                onClick={openOwnVersion}
              >
                Open my edited version
              </button>
              {/* Not while theirs is in progress: its ticks are by position. */}
              {activeQuestId !== quest.id && (
                <button
                  type="button"
                  className="qp-own-version-replace"
                  onClick={replaceOwnVersion}
                >
                  Replace mine with this one
                </button>
              )}
            </div>
          </section>
        )}

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

        {quest.created_by && (
          <p className="qp-byline">
            <span aria-hidden>✦</span> made by {quest.created_by}
          </p>
        )}
        {quest.narrative && <p className="qp-narrative">{quest.narrative}</p>}
        {daysNotice && (
          <p
            className={`qp-closed-note${daysNotice.today ? ' qp-closed-note--today' : ''}`}
            role="note"
          >
            <strong>{daysNotice.headline}</strong> {daysNotice.detail}
          </p>
        )}
        {quest.weather_note && (
          <p className="qp-soft-note">
            <span aria-hidden>🌧️</span> {quest.weather_note}
          </p>
        )}
        {questNotice && <p className="qp-soft-note">{questNotice}</p>}

        <QuestCard
          quest={quest}
          onQuestChange={handleQuestChange}
          active={active}
          completedStopIndexes={completedStopIndexes}
          onToggleStopComplete={handleToggleStopComplete}
          onMarkDone={() => setJournalOpen(true)}
          readOnly={readOnly || choosingVersion}
          onLockedSwap={() => {
            if (choosingVersion) {
              pointToOwnVersion()
              return
            }
            if (active) {
              showToast("Stops can't change while this quest is in progress.", {
                durationMs: 4000,
              })
              return
            }
            showToast('Save this quest to swap stops.', {
              actionLabel: 'Save',
              onAction: handleSave,
              durationMs: 5000,
            })
          }}
          onStopRemoved={handleStopRemoved}
          onSwapSheetChange={setSwapSheetOpen}
          hint={hint}
          onHintDismiss={dismissHint}
          onHintUsed={hintUsed}
          onReplayHints={
            readOnly || choosingVersion
              ? undefined
              : () => {
                  setReplaying(true)
                  replayHints()
                }
          }
          revealHints={replaying}
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

        {/* On every shared link, not only ones with a creator's words: the
            title can be edited on any quest, and anyone can store one. */}
        {shortId && (
          <p className="qp-report">
            <a
              href={CONTACT_URL}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => track('quest_report_tapped', { short_id: shortId })}
            >
              Report this quest
            </a>{' '}
            on Instagram. Tell us its code: <strong>{shortId}</strong>
          </p>
        )}

        <div className="qp-bottom-bar">
          <button
            type="button"
            className={`qp-action-btn qp-action-btn--save${savedToCollection && !choosingVersion ? ' qp-action-btn--saved' : ''}`}
            onClick={handleSave}
          >
            {justSaved
              ? '✓ Saved'
              : savedToCollection && !choosingVersion
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
          {/* Hangs off the bar itself: Share is its middle button. */}
          {hint === 'share' && (
            <CoachMark
              placement="above"
              title="Worth passing on?"
              onDismiss={() => dismissHint('share')}
            >
              Share sends this plan as a link or a story card.
            </CoachMark>
          )}
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
                if (!sharing) closeShareMenu()
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
                <h2 id="qp-share-title">
                  {sharePreviewUrl ? 'Save the story card' : 'Choose what to send'}
                </h2>
                <p>
                  {sharePreviewUrl
                    ? 'Touch and hold the image, then choose Save to Photos.'
                    : iosDevice
                      ? 'Save or share the story card, or copy the quest link to paste anywhere.'
                      : 'Download the story card as a PNG, or copy the quest link to paste anywhere.'}
                </p>
              </div>
              {sharePreviewUrl ? (
                <div className="qp-share-preview">
                  <img
                    className="qp-share-preview-img"
                    src={sharePreviewUrl}
                    alt={`Story card for ${title.trim() || quest.title}`}
                  />
                </div>
              ) : (
                <div className="qp-share-actions">
                  <button
                    type="button"
                    className="qp-share-option"
                    onClick={handleShareWhatsApp}
                    disabled={sharing}
                  >
                    <span
                      className="qp-share-option-icon qp-share-option-icon--wa"
                      aria-hidden
                    >
                      WA
                    </span>
                    <span>
                      <span className="qp-share-option-title">
                        Share on WhatsApp
                      </span>
                      <span className="qp-share-option-subtitle">
                        Send the plan straight to the group.
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    className="qp-share-option"
                    onClick={handleDownloadShareImage}
                    disabled={sharing || iosImagePreparing}
                  >
                    <span className="qp-share-option-icon" aria-hidden>
                      PNG
                    </span>
                    <span>
                      <span className="qp-share-option-title">
                        {iosDevice
                          ? iosImagePreparing
                            ? 'Preparing image...'
                            : 'Save or share image'
                          : sharing
                            ? 'Making PNG...'
                            : 'Download PNG'}
                      </span>
                      <span className="qp-share-option-subtitle">
                        {iosDevice
                          ? 'Save to Photos or post the story card.'
                          : 'Save the Instagram-story card.'}
                      </span>
                    </span>
                    {(sharing || iosImagePreparing) && (
                      <span className="qp-action-spinner" aria-hidden />
                    )}
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
                  {storedKey() && (
                    <button
                      type="button"
                      className="qp-share-option"
                      onClick={handleAddToMyPage}
                      disabled={sharing || addingToPage}
                      aria-busy={addingToPage}
                    >
                      <span className="qp-share-option-icon" aria-hidden>
                        ✦
                      </span>
                      <span>
                        <span className="qp-share-option-title">
                          {addingToPage ? 'Adding...' : 'Add to my page'}
                        </span>
                        <span className="qp-share-option-subtitle">
                          List it publicly on your creator page.
                        </span>
                      </span>
                    </button>
                  )}
                </div>
              )}
              <button
                type="button"
                className="qp-share-cancel"
                onClick={sharePreviewUrl ? closeSharePreview : closeShareMenu}
                disabled={sharing}
              >
                {sharePreviewUrl ? 'Back' : 'Cancel'}
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
          // A new message gets a new element, so its button can take focus.
          key={toast.message}
          className={`saved-toast${toast.actionLabel ? ' saved-toast--action' : ''}`}
          role="status"
          aria-live="polite"
        >
          <span className="saved-toast-msg">{toast.message}</span>
          {toast.actionLabel && (toast.onAction || toast.undo) && (
            <button
              type="button"
              className="saved-toast-action"
              autoFocus={toast.focusAction}
              // The toast stays for as long as the keyboard is on its button.
              onFocus={() => {
                if (toastTimer.current) window.clearTimeout(toastTimer.current)
              }}
              onBlur={() => hideToastAfter(toast.durationMs)}
              onClick={() => {
                setToast(null)
                // Undo is run from here, not stored on the toast, so that it
                // sees the quest as it is now (saved since, for instance).
                if (toast.undo) applyUndo(toast.undo)
                else toast.onAction?.()
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
