// The copy of a quest this browser keeps under `quest_<id>`, and a note of
// whether its stops were changed here.
//
// The note matters because a quest can arrive from somewhere that still holds
// the plan as it was before the change: the page's history entry (which a
// reload keeps), or the short link it was opened from.

import type { Quest } from '../types/quest'

const questKey = (id: string): string => `quest_${id}`
const editedKey = (id: string): string => `moodyeat:edited_${id}`

export function storeEditedQuest(quest: Quest): void {
  localStorage.setItem(questKey(quest.id), JSON.stringify(quest))
  localStorage.setItem(editedKey(quest.id), '1')
}

/** This browser's changed copy of a quest, or null if it never changed it. */
export function readEditedQuest(id: string): Quest | null {
  try {
    if (localStorage.getItem(editedKey(id)) !== '1') return null
    const raw = localStorage.getItem(questKey(id))
    return raw ? (JSON.parse(raw) as Quest) : null
  } catch {
    return null
  }
}
