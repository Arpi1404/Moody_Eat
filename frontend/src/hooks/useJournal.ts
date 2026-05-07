import { useCallback, useEffect, useState } from 'react'
import type { JournalEntry } from '../types/journal'

const STORAGE_KEY = 'moodyeat:journal'

let inMemoryCache: JournalEntry[] | null = null
const listeners = new Set<(next: JournalEntry[]) => void>()

function isJournalEntry(value: unknown): value is JournalEntry {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { questId?: unknown }).questId === 'string' &&
    typeof (value as { completedAt?: unknown }).completedAt === 'string' &&
    typeof (value as { rating?: unknown }).rating === 'number' &&
    Array.isArray((value as { photos?: unknown }).photos) &&
    typeof (value as { note?: unknown }).note === 'string'
  )
}

function readJournal(): JournalEntry[] {
  if (inMemoryCache) return inMemoryCache

  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      inMemoryCache = []
      return inMemoryCache
    }

    const value: unknown = JSON.parse(raw)
    inMemoryCache = Array.isArray(value) ? value.filter(isJournalEntry) : []
  } catch {
    inMemoryCache = []
  }

  return inMemoryCache
}

function writeJournal(next: JournalEntry[]): boolean {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    return false
  }

  inMemoryCache = next
  for (const listener of listeners) listener(next)
  return true
}

export function useJournal() {
  const [entries, setEntries] = useState<JournalEntry[]>(readJournal)

  useEffect(() => {
    const listener = (next: JournalEntry[]) => setEntries(next)
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }, [])

  const addEntry = useCallback((entry: JournalEntry): boolean => {
    const next = [entry, ...readJournal()]
    return writeJournal(next)
  }, [])

  return { entries, addEntry }
}
