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

type Leg = { minutes: number; mode: TravelMode }

// Re-time a stop list: each stop keeps its dwell and the first stop's start
// anchors the chain. `legFor` says how long each hop takes; by default every
// one is worked out from geometry, which is right for a quest being assembled.
// An edit passes keptLegs() instead.
export function rescheduleStops(
  stops: Stop[],
  legFor: (from: Stop, to: Stop) => Leg = travelLeg,
): Stop[] {
  for (let i = 0; i < stops.length; i += 1) {
    const dwell = durationMinutes(
      stops[i].time_block_start,
      stops[i].time_block_end,
    )
    if (i > 0) {
      const leg = legFor(stops[i - 1], stops[i])
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

// ── Editing a quest ───────────────────────────────────────────────────────────

/** The most stops a quest can be built up to. Mirrors _MAX_QUEST_STOPS in
 * backend/routes.py. */
export const MAX_STOPS = 4

/** What makes a stop the same stop from one version of a quest to the next. */
const stopKey = ({ place }: Stop): string =>
  place.provider_id || `${place.name}|${place.lat}|${place.lng}`

/** Two stops that were already next to each other, in either order, keep the
 * travel time and mode the quest had between them. Only the hops an edit
 * creates are worked out afresh. Hand-made quests write these by hand, and a
 * straight line cannot tell how a walk really goes. */
function keptLegs(before: Stop[]): (from: Stop, to: Stop) => Leg {
  const stored = new Map<string, Leg>()
  for (let i = 0; i + 1 < before.length; i += 1) {
    const { travel_to_next_minutes: minutes, travel_mode: mode } = before[i]
    if (minutes == null || mode == null) continue
    stored.set(JSON.stringify([stopKey(before[i]), stopKey(before[i + 1])]), {
      minutes,
      mode,
    })
  }
  return (from, to) =>
    stored.get(JSON.stringify([stopKey(from), stopKey(to)])) ??
    stored.get(JSON.stringify([stopKey(to), stopKey(from)])) ??
    travelLeg(from, to)
}

/** The notes about distance that _why() in backend/quest_generator.py writes
 * into why_this_place. Each describes the leg from the stop before. */
const DISTANCE_NOTES = [
  'just a short walk away',
  'an easy walk from the previous stop',
  'a quick ride from the previous stop',
]

function withoutDistanceNote(stop: Stop): Stop {
  const parts = stop.why_this_place.replace(/\.$/, '').split(', ')
  const kept = parts.filter((part) => !DISTANCE_NOTES.includes(part.toLowerCase()))
  if (kept.length === parts.length) return stop
  const line = kept.join(', ') || 'a solid local choice'
  return { ...stop, why_this_place: `${line[0].toUpperCase()}${line.slice(1)}.` }
}

/** "A short walk away" only holds while the stop before stays the same. A stop
 * that is new to the quest keeps its note: it was written for the stop it now
 * follows. A first stop has nothing before it, so it never keeps one. */
function dropStaleDistanceNotes(before: Stop[], after: Stop[]): Stop[] {
  const previousBefore = new Map(
    before.map((stop, i) => [stop.place.provider_id, before[i - 1]?.place.provider_id]),
  )
  return after.map((stop, i) => {
    const id = stop.place.provider_id
    const unchanged =
      i > 0 &&
      (!previousBefore.has(id) ||
        previousBefore.get(id) === after[i - 1].place.provider_id)
    return unchanged ? stop : withoutDistanceNote(stop)
  })
}

/** Per-person totals, summed as the generator sums them: a stop with no
 * estimate adds nothing. A quest that had no total (the hand-made ones carry
 * no prices at all) only gains one once every stop has an estimate, so one new
 * stop's price is never shown as the price of the whole outing. */
function editedTotals(
  before: Quest,
  stops: Stop[],
): { min: number | null; max: number | null } {
  const priced = stops.filter((s) => s.est_cost_per_person_min_inr != null)
  const hadTotal = before.est_total_per_person_min_inr != null
  if (priced.length === 0 || (!hadTotal && priced.length < stops.length)) {
    return { min: null, max: null }
  }
  return {
    min: priced.reduce((sum, s) => sum + (s.est_cost_per_person_min_inr ?? 0), 0),
    max: priced.reduce((sum, s) => sum + (s.est_cost_per_person_max_inr ?? 0), 0),
  }
}

/** The quest with an already-timed stop list: why-lines, length and totals
 * follow it. */
function withTimedStops(quest: Quest, timed: Stop[]): Quest {
  const stops = dropStaleDistanceNotes(quest.stops, timed)
  const totals = editedTotals(quest, stops)
  return {
    ...quest,
    stops,
    total_duration_minutes: questDuration(stops),
    est_total_per_person_min_inr: totals.min,
    est_total_per_person_max_inr: totals.max,
  }
}

/** The quest with a new stop list, re-timed from its first stop. Everything an
 * edit can change is recomputed here except the narrative, which the quest page
 * owns. Hops between stops that were already neighbours are left as they were. */
export function withStops(quest: Quest, stops: Stop[]): Quest {
  const timed = rescheduleStops(
    stops.map((stop) => ({ ...stop })),
    keptLegs(quest.stops),
  )
  return withTimedStops(quest, timed)
}

/** Whatever lands first keeps the quest's start time (and its own dwell). */
function startingAt(stops: Stop[], start: string): Stop[] {
  const dwell = durationMinutes(stops[0].time_block_start, stops[0].time_block_end)
  return [
    { ...stops[0], time_block_start: start, time_block_end: addMinutes(start, dwell) },
    ...stops.slice(1),
  ]
}

/** The quest with the stop at `from` moved to `to`. */
export function reorderStops(quest: Quest, from: number, to: number): Quest {
  if (from === to || to < 0 || to >= quest.stops.length) return quest
  const stops = [...quest.stops]
  const [moved] = stops.splice(from, 1)
  stops.splice(to, 0, moved)
  return withStops(quest, startingAt(stops, quest.stops[0].time_block_start))
}

/** The same quest without one stop. A quest keeps at least one, so removing the
 * only stop returns the quest unchanged. */
export function removeStop(quest: Quest, index: number): Quest {
  if (quest.stops.length <= 1 || index < 0 || index >= quest.stops.length) {
    return quest
  }
  const rest = quest.stops.filter((_, i) => i !== index)
  if (index === rest.length) {
    // The last stop: nothing before it moves.
    rest[index - 1] = {
      ...rest[index - 1],
      travel_to_next_minutes: null,
      travel_mode: null,
    }
    return withTimedStops(quest, rest)
  }
  return withStops(quest, startingAt(rest, quest.stops[0].time_block_start))
}

// Mirrors OUTDOOR_TYPES in backend/services/weather_service.py.
const OUTDOOR_TYPES = ['park', 'zoo', 'amusement_park']

/** The generator's rain note says the plan was kept indoors, which stops being
 * true once someone adds somewhere outdoors. The forecast still stands. */
function withHonestRainNote(quest: Quest, added: Stop): Quest {
  const outdoors = added.place.types?.some((t) => OUTDOOR_TYPES.includes(t))
  if (!quest.weather_note || !outdoors) return quest
  return { ...quest, weather_note: 'Rain looks likely around your start time.' }
}

/** The quest with the stop at `index` replaced. */
export function replaceStop(quest: Quest, index: number, stop: Stop): Quest {
  const stops = quest.stops.map((current, i) => (i === index ? stop : current))
  return withHonestRainNote(withStops(quest, stops), stop)
}

/** The quest with `stop` added right after the stop at `index`. */
export function insertStopAfter(quest: Quest, index: number, stop: Stop): Quest {
  const stops = [
    ...quest.stops.slice(0, index + 1),
    stop,
    ...quest.stops.slice(index + 1),
  ]
  return withHonestRainNote(withStops(quest, stops), stop)
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

/** The tag that decides what sort of stop a place makes. */
function decidingType(place: PlaceItem): string | undefined {
  return (place.types ?? []).find((t) => CATEGORY_BY_TYPE[t])
}

export function categoryForPlace(place: PlaceItem): StopCategory {
  const type = decidingType(place)
  return type ? CATEGORY_BY_TYPE[type] : 'other'
}

/** A film outlasts the other activities. Mirrors FILM_MINUTES in
 * backend/models.py. */
export const FILM_MINUTES = 150

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
    const dwell =
      decidingType(place) === 'movie_theater'
        ? FILM_MINUTES
        : DWELL_BY_CATEGORY[category]
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
