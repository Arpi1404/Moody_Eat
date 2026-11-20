import { useCallback, useEffect, useRef, useState } from 'react'
import { track } from '../lib/analytics'
import {
  QUEST_HINTS,
  clearHintSeen,
  hintSeen,
  markHintSeen,
  type QuestHint,
} from '../lib/onboarding'

/** A beat of quiet after one hint leaves, so the next reads as a new thing. */
const REST_MS = 900

/** Which one-time hint the quest page should show right now, if any.
 *
 * `eligible` says which hints make sense at this moment: the control is on
 * screen and can be used. Only one hint shows at a time, and each is gone for
 * good once it is dismissed or the person uses the control it points at.
 * `paused` holds every hint back while a sheet or toast has the screen.
 * `order` decides which goes first when several could show. */
export function useQuestHints(
  eligible: Partial<Record<QuestHint, boolean>>,
  paused: boolean,
  order: readonly QuestHint[] = QUEST_HINTS,
) {
  const [seen, setSeen] = useState<ReadonlySet<QuestHint>>(
    () => new Set(QUEST_HINTS.filter(hintSeen)),
  )
  const [resting, setResting] = useState(false)
  const restTimer = useRef<number | null>(null)
  const reported = useRef(new Set<QuestHint>())

  const next = order.find((hint) => eligible[hint] && !seen.has(hint))
  const hint = paused || resting ? null : (next ?? null)

  // Read by the callbacks below, so they can stay stable between renders.
  const showing = useRef<QuestHint | null>(null)
  useEffect(() => {
    showing.current = hint
  }, [hint])

  useEffect(() => {
    if (!hint || reported.current.has(hint)) return
    reported.current.add(hint)
    track('hint_shown', { hint })
  }, [hint])

  useEffect(
    () => () => {
      if (restTimer.current) window.clearTimeout(restTimer.current)
    },
    [],
  )

  const retire = useCallback((target: QuestHint) => {
    markHintSeen(target)
    setSeen((current) =>
      current.has(target) ? current : new Set(current).add(target),
    )
    if (showing.current !== target) return
    setResting(true)
    if (restTimer.current) window.clearTimeout(restTimer.current)
    restTimer.current = window.setTimeout(() => setResting(false), REST_MS)
  }, [])

  /** "Got it" on the hint itself. */
  const dismissHint = useCallback(
    (target: QuestHint) => {
      track('hint_dismissed', { hint: target })
      retire(target)
    },
    [retire],
  )

  /** The person used the control, with or without its hint on screen. Either
   * way they know it now, so the hint never needs to show. */
  const hintUsed = useCallback(
    (target: QuestHint) => {
      if (showing.current === target) track('hint_followed', { hint: target })
      retire(target)
    },
    [retire],
  )

  /** Forget every hint, so each is offered again. Works for this visit even
   * where the browser gives us nowhere to remember things. */
  const replayHints = useCallback(() => {
    QUEST_HINTS.forEach(clearHintSeen)
    reported.current.clear()
    if (restTimer.current) window.clearTimeout(restTimer.current)
    setResting(false)
    setSeen(new Set())
    track('hints_replayed')
  }, [])

  return { hint, dismissHint, hintUsed, replayHints }
}
