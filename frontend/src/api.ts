import type { Quest, StopAlternative, StopKind } from './types/quest'

const DEFAULT_BASE = 'http://127.0.0.1:8000'

export function getApiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE
}

/** What a person sees when the server's limit on new quests is reached. */
export const TOO_MANY_QUESTS =
  "That's a lot of quests at once. Wait a minute, then try again."

export async function generateQuest(payload: {
  /** Typed area, or "lat,lng" when the device's position is used. */
  location: string
  /** Readable area for a "lat,lng" location — names the quest, display only. */
  location_label?: string
  occasion: string
  cost_estimate: string
  people: number
  /** Legacy dwell-scaling knob; omit so stops keep their natural pace. */
  duration_hours?: number
  /** Shuffles near-tied picks; omit for the deterministic best plan. */
  variety_seed?: number
  /** 1–4 stops; omit for the occasion default. */
  stop_count?: number
  /** When the outing starts; omit for the occasion's default start time. */
  day_part?: string
  /** Recently seen places to avoid (soft — never at the cost of a stop). */
  exclude_place_ids?: string[]
}): Promise<Quest> {
  const res = await fetch(`${getApiBase()}/api/quest/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (res.status === 429) throw new Error(TOO_MANY_QUESTS)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const detail =
      typeof data.detail === 'string'
        ? data.detail
        : (data.detail as { message?: string })?.message ??
          'Could not generate quest.'
    throw new Error(detail)
  }
  return res.json()
}

/** Store a quest server-side for short-link sharing. Returns the short id. */
export async function storeQuestForShare(quest: Quest): Promise<string> {
  const res = await fetch(`${getApiBase()}/api/quest/store`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(quest),
  })
  if (!res.ok) {
    throw new Error('Could not store quest for sharing.')
  }
  const data: { short_id?: string } = await res.json()
  if (!data.short_id) {
    throw new Error('Could not store quest for sharing.')
  }
  return data.short_id
}

/** Fetch a quest stored behind a /q/<shortId> share link. Counts a view. */
export async function fetchStoredQuest(shortId: string): Promise<Quest> {
  const res = await fetch(
    `${getApiBase()}/api/quest/stored/${encodeURIComponent(shortId)}`,
  )
  if (!res.ok) {
    throw new Error(
      res.status === 404
        ? 'This shared quest link does not exist — check for typos.'
        : 'Could not load the shared quest.',
    )
  }
  return res.json()
}

export async function fetchCuratedQuests(city: string): Promise<Quest[]> {
  const params = new URLSearchParams({ city })
  const res = await fetch(`${getApiBase()}/api/quests/curated?${params}`)
  if (!res.ok) {
    throw new Error('Could not load curated quests.')
  }
  const data: Quest[] = await res.json()
  return Array.isArray(data) ? data : []
}

/** One curated quest by id — lets a curated link open on a device that has
 * never seen the home page. */
export async function fetchCuratedQuest(id: string): Promise<Quest> {
  const res = await fetch(
    `${getApiBase()}/api/quests/curated/${encodeURIComponent(id)}`,
  )
  if (!res.ok) throw new Error('Curated quest not found.')
  return res.json()
}

// The site can go out before the server does. Until then the server has no
// route for adding a stop, and ignores a requested kind.
const NOT_AVAILABLE_YET =
  'This is not available yet. Try again later. Your quest is unchanged.'

/** One paid places search: options to put at, or after, one stop. */
async function fetchStopOptions(
  quest: Quest,
  stopIndex: number,
  route: 'alternatives' | 'additions',
  kind: StopKind | null,
): Promise<StopAlternative[]> {
  const query = kind ? `?kind=${kind}` : ''
  const res = await fetch(
    `${getApiBase()}/api/quest/${quest.id}/stop/${stopIndex}/${route}${query}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(quest),
    },
  )
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    if (res.status === 404 && data.detail === 'Not Found') {
      throw new Error(NOT_AVAILABLE_YET)
    }
    const detail =
      typeof data.detail === 'string'
        ? data.detail
        : (data.detail as { message?: string })?.message ??
          'Could not load alternatives.'
    throw new Error(detail)
  }
  const options: StopAlternative[] = await res.json()
  // Without the echo these are the old same-type results: showing them under
  // the chosen kind would mislabel them.
  if (kind && options.some((option) => option.kind !== kind)) {
    throw new Error(NOT_AVAILABLE_YET)
  }
  return options
}

/** Replacements for a stop: the same type as now, or of `kind`. */
export function fetchStopAlternatives(
  quest: Quest,
  stopIndex: number,
  kind: StopKind | null = null,
): Promise<StopAlternative[]> {
  return fetchStopOptions(quest, stopIndex, 'alternatives', kind)
}

/** Places of one kind that could be added right after a stop. */
export function fetchStopAdditions(
  quest: Quest,
  afterIndex: number,
  kind: StopKind,
): Promise<StopAlternative[]> {
  return fetchStopOptions(quest, afterIndex, 'additions', kind)
}

export type PlaceItem = {
  name: string
  address: string
  lat: number
  lng: number
  distance_meters: number
  rating?: number | null
  user_ratings_total?: number | null
  /** Google Places price level: 0=free, 1=inexpensive, 2=moderate, 3=expensive, 4=very expensive. */
  price_level?: number | null
  /** Per-person price range in INR from Places API (New). null when unknown. */
  price_range_start_inr?: number | null
  price_range_end_inr?: number | null
  business_status?: string | null
  types?: string[] | null
  /** What Google says the place mainly is, e.g. "pizza_restaurant". null when unknown. */
  primary_type?: string | null
  provider_id: string
  /** "HH:MM" 24-hour, today only. null when unknown. */
  opens_today?: string | null
  /** "HH:MM" 24-hour, today only. null when unknown. */
  closes_today?: string | null
  /** True when the place is open 24h today. */
  open_24h_today?: boolean
}

export type NearbyPlacesResponse = {
  resolved_location: { name: string; lat: number; lng: number }
  places: PlaceItem[]
  count: number
}

export async function searchNearbyPlaces(payload: {
  query: string
  categories: string[]
  radius_meters: number
  limit: number
}): Promise<NearbyPlacesResponse> {
  const res = await fetch(`${getApiBase()}/api/places/nearby`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const detail =
      typeof data.detail === 'string'
        ? data.detail
        : (data.detail as { message?: string })?.message ??
          'Nearby search failed.'
    throw new Error(detail)
  }
  return res.json()
}

/** One row of the location dropdown: "Banjara Hills" / "Hyderabad, Telangana, India". */
export type LocationSuggestion = {
  place_id: string
  main_text: string
  secondary_text: string
}

/** Places matching what has been typed so far. `session` groups the
 * keystrokes of one search for billing (see fetchSuggestionLocation).
 * `near` is a rough position; places around it are offered first. */
export async function fetchLocationSuggestions(
  text: string,
  session: string,
  signal?: AbortSignal,
  near?: { lat: number; lng: number } | null,
): Promise<LocationSuggestion[]> {
  const params = new URLSearchParams({ q: text, session })
  if (near) {
    // One decimal place (about 11 km) is plenty to rank by, and no more
    // precise than it needs to be.
    params.set('lat', near.lat.toFixed(1))
    params.set('lng', near.lng.toFixed(1))
  }
  const res = await fetch(`${getApiBase()}/api/places/autocomplete?${params}`, {
    signal,
  })
  if (!res.ok) throw new Error('Suggestions unavailable.')
  const data = (await res.json()) as { suggestions?: LocationSuggestion[] }
  return data.suggestions ?? []
}

/** Coordinates of a picked suggestion. Sending the same `session` the
 * suggestions were fetched with closes that search for billing. */
export async function fetchSuggestionLocation(
  placeId: string,
  session: string,
): Promise<{ lat: number; lng: number }> {
  const params = new URLSearchParams({ place_id: placeId, session })
  const res = await fetch(
    `${getApiBase()}/api/places/autocomplete/location?${params}`,
  )
  if (!res.ok) throw new Error('Location unavailable.')
  return res.json()
}

export async function fetchPlaceBlurbs(payload: {
  mood: string
  budget: string
  people: number
  places: {
    provider_id: string
    name: string
    types?: string[] | null
  }[]
}): Promise<Record<string, string>> {
  const res = await fetch(`${getApiBase()}/api/places/blurbs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mood: payload.mood,
      budget: payload.budget,
      people: payload.people,
      places: payload.places.map((p) => ({
        provider_id: p.provider_id,
        name: p.name,
        types: p.types ?? [],
      })),
    }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const detail =
      typeof data.detail === 'string'
        ? data.detail
        : (data.detail as { message?: string })?.message ??
          'Blurbs request failed.'
    throw new Error(detail)
  }
  const data: { blurbs?: Record<string, string> } = await res.json()
  return data.blurbs ?? {}
}
