// Single-point analytics wrapper.
//
// Provider: Umami Cloud (script in index.html): cookie-free, so no consent
// banner, and custom events are on its free plan. Swap providers by rewriting
// only the body of `track()` — call sites stay the same.
//
// Constraints baked in:
//   * Respects Do Not Track — returns early.
//   * Logs to console in dev instead of sending.
//   * Callers must NOT pass PII (no lat/lng, no user-edited quest titles, no
//     free-text notes, no emails). Keep props to enums, ids, counts, booleans.

type Primitive = string | number | boolean
export type EventProps = Record<string, Primitive>

declare global {
  interface Window {
    umami?: {
      track: (event: string, data?: EventProps) => void
    }
    doNotTrack?: string
  }
  interface Navigator {
    msDoNotTrack?: string
  }
}

const isDev = import.meta.env.DEV

function doNotTrackEnabled(): boolean {
  if (typeof navigator === 'undefined') return false
  const flag =
    navigator.doNotTrack ??
    window.doNotTrack ??
    navigator.msDoNotTrack ??
    null
  return flag === '1' || flag === 'yes'
}

export function track(event: string, props?: EventProps): void {
  if (doNotTrackEnabled()) return

  if (isDev) {
     
    console.log('[analytics]', event, props ?? {})
    return
  }

  if (typeof window === 'undefined') return
  // Undefined when the script is blocked (ad blockers) or failed to load.
  window.umami?.track(event, props)
}
