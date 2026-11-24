// Tells the server which suggested place was swapped for which.
//
// Why: the engine picks by rating, popularity and price and knows nothing
// about taste. A swap is the one moment a person says "not this place, that
// one, for this kind of outing" — over time, our own signal for what suits
// which occasion.
//
// What is sent: Google place ids and the context of the choice (occasion,
// stop category, budget, the stop's start time, what else was offered).
// Nothing about the person or the quest: no quest id, no title, no
// coordinates, no creator name.
//
// It must never get in the way of a swap: it is sent after the swap has
// already been applied, nothing waits on it, and every failure is ignored.

import { getApiBase } from '../api'
import type { Quest, StopAlternative } from '../types/quest'
import { doNotTrackEnabled } from './analytics'

// The swap sheet shows six alternatives; the server accepts up to twelve.
const MAX_SHOWN = 12

function privacySignalSet(): boolean {
  if (doNotTrackEnabled()) return true
  if (typeof navigator === 'undefined') return false
  // Global Privacy Control: the newer "do not track me" browser signal.
  return (
    (navigator as Navigator & { globalPrivacyControl?: boolean })
      .globalPrivacyControl === true
  )
}

export function logSwap(opts: {
  /** The quest as it was before the swap. */
  quest: Quest
  stopIndex: number
  /** The alternative that was confirmed. */
  chosen: StopAlternative
  /** Every alternative the sheet offered, in the order shown. */
  shown: StopAlternative[]
}): void {
  try {
    if (privacySignalSet()) return

    const { quest, stopIndex, chosen, shown } = opts
    const replaced = quest.stops[stopIndex]
    const from = replaced?.place.provider_id
    const to = chosen.place.provider_id
    // Places without an id (very old saved quests) cannot be told apart.
    if (!replaced || !from || !to || from === to) return

    const body = JSON.stringify({
      from_place_id: from,
      to_place_id: to,
      shown_place_ids: shown
        .map((alternative) => alternative.place.provider_id)
        .filter(Boolean)
        .slice(0, MAX_SHOWN),
      occasion: quest.occasion,
      category: replaced.category,
      budget: quest.total_cost_estimate,
      stop_index: stopIndex,
      stop_count: quest.stops.length,
      slot_start: replaced.time_block_start,
      quest_origin: quest.origin ?? null,
    })

    void fetch(`${getApiBase()}/api/quest/swap-log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      // Lets the request finish if the page is closed right after the swap.
      keepalive: true,
    }).catch(() => {
      // Offline, blocked, or a server that does not have the endpoint yet.
    })
  } catch {
    // Never let logging break a swap.
  }
}
