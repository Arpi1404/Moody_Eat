import type { Occasion } from '../types/quest'

// The four occasions, in the order the home page lists them.
//
// One-word names on purpose: an occasion says who you are with, not what
// time of day it is — a date can be a breakfast.
//
// Each has one photograph, shown faintly behind its tile so the words stay
// the subject. All four are from Unsplash (free licence, no attribution
// required); credits are in public/occasions/CREDITS.md.

export type OccasionKey = Occasion

export const OCCASIONS = [
  {
    key: 'date',
    label: 'Date',
    desc: 'Just the two of you',
    photo: 'https://images.unsplash.com/photo-1635956541203-4625130f761f?auto=format&fit=crop&w=800&q=70',
    // Where the subject sits, so a crop never loses it.
    focus: '38% 62%',
  },
  {
    key: 'friends',
    label: 'Friends',
    desc: "The gang's all here",
    photo: 'https://images.unsplash.com/photo-1654912912322-b0b98a92011d?auto=format&fit=crop&w=800&q=70',
    focus: '50% 40%',
  },
  {
    key: 'solo',
    label: 'Solo',
    desc: 'Just you, on purpose',
    photo: 'https://images.unsplash.com/photo-1474366521946-c3d4b507abf2?auto=format&fit=crop&w=800&q=70',
    focus: '50% 45%',
  },
  {
    key: 'family',
    label: 'Family',
    desc: 'All of you, fed and happy',
    photo: 'https://images.unsplash.com/photo-1665989215795-f67f4723087d?auto=format&fit=crop&w=800&q=70',
    focus: '50% 50%',
  },
] as const satisfies readonly {
  key: OccasionKey
  label: string
  desc: string
  photo: string
  focus: string
}[]

export const OCCASION_LABELS: Record<OccasionKey, string> = {
  date: 'Date',
  friends: 'Friends',
  solo: 'Solo',
  family: 'Family',
}

/** The label for an occasion read from stored data, which may be anything. */
export function occasionLabel(occasion: string | null | undefined): string | null {
  return occasion && occasion in OCCASION_LABELS
    ? OCCASION_LABELS[occasion as OccasionKey]
    : null
}

export function occasionPhoto(occasion: OccasionKey): string {
  return OCCASIONS.find((o) => o.key === occasion)!.photo
}
