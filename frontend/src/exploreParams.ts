/** Serialize / deserialize /plan and /results query strings. */

export const MOODS = [
  { value: 'cozy', label: 'Cozy' },
  { value: 'productive', label: 'Productive' },
] as const

export const PLACE_TYPES: { value: string; label: string }[] = [
  { value: 'cafe', label: 'Café' },
  { value: 'restaurant', label: 'Restaurant' },
  { value: 'bar', label: 'Bar' },
  { value: 'bakery', label: 'Bakery' },
  { value: 'meal_takeaway', label: 'Takeaway' },
  { value: 'meal_delivery', label: 'Delivery' },
]

export const BUDGETS = [
  { value: 'low', label: 'Budget-friendly' },
  { value: 'mid', label: 'Mid-range' },
  { value: 'high', label: 'Splurge' },
] as const

export type MoodValue = (typeof MOODS)[number]['value']
export type BudgetValue = (typeof BUDGETS)[number]['value']

export type ExploreFilters = {
  destination: string
  mood: MoodValue
  people: number
  types: string[]
  minRating: number
  budget: BudgetValue
  radiusKm: number
}

const DEFAULT_FILTERS: ExploreFilters = {
  destination: 'Paris',
  mood: 'cozy',
  people: 2,
  types: ['cafe', 'restaurant'],
  minRating: 3.5,
  budget: 'mid',
  radiusKm: 3,
}

function isMood(s: string): s is MoodValue {
  return MOODS.some((m) => m.value === s)
}

function isBudget(s: string): s is BudgetValue {
  return BUDGETS.some((b) => b.value === s)
}

export function filtersToSearchParams(f: ExploreFilters): URLSearchParams {
  const sp = new URLSearchParams()
  sp.set('q', f.destination)
  sp.set('mood', f.mood)
  sp.set('people', String(f.people))
  sp.set('types', f.types.join(','))
  sp.set('minRating', String(f.minRating))
  sp.set('budget', f.budget)
  sp.set('radius', String(f.radiusKm))
  return sp
}

/** Returns null if `q` (destination) is missing — invalid /results URL. */
export function searchParamsToFilters(sp: URLSearchParams): ExploreFilters | null {
  const q = sp.get('q')?.trim()
  if (!q) return null

  const moodRaw = sp.get('mood')?.trim() || 'cozy'
  const mood = isMood(moodRaw) ? moodRaw : DEFAULT_FILTERS.mood

  const people = Math.min(
    50,
    Math.max(1, Math.round(Number.parseInt(sp.get('people') || '2', 10) || 2)),
  )

  const typesRaw = sp.get('types')?.trim()
  const types = typesRaw
    ? typesRaw
        .split(',')
        .map((t) => t.trim().toLowerCase())
        .filter(Boolean)
    : [...DEFAULT_FILTERS.types]
  const typesNorm =
    types.length > 0 ? types : [...DEFAULT_FILTERS.types]

  const minRating = Math.min(
    5,
    Math.max(1, Number.parseFloat(sp.get('minRating') || '3.5') || 3.5),
  )

  const budgetRaw = sp.get('budget')?.trim() || 'mid'
  const budget = isBudget(budgetRaw) ? budgetRaw : DEFAULT_FILTERS.budget

  const radiusKm = Math.min(
    10,
    Math.max(0.5, Number.parseFloat(sp.get('radius') || '3') || 3),
  )

  return {
    destination: q,
    mood,
    people,
    types: typesNorm,
    minRating,
    budget,
    radiusKm,
  }
}

export function mergeFiltersFromSearchParams(
  sp: URLSearchParams,
): ExploreFilters {
  return searchParamsToFilters(sp) ?? DEFAULT_FILTERS
}

const HIDE_PLACE_TYPES = new Set([
  'establishment',
  'point_of_interest',
  'premise',
  'political',
  'route',
])

/** Human-readable type chips (exclude generic Google types). */
export function placeTypeLabels(types: string[] | null | undefined): string[] {
  if (!types?.length) return []
  return types
    .filter((t) => t && !HIDE_PLACE_TYPES.has(t))
    .slice(0, 6)
    .map((t) => t.replace(/_/g, ' '))
}
