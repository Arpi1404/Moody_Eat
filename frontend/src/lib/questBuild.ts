// Schedule math shared by the quest page (swap/reorder) and the custom quest
// builder. Mirrors the backend travel model (quest_generator.py) so
// client-side recomputes match what the generator would have produced.

import type { PlaceItem } from '../api'
import type {
  CostEstimate,
  DayPart,
  Occasion,
  Quest,
  Stop,
  StopCategory,
  TravelMode,
} from '../types/quest'

// ── Time helpers ──────────────────────────────────────────────────────────────

export function toMinutes(hhmm: string): number {
  const [hStr, mStr] = hhmm.split(':')
  return parseInt(hStr, 10) * 60 + parseInt(mStr, 10)
}

export function addMinutes(hhmm: string, minutes: number): string {
  const total = toMinutes(hhmm) + minutes
  const day = 24 * 60
  const wrapped = ((total % day) + day) % day
  const h = Math.floor(wrapped / 60)
  const m = wrapped % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`
}

export function durationMinutes(start: string, end: string): number {
  let delta = toMinutes(end) - toMinutes(start)
  if (delta < 0) delta += 24 * 60
  return delta
}

export function questDuration(stops: Stop[]): number {
  if (stops.length === 0) return 0
  return durationMinutes(
    stops[0].time_block_start,
    stops[stops.length - 1].time_block_end,
  )
}

// ── Travel model (mirrors backend) ────────────────────────────────────────────

const WALK_M_PER_MIN = 80
const DRIVE_M_PER_MIN = 350
const WALK_THRESHOLD_M = 1400

export function haversineM(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number,
): number {
  const R = 6_371_000
  const rad = (d: number) => (d * Math.PI) / 180
  const dLat = rad(lat2 - lat1)
  const dLng = rad(lng2 - lng1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, a)))
}

export function travelLeg(
  from: Stop,
  to: Stop,
): { minutes: number; mode: TravelMode } {
  const dist = haversineM(from.place.lat, from.place.lng, to.place.lat, to.place.lng)
  if (dist <= WALK_THRESHOLD_M) {
    return { minutes: Math.max(1, Math.round(dist / WALK_M_PER_MIN)), mode: 'walking' }
  }
  return { minutes: Math.max(1, Math.round(dist / DRIVE_M_PER_MIN)), mode: 'driving' }
}

// Recompute every leg from geometry: changing any stop (swap, reorder, or
// assembling a custom quest) changes the travel time AND mode of the legs
// around it. Each stop keeps its dwell; the first stop's start anchors the
// chain.
export function rescheduleStops(stops: Stop[]): Stop[] {
  for (let i = 0; i < stops.length; i += 1) {
    const dwell = durationMinutes(
      stops[i].time_block_start,
      stops[i].time_block_end,
    )
    if (i > 0) {
      const leg = travelLeg(stops[i - 1], stops[i])
      stops[i - 1] = {
        ...stops[i - 1],
        travel_to_next_minutes: leg.minutes,
        travel_mode: leg.mode,
      }
      const nextStart = addMinutes(stops[i - 1].time_block_end, leg.minutes)
      stops[i] = {
        ...stops[i],
        time_block_start: nextStart,
        time_block_end: addMinutes(nextStart, dwell),
      }
    }
  }
  const last = stops.length - 1
  stops[last] = { ...stops[last], travel_to_next_minutes: null, travel_mode: null }
  return stops
}

// ── Custom quest assembly ─────────────────────────────────────────────────────

// Mirrors backend _DWELL (minutes per stop category).
const DWELL_BY_CATEGORY: Record<StopCategory, number> = {
  restaurant: 60,
  bar: 45,
  cafe: 40,
  activity: 60,
  attraction: 30,
  other: 30,
}

const CATEGORY_BY_TYPE: Record<string, StopCategory> = {
  restaurant: 'restaurant',
  meal_takeaway: 'restaurant',
  cafe: 'cafe',
  bakery: 'cafe',
  bar: 'bar',
  night_club: 'bar',
  park: 'attraction',
  tourist_attraction: 'attraction',
  museum: 'attraction',
  art_gallery: 'attraction',
  zoo: 'attraction',
  aquarium: 'attraction',
  amusement_park: 'activity',
  bowling_alley: 'activity',
  movie_theater: 'activity',
  shopping_mall: 'activity',
  stadium: 'activity',
  spa: 'activity',
  book_store: 'other',
  library: 'other',
}

export function categoryForPlace(place: PlaceItem): StopCategory {
  for (const t of place.types ?? []) {
    const category = CATEGORY_BY_TYPE[t]
    if (category) return category
  }
  return 'other'
}

// Mirrors backend _DAY_PART_START.
const DAY_PART_START: Record<DayPart, string> = {
  morning: '10:00',
  afternoon: '13:00',
  evening: '17:30',
  night: '20:00',
}

// Mirrors backend PRICE_LEVEL_BANDS_INR for places with only a price level.
const LEVEL_BANDS_INR: Record<number, [number, number]> = {
  0: [0, 0],
  1: [100, 350],
  2: [350, 900],
  3: [900, 1800],
  4: [1800, 3500],
}

function estBand(place: PlaceItem): { min: number; max: number; source: string } | null {
  if (place.price_range_start_inr != null || place.price_range_end_inr != null) {
    const lo = place.price_range_start_inr ?? place.price_range_end_inr!
    const hi = place.price_range_end_inr ?? place.price_range_start_inr!
    return { min: lo, max: hi, source: 'google_price_range' }
  }
  if (place.price_level != null) {
    const band = LEVEL_BANDS_INR[Math.max(0, Math.min(4, place.price_level))]
    return { min: band[0], max: band[1], source: 'google_price_level' }
  }
  return null
}

function whyLine(place: PlaceItem): string {
  if (place.rating != null && place.rating >= 4.3) {
    return `Rated ${place.rating.toFixed(1)}★ by locals — your hand-picked stop.`
  }
  return 'Hand-picked by you.'
}

function customNarrative(names: string[], occasion: Occasion, area: string): string {
  const where = area ? ` in ${area}` : ''
  if (names.length === 1) {
    return `A custom ${occasion} plan${where}, anchored around ${names[0]}.`
  }
  const mid = names.slice(0, -1).join(', ')
  return `A custom ${occasion} plan${where}: starting at ${mid}, then finishing at ${names[names.length - 1]}.`
}

function costTierFromTotal(midTotal: number | null): CostEstimate {
  if (midTotal == null) return 'mid'
  if (midTotal <= 700) return 'cheap'
  if (midTotal <= 2000) return 'mid'
  return 'splurge'
}

export function buildCustomQuest(opts: {
  places: PlaceItem[]
  occasion: Occasion
  dayPart: DayPart
  area: string
  /** Optional creator display name — titles the quest "Priya's … Quest". */
  createdBy?: string
}): Quest {
  const { places, occasion, dayPart, area, createdBy } = opts
  const start = DAY_PART_START[dayPart]

  // Lay stops out back-to-back from the day-part start, then let the shared
  // reschedule pass insert real travel legs between them.
  let cursor = `${start}:00`
  const initial: Stop[] = places.map((place) => {
    const category = categoryForPlace(place)
    const dwell = DWELL_BY_CATEGORY[category]
    const band = estBand(place)
    const stop: Stop = {
      place,
      category,
      time_block_start: cursor,
      time_block_end: addMinutes(cursor, dwell),
      travel_to_next_minutes: null,
      travel_mode: null,
      why_this_place: whyLine(place),
      est_cost_per_person_min_inr: band?.min ?? null,
      est_cost_per_person_max_inr: band?.max ?? null,
      price_source: band?.source ?? null,
    }
    cursor = stop.time_block_end
    return stop
  })
  const stops = rescheduleStops(initial)

  const priced = stops.filter((s) => s.est_cost_per_person_min_inr != null)
  const totalMin = priced.length
    ? priced.reduce((sum, s) => sum + (s.est_cost_per_person_min_inr ?? 0), 0)
    : null
  const totalMax = priced.length
    ? priced.reduce((sum, s) => sum + (s.est_cost_per_person_max_inr ?? 0), 0)
    : null
  const midTotal =
    totalMin != null && totalMax != null ? (totalMin + totalMax) / 2 : null

  const areaShort = area.split(',')[0].trim()
  const creator = createdBy?.trim() || null
  // "Priya" → "Priya's"; names already ending in s just get an apostrophe.
  const possessive = creator
    ? /s$/i.test(creator)
      ? `${creator}'`
      : `${creator}'s`
    : null
  const title = possessive
    ? `${possessive} ${areaShort || 'Custom'} Quest`
    : areaShort
      ? `My ${areaShort} Quest`
      : 'My Custom Quest'
  return {
    id: crypto.randomUUID(),
    title,
    occasion,
    stops,
    created_by: creator,
    total_duration_minutes: questDuration(stops),
    total_cost_estimate: costTierFromTotal(midTotal),
    est_total_per_person_min_inr: totalMin,
    est_total_per_person_max_inr: totalMax,
    narrative: customNarrative(stops.map((s) => s.place.name), occasion, areaShort),
    created_at: new Date().toISOString(),
  }
}
