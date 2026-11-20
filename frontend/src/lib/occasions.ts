import type { Occasion } from '../types/quest'

// The four occasions, in the order the home page lists them.
//
// One-word names on purpose: an occasion says who you are with, not what
// time of day it is — a date can be a breakfast.
//
// Each has one photograph, shown faintly behind its tile so the words stay
// the subject. The files are in public/occasions/ (640 px wide WebP, about
// 160 KB for all four), from Unsplash; sources and photographers are in
// public/occasions/CREDITS.md.

export type OccasionKey = Occasion

export const OCCASIONS = [
  {
    key: 'date',
    label: 'Date',
    desc: 'Just the two of you',
    photo: '/occasions/date.webp',
    // Which part of the picture a crop keeps. Here: the two cups on the
    // left, not the third on the right.
    focus: '0% 62%',
  },
  {
    key: 'friends',
    label: 'Friends',
    desc: "The gang's all here",
    photo: '/occasions/friends.webp',
    focus: '50% 40%',
  },
  {
    key: 'solo',
    label: 'Solo',
    desc: 'Just you, on purpose',
    photo: '/occasions/solo.webp',
    focus: '50% 45%',
  },
  {
    key: 'family',
    label: 'Family',
    desc: 'All of you, fed and happy',
    photo: '/occasions/family.webp',
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
