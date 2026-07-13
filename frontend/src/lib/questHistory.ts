// Recent-places memory: remembers which places appeared in the user's recent
// generated quests so the next generation can avoid repeating them (the
// backend treats these as a soft exclusion — variety never costs a stop).

import type { Quest } from '../types/quest'

const STORAGE_KEY = 'moodyeat:recent_places'
const MAX_ENTRIES = 24
const EXPIRY_MS = 14 * 24 * 60 * 60 * 1000 // 14 days

type RecentPlace = { id: string; at: number }

function readAll(): RecentPlace[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    const cutoff = Date.now() - EXPIRY_MS
    return parsed.filter(
      (e): e is RecentPlace =>
        typeof (e as RecentPlace)?.id === 'string' &&
        typeof (e as RecentPlace)?.at === 'number' &&
        (e as RecentPlace).at > cutoff,
    )
  } catch {
    return []
  }
}

export function getRecentPlaceIds(): string[] {
  return readAll().map((e) => e.id)
}

export function recordQuestPlaces(quest: Quest): void {
  try {
    const now = Date.now()
    const incoming = quest.stops
      .map((s) => s.place.provider_id)
      .filter((id): id is string => Boolean(id))
    const existing = readAll().filter((e) => !incoming.includes(e.id))
    const merged = [
      ...incoming.map((id) => ({ id, at: now })),
      ...existing,
    ].slice(0, MAX_ENTRIES)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged))
  } catch {
    // localStorage unavailable (private mode etc.) — variety just degrades.
  }
}
