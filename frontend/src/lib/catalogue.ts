// What the home page says about a catalogue quest, and which one it shows
// first.

import type { Quest, Stop, Weekday } from '../types/quest'
import { budgetLabel, formatInrEstimate } from './budget'
import {
  closedTodayLine,
  indiaDayNumber,
  indiaMinuteOfDay,
  indiaWeekday,
  notOnLine,
} from './closedDays'
import { OCCASION_LABELS } from './occasions'

// ── Text ──────────────────────────────────────────────────────────────────────

export function durationText(minutes: number): string {
  const hours = minutes / 60
  return Number.isInteger(hours) ? `${hours}h` : `${hours.toFixed(1)}h`
}

/** The ₹ range per person when the quest has one, else its budget tier. */
export function costText(quest: Quest): string {
  const range = formatInrEstimate(
    quest.est_total_per_person_min_inr,
    quest.est_total_per_person_max_inr,
  )
  if (!range) return budgetLabel(quest.total_cost_estimate)
  return range === 'Free' ? range : `${range}/person`
}

/** A stop's name as a one-line list shows it: without a trailing bracket that
 * spells the name out again, as in "MTR (Mavalli Tiffin Rooms)". */
export function shortStopName(name: string): string {
  return name.replace(/\s*\([^()]*\)\s*$/, '') || name
}

export function stopNames(quest: Quest): string[] {
  return quest.stops.map((stop) => shortStopName(stop.place.name))
}

/** "6 pm", "4:30 pm", or null when the quest has no readable start. */
export function startText(quest: Quest): string | null {
  const minutes = startMinute(quest)
  if (minutes === null) return null
  const hour = Math.floor(minutes / 60)
  const rest = minutes % 60
  const clock = `${hour % 12 || 12}${rest ? `:${String(rest).padStart(2, '0')}` : ''}`
  return `${clock} ${hour < 12 ? 'am' : 'pm'}`
}

/** The stop whose photo leads the quest: the one it names, else the first. */
export function leadStop(quest: Quest): Stop | undefined {
  const ref = quest.photo_stop
  if (!ref) return quest.stops[0]
  const named = ref.place_id
    ? quest.stops.find((stop) => stop.place.provider_id === ref.place_id)
    : quest.stops[ref.stop_index]
  return named ?? quest.stops[0]
}

/** Ends a part of a spoken label with one full stop, however it ended. */
function sentence(text: string): string {
  return /[.!?]$/.test(text) ? text : `${text}.`
}

/** What a screen reader hears for a card or the preview: everything it shows,
 * in order, starting with the title. */
export function cardLabel(
  quest: Quest,
  today: Weekday,
  { withAudience = true, withStart = false } = {},
): string {
  const start = withStart ? startText(quest) : null
  const shutToday = closedTodayLine(quest, today)
  return [
    quest.title,
    `${OCCASION_LABELS[quest.occasion] ?? 'Quest'} quest`,
    withAudience ? quest.audience_line : null,
    `Stops in order: ${stopNames(quest).join(', then ')}`,
    start ? `Starts ${start}` : null,
    `${durationText(quest.total_duration_minutes)}, ${costText(quest)}`,
    shutToday,
    notOnLine(quest),
  ]
    .filter((part): part is string => Boolean(part))
    .map(sentence)
    .join(' ')
}

// ── The quest shown first ─────────────────────────────────────────────────────

const at = (hour: number, minute = 0): number => hour * 60 + minute

/** When a quest should start to suit someone arriving at this time (India),
 * best first. Each is a window of start times, [from, before). */
function suitableStarts(arrival: number): [number, number][] {
  const morning: [number, number] = [at(4), at(12)]
  const afternoon: [number, number] = [at(11), at(17)]
  const evening: [number, number] = [at(16), at(24)]
  // Past six, a 4 pm start has gone; offer what can still nearly be made.
  const laterEvening: [number, number] = [at(17, 30), at(24)]
  const lateStart: [number, number] = [at(19), at(24)]

  if (arrival >= at(4) && arrival < at(11)) return [morning, afternoon, evening]
  if (arrival >= at(11) && arrival < at(15)) return [afternoon, evening]
  if (arrival >= at(15) && arrival < at(18)) return [evening, afternoon]
  if (arrival >= at(18) && arrival < at(20)) return [laterEvening, evening]
  return [lateStart, laterEvening, evening]
}

function startMinute(quest: Quest): number | null {
  const match = /^(\d{1,2}):(\d{2})/.exec(quest.stops[0]?.time_block_start ?? '')
  return match ? at(Number(match[1]), Number(match[2])) : null
}

/** The quest the home page shows as its example: one that suits the time the
 * visitor arrived and has no stop shut today. It is not random, so everyone
 * arriving in the same part of the same day sees the same one, and it moves on
 * from day to day where more than one suits. Null when none can be shown. */
export function pickHeroQuest(quests: Quest[], arrivedAt: Date): Quest | null {
  const today = indiaWeekday(arrivedAt)
  const open = quests.filter(
    (q) => q.stops.length > 0 && closedTodayLine(q, today) === null,
  )
  if (!open.length) return null

  const fitting = suitableStarts(indiaMinuteOfDay(arrivedAt))
    .map(([from, before]) =>
      open.filter((q) => {
        const start = startMinute(q)
        return start !== null && start >= from && start < before
      }),
    )
    .find((found) => found.length > 0)

  // Ordered by id so the answer does not depend on the order they arrived in.
  const pool = [...(fitting ?? open)].sort((a, b) => a.id.localeCompare(b.id))
  return pool[indiaDayNumber(arrivedAt) % pool.length]
}
