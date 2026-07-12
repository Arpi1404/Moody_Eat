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

export interface StopAlternative extends Stop {
  delta: StopSwapDelta
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
  narrative: string
  /** ISO 8601 datetime string */
  created_at: string
}

export interface QuestGenerationRequest {
  location: string
  occasion: Occasion
  cost_estimate: CostEstimate
  /** 1–20 */
  people: number
  /** Legacy dwell-scaling knob; omit so stops keep their natural pace. */
  duration_hours?: number
  /** Shuffles near-tied picks; omit for the deterministic best plan. */
  variety_seed?: number
  /** 1–4 stops; omit for the occasion default. */
  stop_count?: number
  /** When the outing starts; omit for the occasion's default start time. */
  day_part?: DayPart
}

export type DayPart = 'morning' | 'afternoon' | 'evening' | 'night'
