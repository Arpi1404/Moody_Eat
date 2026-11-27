// What a first-time visitor has already been shown.
//
// Remembered in this browser's localStorage only. When storage cannot be read
// (some private modes) everything counts as already seen: showing nothing is
// better than a nudge that comes back on every page load.

const TOUR_KEY = 'moodyeat:tour_seen'

/** The one-time pointers on the quest page, each attached to the control it
 * explains. When several could show, the earliest in this list wins. */
export const QUEST_HINTS = [
  'share',
  'checkoff',
  'swap',
  'reorder',
  'addremove',
  'shuffle',
] as const
export type QuestHint = (typeof QUEST_HINTS)[number]

/** The order a replay ("What can I do here?") walks through them: down the
 * page, the way someone would use a quest. */
export const QUEST_HINTS_REPLAY_ORDER: readonly QuestHint[] = [
  'checkoff',
  'swap',
  'reorder',
  'addremove',
  'shuffle',
  'share',
]

const hintKey = (hint: QuestHint): string => `moodyeat:hint_${hint}_seen`

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

export const hintSeen = (hint: QuestHint): boolean => seen(hintKey(hint))
export const markHintSeen = (hint: QuestHint): void => markSeen(hintKey(hint))
export function clearHintSeen(hint: QuestHint): void {
  try {
    localStorage.removeItem(hintKey(hint))
  } catch {
    // Nothing was remembered, so there is nothing to forget.
  }
}

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
