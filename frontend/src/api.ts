const DEFAULT_BASE = 'http://127.0.0.1:8000'

export function getApiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE
}

export async function fetchUserName(): Promise<string> {
  const res = await fetch(`${getApiBase()}/name`)
  if (!res.ok) {
    throw new Error('Could not load your name from the server.')
  }
  const data: { name?: string } = await res.json()
  return data.name?.trim() || 'Traveler'
}

export type Cafe = {
  name: string
  address: string
  distance_minutes_walk: number
  vibe: string
}

export type QuestResponse = {
  location: string
  mood: string
  cafes: Cafe[]
}

export async function generateQuest(
  location: string,
  mood: string,
): Promise<QuestResponse> {
  const res = await fetch(`${getApiBase()}/api/generate-quest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ location, mood }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const detail =
      typeof data.detail === 'string'
        ? data.detail
        : (data.detail as { message?: string })?.message ??
          'Unable to generate suggestions.'
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
  business_status?: string | null
  types?: string[] | null
  provider_id: string
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
