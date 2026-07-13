import type { Quest, StopAlternative } from './types/quest'

const DEFAULT_BASE = 'http://127.0.0.1:8000'

export function getApiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE
}

export async function generateQuest(payload: {
  location: string
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

export async function fetchCuratedQuests(city: string): Promise<Quest[]> {
  const params = new URLSearchParams({ city })
  const res = await fetch(`${getApiBase()}/api/quests/curated?${params}`)
  if (!res.ok) {
    throw new Error('Could not load curated quests.')
  }
  const data: Quest[] = await res.json()
  return Array.isArray(data) ? data : []
}

export async function fetchStopAlternatives(
  quest: Quest,
  stopIndex: number,
): Promise<StopAlternative[]> {
  const res = await fetch(
    `${getApiBase()}/api/quest/${quest.id}/stop/${stopIndex}/alternatives`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(quest),
    },
  )
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const detail =
      typeof data.detail === 'string'
        ? data.detail
        : (data.detail as { message?: string })?.message ??
          'Could not load alternatives.'
    throw new Error(detail)
  }
  return res.json()
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
