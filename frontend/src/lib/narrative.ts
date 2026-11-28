// The intro after a quest's stops change. An automatic intro names specific
// stops, so after an edit it is written again from the new list.

import type { DayPart, Quest } from '../types/quest'

// The sentence the backend writes when no model-written narrative is
// available. Mirrors _OUTING_PHRASES and _fallback_narrative in
// backend/services/place_blurbs_service.py: change one, change both.
const OUTING_PHRASES: Record<string, Record<DayPart, string>> = {
  date: {
    morning: 'morning date',
    afternoon: 'afternoon date',
    evening: 'evening date',
    night: 'date night',
  },
  friends: {
    morning: 'morning out with friends',
    afternoon: 'afternoon out with friends',
    evening: 'evening out with friends',
    night: 'night out with friends',
  },
  solo: {
    morning: 'solo morning',
    afternoon: 'solo afternoon',
    evening: 'solo evening',
    night: 'solo night out',
  },
  family: {
    morning: 'family morning out',
    afternoon: 'family afternoon out',
    evening: 'family evening out',
    night: 'family night out',
  },
}

const BUDGET_WORDS: Record<string, string> = {
  cheap: 'budget-friendly',
  splurge: 'splurge-worthy',
}

/** The backend's phrases for a quest with no known start time. */
const UNTIMED_PHRASES = [
  'date',
  'outing with friends',
  'solo outing',
  'family outing',
]

/** What a person would call the hour a quest starts at. */
function spokenDayPart(start: string | undefined): DayPart {
  const hour = parseInt((start ?? '').split(':')[0], 10)
  if (Number.isNaN(hour) || hour < 5 || hour >= 20) return 'night'
  if (hour < 12) return 'morning'
  if (hour < 17) return 'afternoon'
  return 'evening'
}

function outingPhrase(quest: Quest): string {
  const dayPart = spokenDayPart(quest.stops[0]?.time_block_start)
  let phrase =
    OUTING_PHRASES[quest.occasion]?.[dayPart] ?? `${quest.occasion} outing`
  const budget = BUDGET_WORDS[quest.total_cost_estimate]
  if (budget) phrase = `${budget} ${phrase}`
  return `${/^[aeiou]/i.test(phrase) ? 'An' : 'A'} ${phrase}`
}

/** "A and B", "A, B and C". */
function listOf(names: string[]): string {
  return names.length === 1
    ? names[0]
    : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/** Everything after "An evening date in <area>". */
function stopsTail(names: string[]): string {
  if (names.length === 0) return '.'
  if (names.length === 1) return `, built around ${names[0]}.`
  const first = names[0]
  const last = names[names.length - 1]
  if (names.length === 2) return `: start at ${first}, then finish at ${last}.`
  return `: start at ${first}, move on to ${listOf(names.slice(1, -1))}, then finish at ${last}.`
}

/** The same, for the sentence a quest built by hand starts with. Mirrors
 * customNarrative in lib/questBuild.ts. */
function customTail(names: string[]): string {
  if (names.length === 1) return `, anchored around ${names[0]}.`
  return `: starting at ${names.slice(0, -1).join(', ')}, then finishing at ${names[names.length - 1]}.`
}

const OUTING_HEAD = new RegExp(
  `^An? (?:(?:${Object.values(BUDGET_WORDS).join('|')}) )?(?:${[
    ...Object.values(OUTING_PHRASES).flatMap((byPart) => Object.values(byPart)),
    ...UNTIMED_PHRASES,
  ].join('|')}) in (.+)$`,
)
const CUSTOM_HEAD = /^A custom (?:date|friends|solo|family) plan in (.+)$/

// The server stores the intro with runs of spaces closed up, while a stop's
// name keeps them.
const oneSpaced = (text: string) => text.trim().replace(/\s+/g, ' ')

/** The area an automatic intro names, or "". Only a sentence we wrote
 * ourselves is read: one that ends exactly as it would for these stops. A
 * model's or an editor's own prose gives "". */
function areaNamedIn(quest: Quest): string {
  const text = oneSpaced(quest.narrative)
  const names = quest.stops.map((stop) => stop.place.name)
  for (const [tail, head] of [
    [stopsTail(names), OUTING_HEAD],
    [customTail(names), CUSTOM_HEAD],
  ] as const) {
    const ending = oneSpaced(tail)
    if (!text.endsWith(ending)) continue
    const found = head.exec(text.slice(0, -ending.length))
    if (found) return found[1]
  }
  return ''
}

function rebuildNarrative(quest: Quest, area: string): string {
  const where = area ? ` in ${area}` : ''
  const names = quest.stops.map((stop) => stop.place.name)
  return `${outingPhrase(quest)}${where}${stopsTail(names)}`
}

/** The intro `next` should carry, given the quest it was edited from. */
export function narrativeAfterEdit(previous: Quest, next: Quest): string {
  // The length is compared too: removing the last stop changes no other
  // position.
  const stopsChanged =
    next.stops.length !== previous.stops.length ||
    next.stops.some(
      (stop, i) =>
        stop.place.provider_id !== previous.stops[i]?.place.provider_id,
    )
  // An intro the creator wrote is theirs: it stays as written.
  if (!stopsChanged || !next.narrative || next.narrative_by_creator) {
    return next.narrative
  }
  return rebuildNarrative(next, areaNamedIn(previous))
}
