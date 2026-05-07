import { useCallback, useEffect, useState } from 'react'
import type { Quest } from '../types/quest'

// Storage key for the quest-aware bookmarks system. Replaces the older
// place-id bookmarks (`tp-place-bookmarks-v1`) and the inline quest list
// (`moodyeat:quests`).
//
// Migration choice: the old place-bookmark data (`tp-place-bookmarks-v1`)
// is wiped — those entries are bare place IDs, not quests, and cannot be
// meaningfully promoted into the quest-shaped store. The legacy quest list
// at `moodyeat:quests` IS migrated, since it's already quest-shaped.
const STORAGE_KEY = 'moodyeat:saved_quests'
const LEGACY_QUEST_KEY = 'moodyeat:quests'
const LEGACY_PLACE_BOOKMARK_KEY = 'tp-place-bookmarks-v1'

export interface SavedQuest extends Quest {
  saved_at: string
}

let inMemoryCache: SavedQuest[] | null = null
const listeners = new Set<(next: SavedQuest[]) => void>()

function isQuest(value: unknown): value is Quest {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    'stops' in value &&
    typeof (value as { id?: unknown }).id === 'string' &&
    Array.isArray((value as { stops?: unknown }).stops)
  )
}

function readSaved(): SavedQuest[] {
  if (inMemoryCache) return inMemoryCache

  // One-shot migration: drop the legacy place-bookmark IDs.
  try {
    if (localStorage.getItem(LEGACY_PLACE_BOOKMARK_KEY) != null) {
      localStorage.removeItem(LEGACY_PLACE_BOOKMARK_KEY)
    }
  } catch {
    /* ignore */
  }

  let parsed: SavedQuest[] = []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const value: unknown = JSON.parse(raw)
      if (Array.isArray(value)) {
        parsed = value.filter(isQuest).map((q) => {
          const candidate = (q as { saved_at?: unknown }).saved_at
          return {
            ...q,
            saved_at:
              typeof candidate === 'string'
                ? candidate
                : new Date().toISOString(),
          }
        })
      }
    }
  } catch {
    parsed = []
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      /* ignore */
    }
  }

  // One-shot migration: pull legacy quests into the new key.
  try {
    const legacyRaw = localStorage.getItem(LEGACY_QUEST_KEY)
    if (legacyRaw) {
      const legacyValue: unknown = JSON.parse(legacyRaw)
      if (Array.isArray(legacyValue)) {
        const legacyQuests = legacyValue.filter(isQuest)
        const seen = new Set(parsed.map((q) => q.id))
        for (const q of legacyQuests) {
          if (!seen.has(q.id)) {
            parsed.push({ ...q, saved_at: new Date().toISOString() })
            seen.add(q.id)
          }
        }
        localStorage.removeItem(LEGACY_QUEST_KEY)
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed))
        } catch {
          /* ignore quota */
        }
      }
    }
  } catch {
    /* ignore */
  }

  inMemoryCache = parsed
  return parsed
}

function writeSaved(next: SavedQuest[]) {
  inMemoryCache = next
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    /* ignore quota */
  }
  for (const listener of listeners) listener(next)
}

export function useSavedQuests() {
  const [savedQuests, setSavedQuests] = useState<SavedQuest[]>(readSaved)

  useEffect(() => {
    const listener = (next: SavedQuest[]) => setSavedQuests(next)
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }, [])

  const saveQuest = useCallback((quest: Quest) => {
    const current = readSaved()
    const existing = current.find((q) => q.id === quest.id)
    const saved_at = existing?.saved_at ?? new Date().toISOString()
    const next = [
      { ...quest, saved_at },
      ...current.filter((q) => q.id !== quest.id),
    ]
    writeSaved(next)
  }, [])

  const removeQuest = useCallback((questId: string) => {
    const current = readSaved()
    const next = current.filter((q) => q.id !== questId)
    writeSaved(next)
  }, [])

  const isQuestSaved = useCallback(
    (questId: string) => savedQuests.some((q) => q.id === questId),
    [savedQuests],
  )

  return { savedQuests, saveQuest, removeQuest, isQuestSaved }
}
