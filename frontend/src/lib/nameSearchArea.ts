// Where a search by name is anchored. The server has to geocode an area that
// arrives as text, which is a second billed Google call, so text is sent only
// when there is nothing better: coordinates are sent whenever we have them.

/** What the 📍 button puts in the location field. */
export const COORDINATES_RE = /^(-?\d+\.\d+),\s*(-?\d+\.\d+)$/

/** The server's answer for an area it geocoded. */
export type ResolvedArea = { lat: number; lng: number; name: string }

/** The same area however it was spaced or capitalised. */
export function areaKey(typed: string): string {
  return typed.trim().replace(/\s+/g, ' ').toLowerCase()
}

function parseCoordinates(text: string): { lat: number; lng: number } | null {
  const match = COORDINATES_RE.exec(text)
  if (!match) return null
  const lat = Number(match[1])
  const lng = Number(match[2])
  return Math.abs(lat) <= 90 && Math.abs(lng) <= 180 ? { lat, lng } : null
}

/** What to send for the area in the location field.
 *
 * `picked` is a chosen suggestion; `remembered` holds, by areaKey, the typed
 * areas this page has already had geocoded. `knownName` is what the server
 * once called the area: it sends no name back for coordinates. */
export function nameSearchAnchor(
  field: string,
  picked: { lat: number; lng: number } | null,
  remembered: ReadonlyMap<string, ResolvedArea>,
): {
  send: { lat: number; lng: number } | { area: string }
  knownName: string
} {
  if (picked) {
    return { send: { lat: picked.lat, lng: picked.lng }, knownName: '' }
  }
  const typed = field.trim()
  const coordinates = parseCoordinates(typed)
  if (coordinates) return { send: coordinates, knownName: '' }
  const seen = remembered.get(areaKey(typed))
  if (seen) {
    return { send: { lat: seen.lat, lng: seen.lng }, knownName: seen.name }
  }
  return { send: { area: typed }, knownName: '' }
}
