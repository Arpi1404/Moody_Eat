// Catalogue quests that do not work every day of the week: which days, which
// stop is the reason, and whether today is one of them.
//
// "Today" is the date in India, where the places are, whatever the clock of
// the device says its time zone is.

import type { Quest, Weekday } from '../types/quest'

/** Monday first, as in backend/models.py. */
const WEEKDAYS: Weekday[] = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday',
]

// India keeps one offset all year (no daylight saving).
const INDIA_OFFSET_MS = 330 * 60 * 1000

export function indiaWeekday(now: Date = new Date()): Weekday {
  const inIndia = new Date(now.getTime() + INDIA_OFFSET_MS)
  // getUTCDay counts from Sunday = 0.
  return WEEKDAYS[(inIndia.getUTCDay() + 6) % 7]
}

/** The quest's closed days, each with the stop it is about. An entry follows
 * its place: when that stop has been swapped out or removed, it no longer
 * applies. */
function closures(quest: Quest): { day: Weekday; stopIndex: number }[] {
  return (quest.closed_days ?? []).flatMap(({ day, stop_index, place_id }) => {
    const stopIndex = place_id
      ? quest.stops.findIndex((s) => s.place.provider_id === place_id)
      : stop_index
    return WEEKDAYS.includes(day) && quest.stops[stopIndex]
      ? [{ day, stopIndex }]
      : []
  })
}

function listed(items: string[], joiner: 'and' | 'or'): string {
  return items.length < 2
    ? items.join('')
    : `${items.slice(0, -1).join(', ')} ${joiner} ${items[items.length - 1]}`
}

const plural = (day: Weekday): string => `${day[0].toUpperCase()}${day.slice(1)}s`

/** Names of the stops shut on `day`, in the order the quest visits them. */
function stopsShutOn(quest: Quest, day: Weekday): string[] {
  const indexes = closures(quest)
    .filter((c) => c.day === day)
    .map((c) => c.stopIndex)
  return quest.stops
    .filter((_, i) => indexes.includes(i))
    .map((s) => s.place.name)
}

function closedWeekdays(quest: Quest): Weekday[] {
  const days = new Set(closures(quest).map((c) => c.day))
  return WEEKDAYS.filter((day) => days.has(day))
}

/** "Not on Mondays", or null for a quest that works all week. */
export function notOnLine(quest: Quest): string | null {
  const days = closedWeekdays(quest)
  return days.length ? `Not on ${listed(days.map(plural), 'or')}` : null
}

/** "Museo Camera is closed today", or null when every stop is open. */
export function closedTodayLine(quest: Quest, today: Weekday): string | null {
  const names = stopsShutOn(quest, today)
  if (!names.length) return null
  return `${listed(names, 'and')} ${names.length === 1 ? 'is' : 'are'} closed today`
}

/** The quest page's one notice. `today` is true when a stop is shut today. */
export function closedNotice(
  quest: Quest,
  today: Weekday,
): { today: boolean; headline: string; detail: string } | null {
  const notOn = notOnLine(quest)
  if (!notOn) return null
  const shutToday = closedTodayLine(quest, today)
  if (shutToday) {
    return { today: true, headline: `${shutToday}.`, detail: `${notOn}.` }
  }
  const reasons = closedWeekdays(quest).map((day) => {
    const names = stopsShutOn(quest, day)
    return `${listed(names, 'and')} ${names.length === 1 ? 'is' : 'are'} shut on ${plural(day)}`
  })
  return { today: false, headline: `${notOn}.`, detail: `${reasons.join('; ')}.` }
}

/** The same quests, with those that have a stop shut today moved to the end.
 * Each group keeps its order. Nothing is dropped. */
export function closedTodayLast(quests: Quest[], today: Weekday): Quest[] {
  const shut = (quest: Quest) => closedTodayLine(quest, today) !== null
  return [...quests.filter((q) => !shut(q)), ...quests.filter(shut)]
}
