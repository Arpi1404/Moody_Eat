// The cities with hand-made quests, in the order the home page lists them.
// Keep in step with CURATED_CITIES in backend/curated_quests.py.
//
// Quests can be built anywhere; these are only the places where we have also
// put six together by hand. Which one a visitor sees first is a guess from
// roughly where they are — never a prompt, and always theirs to change.

export const CURATED_CITIES = [
  { key: 'hyderabad', name: 'Hyderabad', lat: 17.385, lng: 78.4867 },
  { key: 'bangalore', name: 'Bangalore', lat: 12.9716, lng: 77.5946 },
  { key: 'gurgaon', name: 'Gurgaon', lat: 28.4595, lng: 77.0266 },
] as const

export type CityKey = (typeof CURATED_CITIES)[number]['key']
export type Coords = { lat: number; lng: number }

/** Shown when a visitor is not near any of the cities, or we cannot tell. */
export const DEFAULT_CITY: CityKey = 'hyderabad'

// "In the city" for our purposes: covers each metro's suburbs and airport,
// and puts Delhi and Noida with Gurgaon.
const NEAR_KM = 40

const OTHER_NAMES: Record<string, CityKey> = {
  bengaluru: 'bangalore',
  gurugram: 'gurgaon',
  secunderabad: 'hyderabad',
}

export function cityName(key: CityKey): string {
  return CURATED_CITIES.find((c) => c.key === key)!.name
}

/** A city key from loose text ("Bengaluru", " GURGAON "), or null. */
export function parseCityKey(value: string | null | undefined): CityKey | null {
  const name = value?.trim().toLowerCase()
  if (!name) return null
  return CURATED_CITIES.find((c) => c.key === name)?.key ?? OTHER_NAMES[name] ?? null
}

function distanceKm(a: Coords, b: Coords): number {
  const rad = Math.PI / 180
  const dLat = (b.lat - a.lat) * rad
  const dLng = (b.lng - a.lng) * rad
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(h))
}

/** The curated city this position is in or around, or null when it is
 * somewhere else. */
export function nearestCity(pos: Coords): CityKey | null {
  let best: { key: CityKey; km: number } | null = null
  for (const city of CURATED_CITIES) {
    const km = distanceKm(pos, city)
    if (km <= NEAR_KM && (!best || km < best.km)) best = { key: city.key, km }
  }
  return best?.key ?? null
}

// ── The visitor's own pick ────────────────────────────────────────────────────

const CHOICE_KEY = 'moodyeat_curated_city'

/** The city the visitor last picked on the toggle, if they ever did. */
export function savedCity(): CityKey | null {
  try {
    return parseCityKey(localStorage.getItem(CHOICE_KEY))
  } catch {
    return null
  }
}

export function saveCity(key: CityKey): void {
  try {
    localStorage.setItem(CHOICE_KEY, key)
  } catch {
    // Private mode: the pick just lasts for this visit.
  }
}

// ── Roughly where the visitor is ──────────────────────────────────────────────

export type PositionSource = 'device' | 'ip'
type RoughPosition = Coords & { source: PositionSource }

const POSITION_KEY = 'moodyeat_rough_position'
const IP_LOOKUP_TIMEOUT_MS = 1500
const DEVICE_TIMEOUT_MS = 2500
const DEVICE_MAX_AGE_MS = 10 * 60 * 1000

function readStoredPosition(): RoughPosition | null {
  try {
    const raw = sessionStorage.getItem(POSITION_KEY)
    if (!raw) return null
    const p = JSON.parse(raw) as Partial<RoughPosition>
    if (typeof p.lat !== 'number' || typeof p.lng !== 'number') return null
    return { lat: p.lat, lng: p.lng, source: p.source === 'device' ? 'device' : 'ip' }
  } catch {
    return null
  }
}

let position: RoughPosition | null = readStoredPosition()

/** Record a position we have just learned — from the 📍 button, say. Kept
 * for this tab only, and only to one decimal place (about 11 km). */
export function rememberPosition(pos: Coords, source: PositionSource): void {
  position = {
    lat: Math.round(pos.lat * 10) / 10,
    lng: Math.round(pos.lng * 10) / 10,
    source,
  }
  try {
    sessionStorage.setItem(POSITION_KEY, JSON.stringify(position))
  } catch {
    // Fine — it stays in memory for this page.
  }
}

/** The device's position, but only if the visitor has already allowed this
 * site to read it. Never raises the browser's permission prompt. */
async function devicePositionIfAllowed(): Promise<Coords | null> {
  try {
    if (!navigator.geolocation || !navigator.permissions) return null
    const status = await navigator.permissions.query({ name: 'geolocation' })
    if (status.state !== 'granted') return null
    return await new Promise<Coords | null>((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
        () => resolve(null),
        { timeout: DEVICE_TIMEOUT_MS, maximumAge: DEVICE_MAX_AGE_MS },
      )
    })
  } catch {
    return null
  }
}

/** City-level position from the visitor's IP address (see api/geo.js). Often
 * wrong by a city on mobile data, which is why it only picks a default. */
async function ipPosition(): Promise<Coords | null> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), IP_LOOKUP_TIMEOUT_MS)
  try {
    const res = await fetch('/api/geo', { signal: controller.signal })
    if (!res.ok) return null
    const data = (await res.json()) as Partial<Coords>
    return typeof data.lat === 'number' && typeof data.lng === 'number'
      ? { lat: data.lat, lng: data.lng }
      : null
  } catch {
    // No such endpoint in local dev, or the lookup timed out.
    return null
  } finally {
    window.clearTimeout(timer)
  }
}

/** Best available idea of where the visitor is, without asking them. */
export async function roughPosition(): Promise<RoughPosition | null> {
  if (position) return position
  const [device, ip] = await Promise.all([devicePositionIfAllowed(), ipPosition()])
  if (device) rememberPosition(device, 'device')
  else if (ip) rememberPosition(ip, 'ip')
  return position
}

/** Where location suggestions should lean. A real device position wins; then
 * the city the visitor picked themselves; then the IP guess. */
export function suggestionBias(): Coords | null {
  if (position?.source === 'device') return { lat: position.lat, lng: position.lng }
  const picked = savedCity()
  if (picked) {
    const city = CURATED_CITIES.find((c) => c.key === picked)!
    return { lat: city.lat, lng: city.lng }
  }
  return position ? { lat: position.lat, lng: position.lng } : null
}
