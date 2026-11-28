import type { PlaceItem } from '../api'

export type Occasion = 'date' | 'friends' | 'solo' | 'family'

export type CostEstimate = 'cheap' | 'mid' | 'splurge'

export type TravelMode = 'walking' | 'cycling' | 'transit' | 'driving'

export type StopCategory =
  | 'cafe'
  | 'restaurant'
  | 'bar'
  | 'activity'
  | 'attraction'
  | 'other'

export interface Stop {
  place: PlaceItem
  category: StopCategory
  /** HH:MM (24-hour) */
  time_block_start: string
  /** HH:MM (24-hour) */
  time_block_end: string
  /** null on the final stop */
  travel_to_next_minutes: number | null
  /** null on the final stop */
  travel_mode: TravelMode | null
  why_this_place: string
  /** True when why_this_place is a note the quest's creator typed. */
  note_by_creator?: boolean | null
  /** Estimated per-person spend at this stop in INR. null when no price signal. */
  est_cost_per_person_min_inr?: number | null
  est_cost_per_person_max_inr?: number | null
  /** 'google_price_range' | 'google_price_level' | 'heuristic'. null when unknown. */
  price_source?: string | null
}

export interface StopSwapDelta {
  cost_change: number
  time_change_minutes: number
  distance_change_meters: number
}

/** What a person can ask for when swapping or adding a stop. */
export type StopKind =
  | 'meal'
  | 'coffee'
  | 'dessert'
  | 'drinks'
  | 'walk'
  | 'sights'
  | 'movie'
  | 'bowling'

export interface StopAlternative extends Stop {
  delta: StopSwapDelta
  /** The kind asked for, echoed back. Absent from servers that predate it. */
  kind?: StopKind | null
}

/** Who chose a quest's stops: the engine, an editor, or the person. */
export type QuestOrigin = 'generated' | 'curated' | 'custom'

export type Weekday =
  | 'monday'
  | 'tuesday'
  | 'wednesday'
  | 'thursday'
  | 'friday'
  | 'saturday'
  | 'sunday'

/** One of a quest's own stops. */
export interface StopRef {
  stop_index: number
  /** The place at that stop: the reference follows it if stops are moved. */
  place_id?: string | null
}

/** A weekday a catalogue quest does not work, and the stop that is why. */
export interface ClosedDay extends StopRef {
  day: Weekday
}

export interface Quest {
  /** UUID v4 */
  id: string
  title: string
  occasion: Occasion
  stops: Stop[]
  total_duration_minutes: number
  total_cost_estimate: CostEstimate
  /** Sum of per-stop INR estimates. null when no stop had a price signal. */
  est_total_per_person_min_inr?: number | null
  est_total_per_person_max_inr?: number | null
  /** Present when the rain forecast changed how the quest was planned. */
  weather_note?: string | null
  /** The day the outing is for, "YYYY-MM-DD", local to the place. Generated
   * quests only; absent on catalogue quests and on any made before it existed. */
  outing_date?: string | null
  /** Why the start is later than the time chosen (it had already passed). */
  start_note?: string | null
  /** True when `narrative` is an intro the quest's creator typed. It is then
   * never rewritten. */
  narrative_by_creator?: boolean | null
  /** Display name of the custom-quest creator ("Priya's Old City Crawl"). */
  created_by?: string | null
  /** Absent on quests made before the field existed. */
  origin?: QuestOrigin | null
  /** Catalogue quests only; absent when the quest works all week. */
  closed_days?: ClosedDay[] | null
  /** Catalogue quests only: one line on who the quest is for. */
  audience_line?: string | null
  /** The stop whose photo leads the quest; the first when absent. */
  photo_stop?: StopRef | null
  narrative: string
  /** ISO 8601 datetime string */
  created_at: string
}

export interface QuestGenerationRequest {
  /** Typed area, or "lat,lng" when the device's position is used. */
  location: string
  /** Readable area for a "lat,lng" location — names the quest, display only. */
  location_label?: string
  occasion: Occasion
  cost_estimate: CostEstimate
  /** 1–20 */
  people: number
  /** Legacy dwell-scaling knob; omit so stops keep their natural pace. */
  duration_hours?: number
  /** Shuffles near-tied picks; omit for the deterministic best plan. */
  variety_seed?: number
  /** 1–4 stops; omit for the default (2). */
  stop_count?: number
  /** When the outing starts; omit for the occasion's default start time. */
  day_part?: DayPart
  /** Recently seen places to avoid (soft — never at the cost of a stop). */
  exclude_place_ids?: string[]
  /** The day, "YYYY-MM-DD", within the coming week. Omit for today. */
  start_date?: string
  /** "HH:MM", 07:00–22:00, local to the place. Wins over day_part. */
  start_time?: string
}

export type DayPart = 'morning' | 'afternoon' | 'evening' | 'night'
