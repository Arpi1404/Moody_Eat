import { useCallback, useState } from 'react'

const STORAGE_KEY = 'tp-place-bookmarks-v1'

function readIds(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((x): x is string => typeof x === 'string')
  } catch {
    return []
  }
}

export function useBookmarks() {
  const [ids, setIds] = useState<string[]>(readIds)

  const toggle = useCallback((id: string) => {
    setIds((prev) => {
      const next = prev.includes(id)
        ? prev.filter((x) => x !== id)
        : [...prev, id]
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      } catch {
        /* ignore quota */
      }
      return next
    })
  }, [])

  const isSaved = useCallback((id: string) => ids.includes(id), [ids])

  return { toggle, isSaved }
}
