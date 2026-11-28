// When a quest starts: the day and time choices in the planner sheet.
// Pure functions of a clock, so `npm test` can check them.
//
// Mirrors backend/models.py (EARLIEST_START_MIN, LATEST_START_MIN,
// PLAN_AHEAD_DAYS) and backend/quest_generator.py (_spoken_part_at,
// _plan_part_at, _DAY_PART_START): change one, change both.

export type DayPart = 'morning' | 'afternoon' | 'evening' | 'night'
export type Occasion = 'date' | 'friends' | 'solo' | 'family'

/** 07:00 to 22:00: few places open earlier, little is open later. */
export const EARLIEST_START_MIN = 7 * 60
export const LATEST_START_MIN = 22 * 60
/** Times are offered every half hour. */
export const START_STEP_MIN = 30
/** Today and the six days after it. */
export const PLAN_AHEAD_DAYS = 6
export const MAX_STOPS = 4
/** A family night is dinner, a treat and bowling or a film: three at most. */
export const FAMILY_NIGHT_MAX_STOPS = 3

/** The time each day part button starts at. */
export const DAY_PART_START: Record<DayPart, string> = {
  morning: '10:00',
  afternoon: '13:00',
  evening: '17:30',
  night: '20:00',
}

export function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

export function toHhmm(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

/** "19:30" → "7:30 pm". */
export function timeLabel(hhmm: string): string {
  const minutes = toMinutes(hhmm)
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  const suffix = h < 12 ? 'am' : 'pm'
  const h12 = h % 12 === 0 ? 12 : h % 12
  return m === 0 ? `${h12} ${suffix}` : `${h12}:${String(m).padStart(2, '0')} ${suffix}`
}

/** What a person calls a time: picks the highlighted day part button. */
export function spokenDayPart(hhmm: string): DayPart {
  const t = toMinutes(hhmm)
  if (t < 12 * 60) return 'morning'
  if (t < 17 * 60) return 'afternoon'
  if (t < 20 * 60) return 'evening'
  return 'night'
}

/** Which plan the engine builds for a start time (see PLANS in
 * backend/quest_templates.py). */
export function planDayPart(hhmm: string): DayPart {
  const t = toMinutes(hhmm)
  if (t >= 18 * 60 + 30) return 'night'
  if (t >= 15 * 60) return 'evening'
  if (t >= 11 * 60 + 30) return 'afternoon'
  return 'morning'
}

/** The most stops a plan can have at this time. */
export function maxStopsFor(occasion: Occasion, hhmm: string): number {
  return occasion === 'family' && planDayPart(hhmm) === 'night'
    ? FAMILY_NIGHT_MAX_STOPS
    : MAX_STOPS
}

/** "2026-11-28" for the device's calendar day `offset` days from `now`. */
export function isoDay(now: Date, offset: number): string {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "Today", "Tomorrow", then "Mon 1 Dec". */
export function dayLabel(now: Date, offset: number): string {
  if (offset === 0) return 'Today'
  if (offset === 1) return 'Tomorrow'
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + offset)
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`
}

/** The start times on offer for a day: every half hour from 07:00 to 22:00,
 * and today only those not yet past. Empty when today is over. */
export function timeChoices(now: Date, offset: number): string[] {
  let from = EARLIEST_START_MIN
  if (offset === 0) {
    const nowMin = now.getHours() * 60 + now.getMinutes()
    from = Math.max(from, Math.ceil(nowMin / START_STEP_MIN) * START_STEP_MIN)
  }
  const out: string[] = []
  for (let t = from; t <= LATEST_START_MIN; t += START_STEP_MIN) out.push(toHhmm(t))
  return out
}

export type DayChoice = { offset: number; label: string; disabled: boolean }

/** Today (disabled once nothing is left to start today) and the next six days. */
export function dayChoices(now: Date): DayChoice[] {
  const out: DayChoice[] = []
  for (let offset = 0; offset <= PLAN_AHEAD_DAYS; offset += 1) {
    out.push({
      offset,
      label: dayLabel(now, offset),
      disabled: timeChoices(now, offset).length === 0,
    })
  }
  return out
}

export type Start = { offset: number; time: string }

/** The start for a tap on a day part button, on the chosen day.
 *
 * Today, a time already past moves to the next time still on offer while
 * that is the same part of the day (a tap on "Evening" at 6:10 pm gives
 * 6:30 pm). A part of the day that is over moves to tomorrow. */
export function startForDayPart(now: Date, offset: number, part: DayPart): Start {
  const wanted = DAY_PART_START[part]
  const choices = timeChoices(now, offset)
  if (choices.includes(wanted)) return { offset, time: wanted }
  const sameOffset = choices.find(
    (t) => toMinutes(t) > toMinutes(wanted) && spokenDayPart(t) === part,
  )
  if (sameOffset) return { offset, time: sameOffset }
  return { offset: offset + 1, time: wanted }
}

/** A start that is still on offer: the same time on the chosen day when it
 * can be had, else the next one that can. */
export function keepStartValid(now: Date, start: Start): Start {
  const choices = timeChoices(now, start.offset)
  if (choices.includes(start.time)) return start
  const later = choices.find((t) => toMinutes(t) >= toMinutes(start.time))
  if (later) return { offset: start.offset, time: later }
  if (choices.length > 0) return { offset: start.offset, time: choices[choices.length - 1] }
  return { offset: start.offset + 1, time: start.time }
}

/** What a quest page calls the outing's day: "Today", "Tomorrow", otherwise
 * "Thu 3 Dec". `iso` is "YYYY-MM-DD"; null for anything else. */
export function questDayLabel(iso: string | null | undefined, now: Date): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? '')
  if (!match) return null
  const day = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  if (Number.isNaN(day.getTime())) return null
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const offset = Math.round((day.getTime() - today.getTime()) / 86_400_000)
  if (offset === 0) return 'Today'
  if (offset === 1) return 'Tomorrow'
  return `${WEEKDAYS[day.getDay()]} ${day.getDate()} ${MONTHS[day.getMonth()]}`
}
