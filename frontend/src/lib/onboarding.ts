// What a first-time visitor has already been shown.
//
// Remembered in this browser's localStorage only. When storage cannot be read
// (some private modes) everything counts as already seen: showing nothing is
// better than a nudge that comes back on every page load.

const TOUR_KEY = 'moodyeat:tour_seen'
const QUEST_TIPS_KEY = 'moodyeat:quest_tips_seen'

function seen(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return true
  }
}

function markSeen(key: string): void {
  try {
    localStorage.setItem(key, '1')
  } catch {
    // Nothing to remember it in; the nudge may show once more.
  }
}

export const tourSeen = (): boolean => seen(TOUR_KEY)
export const markTourSeen = (): void => markSeen(TOUR_KEY)

export const questTipsSeen = (): boolean => seen(QUEST_TIPS_KEY)
export const markQuestTipsSeen = (): void => markSeen(QUEST_TIPS_KEY)

/** True when this browser already holds a quest — someone who has made or
 * opened one before is not a first-time visitor, whatever the flags say. */
export function hasQuestHistory(): boolean {
  try {
    for (let i = 0; i < localStorage.length; i++) {
      if (localStorage.key(i)?.startsWith('quest_')) return true
    }
    return false
  } catch {
    return true
  }
}
