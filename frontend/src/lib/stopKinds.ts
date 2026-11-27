// The kinds of stop a person can ask for when they swap a stop or add one.
// Mirrors STOP_KIND_SEARCHES in backend/models.py: change one, change both
// (a backend test compares the keys and place types).

import type { StopKind } from '../types/quest'

export interface StopKindOption {
  key: StopKind
  /** On the chip. */
  label: string
  /** The one Google place type the server searches for. */
  placeType: string
  /** Completes "No well-reviewed … found nearby." */
  plural: string
}

export const STOP_KINDS: readonly StopKindOption[] = [
  { key: 'meal', label: 'Food', placeType: 'restaurant', plural: 'restaurants' },
  { key: 'coffee', label: 'Coffee', placeType: 'cafe', plural: 'coffee places' },
  { key: 'dessert', label: 'Dessert', placeType: 'bakery', plural: 'dessert places or bakeries' },
  { key: 'drinks', label: 'Drinks', placeType: 'bar', plural: 'bars' },
  { key: 'walk', label: 'A walk', placeType: 'park', plural: 'parks' },
  { key: 'sights', label: 'Sights', placeType: 'tourist_attraction', plural: 'sights' },
  { key: 'movie', label: 'Movie', placeType: 'movie_theater', plural: 'cinemas' },
  { key: 'bowling', label: 'Bowling', placeType: 'bowling_alley', plural: 'bowling alleys' },
]
