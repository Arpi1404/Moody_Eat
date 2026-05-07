// Single-point analytics wrapper.
//
// Provider: Plausible (script in index.html). Chosen over Umami for zero-cookie,
// no-consent-banner defaults and a one-line drop-in script. Swap providers by
// rewriting only the body of `track()` — call sites stay the same.
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
    plausible?: (
      event: string,
      options?: { props?: EventProps; callback?: () => void },
    ) => void
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
    // eslint-disable-next-line no-console
    console.log('[analytics]', event, props ?? {})
    return
  }

  if (typeof window === 'undefined') return
  if (typeof window.plausible !== 'function') return
  window.plausible(event, props ? { props } : undefined)
}
