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
}
